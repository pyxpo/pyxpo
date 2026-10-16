import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

import {
  Completion, Data, Naming, colorSpots, completionAt, convertStyleKeys, detectNaming,
  detectPropNaming, diagnose, hoverAt, isPyxpoFile, spell, styleKeyMarkdown, valuesFor,
} from "./analyze";
import { formatColor, parseColor } from "./colors";
import { importEdit, missingNames, nameContext } from "./imports";
import { scan, Scan } from "./pyscan";
import {
  Schema, isTable, mapConfigErrors, schemaAt, schemaMarkdown, tomlColorSpots, tomlCompletionAt, tomlKeyAt,
  typeLabel,
} from "./toml";

const PY: vscode.DocumentSelector = { language: "python" };
const TOML: vscode.DocumentSelector = { pattern: "**/pyproject.toml" };

let data: Data;
const scans = new WeakMap<vscode.TextDocument, { version: number; scan: Scan; pyxpo: boolean }>();

function cfg(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration("pyxpo");
}

/** The scan of a document, cached per version; null for Python files that do not use pyxpo. */
function scanOf(doc: vscode.TextDocument): Scan | null {
  let hit = scans.get(doc);
  if (!hit || hit.version !== doc.version) {
    const text = doc.getText();
    const pyxpo = isPyxpoFile(text);
    hit = { version: doc.version, scan: pyxpo ? scan(text) : { toks: [], nodes: [] }, pyxpo };
    scans.set(doc, hit);
  }
  return hit.pyxpo ? hit.scan : null;
}

function styleNaming(s: Scan): Naming {
  const set = cfg().get<string>("styleNaming", "auto");
  return set === "camelCase" || set === "snake_case" ? set : detectNaming(s, data);
}

function propNaming(s: Scan): Naming {
  const set = cfg().get<string>("styleNaming", "auto");
  return set === "camelCase" || set === "snake_case" ? set : detectPropNaming(s, data);
}

function range(doc: vscode.TextDocument, start: number, end: number): vscode.Range {
  return new vscode.Range(doc.positionAt(start), doc.positionAt(end));
}

// ---- Python: completion, hover, colors, checks ------------------------------------------------------------

function md(text: string): vscode.MarkdownString {
  return new vscode.MarkdownString(text);
}

function styleItems(doc: vscode.TextDocument, c: Extract<Completion, { kind: "styleKey" }>, s: Scan): vscode.CompletionItem[] {
  const naming = styleNaming(s);
  const r = range(doc, c.replaceStart, c.replaceEnd);
  const out: vscode.CompletionItem[] = [];
  for (const [key, info] of Object.entries(data.style.keys)) {
    if (c.present.includes(key)) continue;
    const name = spell(key, naming);
    const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Property);
    item.detail = info.kind === "enum" ? (info.values || []).join(" | ") : info.kind;
    item.documentation = md(styleKeyMarkdown(key, info));
    item.range = r;
    // keep the other spelling searchable: typing "font_s" still finds fontSize
    item.filterText = name === key ? name : `${name} ${key}`;
    if (c.form === "dict") {
      item.insertText = new vscode.SnippetString(`"${name}": ${valueSnippet(info.kind)}`);
    } else if (c.form === "kw") {
      item.insertText = new vscode.SnippetString(`${name}=${valueSnippet(info.kind)}`);
    } else {
      item.insertText = name;
    }
    if (info.kind === "enum" || info.kind === "color") {
      item.command = { command: "editor.action.triggerSuggest", title: "values" };
    }
    out.push(item);
  }
  return out;
}

function valueSnippet(kind: string): string {
  switch (kind) {
    case "enum": case "string": return '"$1"';
    case "color": return '"${1:#000000}"';
    case "bool": return "${1|True,False|}";
    case "gradient": return '{"colors": ["${1:#000000}", "${2:#ffffff}"], "angle": ${3:180}}';
    case "transform": return '[{"${1:rotate}": "${2:45deg}"}]';
    default: return "${1:0}";
  }
}

function valueItems(doc: vscode.TextDocument, c: Extract<Completion, { kind: "value" }>): vscode.CompletionItem[] {
  const { values, quote } = valuesFor(c.key, data);
  const info = data.style.keys[c.key];
  const r = range(doc, c.replaceStart, c.replaceEnd);
  return values.map((v, i) => {
    const color = info?.kind === "color" ? data.named_colors[v] : undefined;
    const item = new vscode.CompletionItem(v, color ? vscode.CompletionItemKind.Color : vscode.CompletionItemKind.EnumMember);
    item.insertText = c.quoted || !quote ? v : `"${v}"`;
    item.range = r;
    item.sortText = String(i).padStart(3, "0");
    if (color) { item.documentation = color; item.detail = color; }
    return item;
  });
}

function propItems(doc: vscode.TextDocument, c: Extract<Completion, { kind: "prop" }>, s: Scan): vscode.CompletionItem[] {
  const comp = data.components[c.component];
  const naming = propNaming(s);
  const r = range(doc, c.replaceStart, c.replaceEnd);
  return comp.props.filter((p) => !c.present.includes(p)).map((p, i) => {
    const name = spell(p, naming);
    const item = new vscode.CompletionItem(name + "=", vscode.CompletionItemKind.Field);
    item.insertText = name + "=";
    item.filterText = name === p ? name : `${name} ${p}`;
    item.detail = `${c.component} prop`;
    item.range = r;
    item.sortText = "!" + String(i).padStart(3, "0"); // before Pylance's own suggestions
    return item;
  });
}

const completion: vscode.CompletionItemProvider = {
  provideCompletionItems(doc, pos, _token, ctx) {
    const s = scanOf(doc);
    const c = s && completionAt(doc.getText(), doc.offsetAt(pos), data, s);
    if (s && c) {
      if (c.kind === "styleKey") return styleItems(doc, c, s);
      if (c.kind === "value") return valueItems(doc, c);
      if (!ctx.triggerCharacter) return [...propItems(doc, c, s), ...importItems(doc, pos)];
      return propItems(doc, c, s);
    }
    // typing a name: offer pyxpo's exports with their import (the trigger characters are for the cases above)
    return ctx.triggerCharacter ? undefined : importItems(doc, pos);
  },
};

const EXPORT_KIND: Record<string, vscode.CompletionItemKind> = {
  component: vscode.CompletionItemKind.Function,
  class: vscode.CompletionItemKind.Class,
  hook: vscode.CompletionItemKind.Function,
  function: vscode.CompletionItemKind.Function,
};

/** True for a Python file that imports pyxpo or sits in a pyxpo project. */
function usesPyxpo(doc: vscode.TextDocument): boolean {
  return !!scanOf(doc) || (doc.uri.scheme === "file" && !!projectOf(path.dirname(doc.uri.fsPath)));
}

/** pyxpo exports for the name being typed, each adding its `from pyxpo import` when picked. */
function importItems(doc: vscode.TextDocument, pos: vscode.Position): vscode.CompletionItem[] {
  if (!cfg().get<boolean>("autoImport", true) || !usesPyxpo(doc)) return [];
  const text = doc.getText();
  const s = scan(text);
  const at = nameContext(text, s, doc.offsetAt(pos));
  if (!at) return [];
  const replace = range(doc, at.start, doc.offsetAt(pos));
  const out: vscode.CompletionItem[] = [];
  for (const [name, info] of Object.entries(data.exports)) {
    const e = importEdit(text, s, name);
    if (!e) continue; // already imported or defined: Pylance offers it
    const item = new vscode.CompletionItem({ label: name, description: "pyxpo" }, EXPORT_KIND[info.kind]);
    item.range = replace;
    item.detail = `Auto-import from pyxpo (${info.kind})`;
    const comp = data.components[name];
    item.documentation = md(`\`from pyxpo import ${name}\`${info.doc ? "\n\n" + info.doc : ""}`
      + (comp && comp.props.length ? `\n\nProps: ${comp.props.map((p) => `\`${p}\``).join(", ")}` : ""));
    item.additionalTextEdits = [vscode.TextEdit.replace(range(doc, e.start, e.end), e.text)];
    item.sortText = `~${name}`; // after names the file already has
    out.push(item);
  }
  return out;
}

/** Adds `from pyxpo import` lines for every pyxpo name the file uses but does not import. */
async function addImports(): Promise<void> {
  const ed = vscode.window.activeTextEditor;
  if (!ed || ed.document.languageId !== "python") return;
  const names = missingNames(ed.document.getText(), scan(ed.document.getText()), Object.keys(data.exports));
  if (!names.length) { vscode.window.setStatusBarMessage("pyxpo: no missing imports", 3000); return; }
  for (const name of names) {
    const text = ed.document.getText();
    const e = importEdit(text, scan(text), name);
    if (e) await ed.edit((b) => b.replace(range(ed.document, e.start, e.end), e.text));
  }
  vscode.window.setStatusBarMessage(`pyxpo: imported ${names.join(", ")}`, 4000);
}

const hover: vscode.HoverProvider = {
  provideHover(doc, pos) {
    const s = scanOf(doc);
    if (!s) return undefined;
    const h = hoverAt(doc.getText(), doc.offsetAt(pos), data, s);
    return h ? new vscode.Hover(md(h.markdown), range(doc, h.start, h.end)) : undefined;
  },
};

function toVsColor(value: string): vscode.Color | null {
  const c = parseColor(value, data.named_colors);
  return c ? new vscode.Color(c.r, c.g, c.b, c.a) : null;
}

function presentations(color: vscode.Color, original: string): vscode.ColorPresentation[] {
  const c = { r: color.red, g: color.green, b: color.blue, a: color.alpha };
  const out = [formatColor(c, original)];
  for (const alt of ["#000000", "rgba(0, 0, 0, 1)"]) {
    const v = formatColor(c, alt);
    if (!out.includes(v)) out.push(v);
  }
  return out.map((v) => new vscode.ColorPresentation(v));
}

const pyColors: vscode.DocumentColorProvider = {
  provideDocumentColors(doc) {
    const s = scanOf(doc);
    if (!s || !cfg().get<boolean>("colorDecorators", true)) return [];
    const out: vscode.ColorInformation[] = [];
    for (const spot of colorSpots(doc.getText(), data, s)) {
      const c = toVsColor(spot.value);
      if (c) out.push(new vscode.ColorInformation(range(doc, spot.start, spot.end), c));
    }
    return out;
  },
  provideColorPresentations(color, ctx) {
    return presentations(color, ctx.document.getText(ctx.range));
  },
};

const tomlColors: vscode.DocumentColorProvider = {
  provideDocumentColors(doc) {
    if (!cfg().get<boolean>("colorDecorators", true)) return [];
    const lines = doc.getText().split(/\r?\n/);
    return tomlColorSpots(lines).flatMap((s) => {
      const c = toVsColor(s.value);
      return c ? [new vscode.ColorInformation(new vscode.Range(s.line, s.start, s.line, s.end), c)] : [];
    });
  },
  provideColorPresentations(color, ctx) {
    // the config accepts only hex
    const c = { r: color.red, g: color.green, b: color.blue, a: color.alpha };
    const orig = ctx.document.getText(ctx.range);
    return [new vscode.ColorPresentation(formatColor(c, orig.startsWith("#") ? orig : "#000000"))];
  },
};

const SEVERITY = {
  error: vscode.DiagnosticSeverity.Error,
  warning: vscode.DiagnosticSeverity.Warning,
  info: vscode.DiagnosticSeverity.Information,
};

function checkPython(doc: vscode.TextDocument, coll: vscode.DiagnosticCollection): void {
  if (doc.languageId !== "python") return;
  const s = cfg().get<boolean>("diagnostics.enable", true) ? scanOf(doc) : null;
  if (!s) { coll.delete(doc.uri); return; }
  coll.set(doc.uri, diagnose(doc.getText(), data, s).map((p) => {
    const d = new vscode.Diagnostic(range(doc, p.start, p.end), p.message, SEVERITY[p.severity]);
    d.source = "pyxpo";
    d.code = p.code;
    return d;
  }));
}

const ADD_IMPORTS = vscode.CodeActionKind.Source.append("addMissingImports").append("pyxpo");

const quickFix: vscode.CodeActionProvider = {
  provideCodeActions(doc, _range, ctx) {
    const out: vscode.CodeAction[] = [];
    const text = doc.getText();
    const wanted = new Set<string>();
    for (const d of ctx.diagnostics) {
      // Pylance: "View" is not defined; Ruff / Flake8: Undefined name `View`, undefined name 'View'
      const m = /^"(\w+)" is not defined|^Undefined name [`'](\w+)[`']/i.exec(d.message);
      const name = m && (m[1] || m[2]);
      if (name && data.exports[name]) wanted.add(name);
    }
    const word = doc.getWordRangeAtPosition(_range.start);
    if (word && data.exports[doc.getText(word)] && usesPyxpo(doc)) wanted.add(doc.getText(word));
    const s = scan(text);
    for (const name of wanted) {
      const e = importEdit(text, s, name);
      if (!e) continue;
      const a = new vscode.CodeAction(`Import '${name}' from pyxpo`, vscode.CodeActionKind.QuickFix);
      a.edit = new vscode.WorkspaceEdit();
      a.edit.replace(doc.uri, range(doc, e.start, e.end), e.text);
      a.diagnostics = ctx.diagnostics.filter((d) => d.message.includes(name));
      a.isPreferred = true;
      out.push(a);
    }
    if (usesPyxpo(doc) && missingNames(text, s, Object.keys(data.exports)).length) {
      const a = new vscode.CodeAction("Add all missing pyxpo imports", ADD_IMPORTS);
      a.command = { command: "pyxpo.addImports", title: "Add all missing pyxpo imports" };
      out.push(a);
    }
    for (const d of ctx.diagnostics) {
      // the fix travels in the message: diagnostics reach this provider as copies
      const fix = /did you mean '([^']+)'/.exec(d.message)?.[1];
      if (d.source !== "pyxpo" || d.code !== "unknown-key" || !fix) continue;
      const a = new vscode.CodeAction(`Change to '${fix}'`, vscode.CodeActionKind.QuickFix);
      a.edit = new vscode.WorkspaceEdit();
      a.edit.replace(doc.uri, d.range, fix);
      a.diagnostics = [d];
      a.isPreferred = true;
      out.push(a);
    }
    return out;
  },
};

// ---- pyproject.toml ---------------------------------------------------------------------------------------

function configSchema(): Schema {
  return data.config as Schema;
}

const tomlCompletion: vscode.CompletionItemProvider = {
  provideCompletionItems(doc, pos) {
    const lines = doc.getText().split(/\r?\n/);
    const c = tomlCompletionAt(lines, pos.line, pos.character, configSchema());
    if (!c) return undefined;
    const r = new vscode.Range(pos.line, c.replaceStart, pos.line, pos.character);
    if (c.kind === "header") {
      return c.options.map((o) => {
        const item = new vscode.CompletionItem(o, vscode.CompletionItemKind.Module);
        item.range = r;
        return item;
      });
    }
    if (c.kind === "key") {
      return Object.entries(c.schema.properties || {}).filter(([k]) => !c.present.includes(k)).map(([k, s]) => {
        const item = new vscode.CompletionItem(k, vscode.CompletionItemKind.Property);
        item.detail = typeLabel(s);
        item.documentation = md(schemaMarkdown(k, s));
        item.range = r;
        if (!isTable(s)) {
          item.insertText = new vscode.SnippetString(`${k} = ${tomlValueSnippet(s)}`);
          if (s.enum) item.command = { command: "editor.action.triggerSuggest", title: "values" };
        }
        return item;
      });
    }
    const s = c.schema;
    const values: string[] = s.enum ? s.enum.map(String) : s.type === "boolean" ? ["true", "false"] : [];
    return values.map((v) => {
      const str = s.enum && typeof s.enum.find((x) => String(x) === v) === "string";
      const item = new vscode.CompletionItem(v, vscode.CompletionItemKind.EnumMember);
      item.insertText = str && !c.quoted ? `"${v}"` : v;
      item.range = r;
      return item;
    });
  },
};

function tomlValueSnippet(s: Schema): string {
  if (s.enum) return typeof s.enum[0] === "string" ? '"$1"' : "$1";
  switch (Array.isArray(s.type) ? s.type[0] : s.type) {
    case "string": return s.pattern && s.pattern.includes("0-9a-fA-F") ? '"${1:#ffffff}"' : '"$1"';
    case "boolean": return "${1|true,false|}";
    case "integer": case "number": return "${1:" + (s.minimum ?? 0) + "}";
    case "array": return "[$1]";
    default: return "$1";
  }
}

const tomlHover: vscode.HoverProvider = {
  provideHover(doc, pos) {
    const lines = doc.getText().split(/\r?\n/);
    const k = tomlKeyAt(lines, pos.line, pos.character);
    if (!k || !k.path.length) return undefined;
    const s = schemaAt(configSchema(), k.path);
    if (!s) return undefined;
    return new vscode.Hover(md(schemaMarkdown(k.path.join("."), s)), new vscode.Range(pos.line, k.start, pos.line, k.end));
  },
};

async function checkConfig(doc: vscode.TextDocument, coll: vscode.DiagnosticCollection): Promise<void> {
  if (path.basename(doc.uri.fsPath) !== "pyproject.toml" || doc.uri.scheme !== "file") return;
  const text = doc.getText();
  if (!cfg().get<boolean>("validateConfig", true) || !vscode.workspace.isTrusted || !/^\s*\[tool\.pyxpo\b/m.test(text)) {
    coll.delete(doc.uri);
    return;
  }
  const dir = path.dirname(doc.uri.fsPath);
  const py = await pythonFor(dir);
  cp.execFile(py, ["-m", "pyxpo", "config", "--dir", dir], { cwd: dir, timeout: 30000 }, (err, stdout, stderr) => {
    if (!err) { coll.delete(doc.uri); return; }
    const out = `${stdout}\n${stderr}`;
    if (/No module named pyxpo/.test(out) || (err as any).code === "ENOENT") {
      coll.delete(doc.uri); // no pyxpo in that Python: nothing to say about the file
      return;
    }
    const lines = doc.getText().split(/\r?\n/);
    coll.set(doc.uri, mapConfigErrors(out, lines).map((p) => {
      const d = new vscode.Diagnostic(new vscode.Range(p.line, p.start, p.line, p.end), p.message,
        vscode.DiagnosticSeverity.Error);
      d.source = "pyxpo config";
      return d;
    }));
  });
}

// ---- Python and project lookup, commands ------------------------------------------------------------------

function venvPython(dir: string): string | null {
  for (const v of [".venv", "venv"]) {
    const p = process.platform === "win32" ? path.join(dir, v, "Scripts", "python.exe") : path.join(dir, v, "bin", "python");
    if (fs.existsSync(p)) return p;
  }
  return null;
}

async function pythonFor(dir: string): Promise<string> {
  const set = cfg().get<string>("pythonPath", "").trim();
  if (set) return set;
  try {
    const ext = vscode.extensions.getExtension("ms-python.python");
    if (ext) {
      const api: any = ext.isActive ? ext.exports : await ext.activate();
      const env = api?.environments?.getActiveEnvironmentPath?.(vscode.Uri.file(dir));
      if (env?.path && fs.existsSync(env.path)) return env.path;
    }
  } catch {
    // fall through to the project's venv
  }
  for (let d = dir; ; d = path.dirname(d)) {
    const p = venvPython(d);
    if (p) return p;
    if (path.dirname(d) === d) break;
  }
  return process.platform === "win32" ? "python" : "python3";
}

const projectCache = new Map<string, { at: number; dir: string | null }>();

/** The pyxpo project (a folder whose pyproject.toml has [tool.pyxpo]) containing `start`, cached for 5 s. */
function projectOf(start: string): string | null {
  const hit = projectCache.get(start);
  if (hit && Date.now() - hit.at < 5000) return hit.dir;
  let found: string | null = null;
  for (let d = start; ; d = path.dirname(d)) {
    const p = path.join(d, "pyproject.toml");
    try {
      if (fs.existsSync(p) && /^\s*\[tool\.pyxpo\b/m.test(fs.readFileSync(p, "utf8"))) { found = d; break; }
    } catch {
      // unreadable: keep looking
    }
    if (path.dirname(d) === d) break;
  }
  projectCache.set(start, { at: Date.now(), dir: found });
  return found;
}

/** The pyxpo project of the active file, else of the workspace. */
function projectDir(): string | null {
  const starts: string[] = [];
  const doc = vscode.window.activeTextEditor?.document;
  if (doc && doc.uri.scheme === "file") starts.push(path.dirname(doc.uri.fsPath));
  for (const f of vscode.workspace.workspaceFolders || []) starts.push(f.uri.fsPath);
  for (const start of starts) {
    const d = projectOf(start);
    if (d) return d;
  }
  return null;
}

function quote(arg: string): string {
  if (/^[A-Za-z0-9_\-./:=@]+$/.test(arg)) return arg;
  return process.platform === "win32" ? `"${arg.replace(/"/g, '""')}"` : `'${arg.replace(/'/g, "'\\''")}'`;
}

let terminal: vscode.Terminal | undefined;

async function runPyxpo(args: string[], dir?: string | null): Promise<void> {
  if (!vscode.workspace.isTrusted) {
    // runs the project's python: only in a trusted folder
    const pick = await vscode.window.showWarningMessage("pyxpo: trust this folder to run pyxpo commands.", "Manage Trust");
    if (pick) vscode.commands.executeCommand("workbench.trust.manage");
    return;
  }
  const where = dir === undefined ? projectDir() : dir;
  if (dir === undefined && !where) {
    vscode.window.showErrorMessage("pyxpo: no project found (a pyproject.toml with [tool.pyxpo]).");
    return;
  }
  const cwd = where || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const py = await pythonFor(cwd || process.cwd());
  if (!terminal || terminal.exitStatus !== undefined) terminal = vscode.window.createTerminal({ name: "pyxpo", cwd });
  terminal.show();
  const ps = process.platform === "win32" && (vscode.env.shell || "").toLowerCase().includes("powershell");
  const cmd = [quote(py), "-m", "pyxpo", ...args.map(quote)].join(" ");
  const cd = cwd ? `cd ${quote(cwd)} && ` : "";
  terminal.sendText(ps ? `${cwd ? `Set-Location ${quote(cwd)}; ` : ""}& ${cmd}` : `${cd}${cmd}`);
}

async function pickRun(): Promise<void> {
  const picks = [
    { label: "$(device-mobile) Android", target: "android" },
    { label: "$(device-mobile) iOS", target: "ios" },
    { label: "$(desktop-download) Desktop", target: "desktop" },
    { label: "$(package) Prebuild", target: "prebuild" },
    { label: "$(checklist) Doctor", target: "doctor" },
    { label: "$(settings) Show config", target: "config" },
  ];
  const p = await vscode.window.showQuickPick(picks, { placeHolder: "pyxpo" });
  if (!p) return;
  if (["android", "ios", "desktop"].includes(p.target)) return runPyxpo(["run", p.target]);
  if (p.target === "doctor") return runPyxpo(["doctor"], null);
  return runPyxpo([p.target]);
}

async function create(): Promise<void> {
  const name = await vscode.window.showInputBox({
    prompt: "New pyxpo project name", placeHolder: "my-app",
    validateInput: (v) => (/^[A-Za-z][A-Za-z0-9_-]*$/.test(v) ? null : "Letters, digits, - and _; start with a letter."),
  });
  if (!name) return;
  const folder = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false,
    openLabel: "Create here", defaultUri: vscode.workspace.workspaceFolders?.[0]?.uri });
  if (!folder || !folder.length) return;
  await runPyxpo(["create", name], folder[0].fsPath);
}

async function convertKeys(naming: Naming): Promise<void> {
  const ed = vscode.window.activeTextEditor;
  if (!ed || ed.document.languageId !== "python") return;
  const s = scanOf(ed.document);
  if (!s) { vscode.window.showInformationMessage("pyxpo: this file does not import pyxpo."); return; }
  const edits = convertStyleKeys(ed.document.getText(), naming, data, s);
  if (!edits.length) { vscode.window.showInformationMessage(`pyxpo: style keys are already ${naming}.`); return; }
  await ed.edit((b) => { for (const e of edits) b.replace(range(ed.document, e.start, e.end), e.text); });
  vscode.window.setStatusBarMessage(`pyxpo: ${edits.length} style key(s) changed to ${naming}`, 4000);
}

// ---- activation -------------------------------------------------------------------------------------------

export function activate(ctx: vscode.ExtensionContext): void {
  data = JSON.parse(fs.readFileSync(ctx.asAbsolutePath(path.join("data", "pyxpo.json")), "utf8"));
  const pyDiag = vscode.languages.createDiagnosticCollection("pyxpo");
  const tomlDiag = vscode.languages.createDiagnosticCollection("pyxpo-config");
  ctx.subscriptions.push(pyDiag, tomlDiag);

  ctx.subscriptions.push(
    vscode.languages.registerCompletionItemProvider(PY, completion, '"', "'", "(", "{", ",", " ", ":", "="),
    vscode.languages.registerHoverProvider(PY, hover),
    vscode.languages.registerColorProvider(PY, pyColors),
    vscode.languages.registerCodeActionsProvider(PY, quickFix, { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix, ADD_IMPORTS] }),
    vscode.languages.registerCompletionItemProvider(TOML, tomlCompletion, "[", ".", "=", '"', " "),
    vscode.languages.registerHoverProvider(TOML, tomlHover),
    vscode.languages.registerColorProvider(TOML, tomlColors),
  );

  const timers = new Map<string, NodeJS.Timeout>();
  const later = (doc: vscode.TextDocument) => {
    const k = doc.uri.toString();
    clearTimeout(timers.get(k));
    timers.set(k, setTimeout(() => { timers.delete(k); checkPython(doc, pyDiag); }, 250));
  };
  vscode.workspace.textDocuments.forEach((d) => { checkPython(d, pyDiag); checkConfig(d, tomlDiag); });
  ctx.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((d) => { checkPython(d, pyDiag); checkConfig(d, tomlDiag); }),
    vscode.workspace.onDidChangeTextDocument((e) => later(e.document)),
    vscode.workspace.onDidSaveTextDocument((d) => checkConfig(d, tomlDiag)),
    vscode.workspace.onDidCloseTextDocument((d) => { pyDiag.delete(d.uri); tomlDiag.delete(d.uri); }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (!e.affectsConfiguration("pyxpo")) return;
      vscode.workspace.textDocuments.forEach((d) => { checkPython(d, pyDiag); checkConfig(d, tomlDiag); });
    }),
    vscode.workspace.onDidGrantWorkspaceTrust(() => vscode.workspace.textDocuments.forEach((d) => checkConfig(d, tomlDiag))),
    vscode.window.onDidCloseTerminal((t) => { if (t === terminal) terminal = undefined; }),
  );

  const cmd = (id: string, fn: () => unknown) => ctx.subscriptions.push(vscode.commands.registerCommand(id, fn));
  cmd("pyxpo.run", pickRun);
  cmd("pyxpo.runAndroid", () => runPyxpo(["run", "android"]));
  cmd("pyxpo.runIos", () => runPyxpo(["run", "ios"]));
  cmd("pyxpo.runDesktop", () => runPyxpo(["run", "desktop"]));
  cmd("pyxpo.prebuild", () => runPyxpo(["prebuild"]));
  cmd("pyxpo.doctor", () => runPyxpo(["doctor"], null));
  cmd("pyxpo.config", () => runPyxpo(["config"]));
  cmd("pyxpo.create", create);
  cmd("pyxpo.styleKeysCamel", () => convertKeys("camelCase"));
  cmd("pyxpo.styleKeysSnake", () => convertKeys("snake_case"));
  cmd("pyxpo.addImports", addImports);

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.text = "$(play) pyxpo";
  status.tooltip = "pyxpo: run, prebuild, doctor";
  status.command = "pyxpo.run";
  const showStatus = () => (projectDir() ? status.show() : status.hide());
  showStatus();
  ctx.subscriptions.push(status, vscode.window.onDidChangeActiveTextEditor(showStatus),
    vscode.workspace.onDidChangeWorkspaceFolders(showStatus));
}

export function deactivate(): void {
  // nothing to clean: subscriptions are disposed by VS Code
}
