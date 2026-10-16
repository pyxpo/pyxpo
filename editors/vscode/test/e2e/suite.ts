// Runs inside a real VS Code window (see launch.ts): drives the extension through VS Code's own commands.
import { strict as assert } from "assert";
import * as path from "path";
import * as vscode from "vscode";

const root = () => vscode.workspace.workspaceFolders![0].uri.fsPath;

async function waitFor<T>(what: string, get: () => T | undefined | Promise<T | undefined>, ms = 30000): Promise<T> {
  const end = Date.now() + ms;
  for (;;) {
    const v = await get();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

async function open(name: string): Promise<vscode.TextEditor> {
  const doc = await vscode.workspace.openTextDocument(path.join(root(), name));
  return vscode.window.showTextDocument(doc);
}

/** Position just after the first match of `needle` (plus `delta` characters). */
function after(doc: vscode.TextDocument, needle: string, delta = 0): vscode.Position {
  const i = doc.getText().indexOf(needle);
  assert.ok(i >= 0, `fixture has no ${needle}`);
  return doc.positionAt(i + needle.length + delta);
}

async function labels(doc: vscode.TextDocument, pos: vscode.Position, trigger?: string): Promise<string[]> {
  const list = await vscode.commands.executeCommand<vscode.CompletionList>(
    "vscode.executeCompletionItemProvider", doc.uri, pos, trigger);
  return list.items.map((i) => (typeof i.label === "string" ? i.label : i.label.label));
}

async function hoverText(doc: vscode.TextDocument, pos: vscode.Position): Promise<string> {
  const hs = await vscode.commands.executeCommand<vscode.Hover[]>("vscode.executeHoverProvider", doc.uri, pos);
  return hs.flatMap((h) => h.contents.map((c) => (typeof c === "string" ? c : (c as vscode.MarkdownString).value))).join("\n");
}

type Case = [string, () => Promise<void>];

const trusted = process.env.PYXPO_E2E_TRUSTED !== "0";

async function items(doc: vscode.TextDocument, pos: vscode.Position): Promise<vscode.CompletionItem[]> {
  const list = await vscode.commands.executeCommand<vscode.CompletionList>(
    "vscode.executeCompletionItemProvider", doc.uri, pos);
  return list.items;
}

const label = (i: vscode.CompletionItem) => (typeof i.label === "string" ? i.label : i.label.label);

const cases: Case[] = [
  ["extension activates in a pyxpo project", async () => {
    await open("app.py");
    assert.equal(vscode.workspace.isTrusted, trusted, "workspace trust");
    const ext = vscode.extensions.getExtension("pyxpo.pyxpo")!;
    await waitFor("activation", () => ext.isActive);
    const cmds = await vscode.commands.getCommands(true);
    for (const c of ["pyxpo.run", "pyxpo.runAndroid", "pyxpo.runIos", "pyxpo.runDesktop", "pyxpo.prebuild",
      "pyxpo.doctor", "pyxpo.config", "pyxpo.create", "pyxpo.styleKeysCamel", "pyxpo.styleKeysSnake",
      "pyxpo.addImports"]) {
      assert.ok(cmds.includes(c), c);
    }
  }],

  ["style key completion in a sheet", async () => {
    const doc = (await open("app.py")).document;
    const ls = await labels(doc, after(doc, '"title": {', 0), "{");
    for (const k of ["justifyContent", "backgroundColor", "fontSize", "linearGradient"]) assert.ok(ls.includes(k), k);
    assert.ok(!ls.includes("justify_content"), "file is camelCase");
  }],

  ["enum value completion", async () => {
    const doc = (await open("app.py")).document;
    const ls = await labels(doc, after(doc, '"justifyContent": "', 0), '"');
    for (const v of ["center", "space-between", "flex-start"]) assert.ok(ls.includes(v), `${v} in ${ls.join(",")}`);
  }],

  ["prop completion in a component call", async () => {
    const doc = (await open("app.py")).document;
    const ls = await labels(doc, after(doc, "Pressable(", 0), "(");
    for (const p of ["style=", "onLongPress=", "disabled="]) assert.ok(ls.includes(p), ls.join(","));
    assert.ok(!ls.includes("onPress="), "present props are not offered again");
  }],

  ["snippets are offered", async () => {
    const doc = (await open("app.py")).document;
    const ls = await labels(doc, after(doc, "# snippets here\n", 0));
    for (const s of ["pxscreen", "pxstyles", "pxlist"]) assert.ok(ls.includes(s), s);
  }],

  ["hover shows docs for style keys and components", async () => {
    const doc = (await open("app.py")).document;
    assert.match(await hoverText(doc, after(doc, '"flexDirect', 0)), /flex_?[dD]irection/);
    assert.ok((await hoverText(doc, after(doc, "Pressable(Text", -10))).includes("Pressable"));
  }],

  ["colors: swatches and picker forms", async () => {
    const doc = (await open("app.py")).document;
    const cs = await vscode.commands.executeCommand<vscode.ColorInformation[]>(
      "vscode.executeDocumentColorProvider", doc.uri);
    const texts = cs.map((c) => doc.getText(c.range));
    for (const t of ["#ff0000", "rgba(0, 128, 255, 0.5)", "white", "#0f08"]) assert.ok(texts.includes(t), `${t} in ${texts}`);
    assert.ok(!texts.includes("blue"), "a name outside a color key is not a color");
    const red = cs.find((c) => doc.getText(c.range) === "#ff0000")!;
    assert.deepEqual([red.color.red, red.color.green, red.color.blue, red.color.alpha], [1, 0, 0, 1]);
    const ps = await vscode.commands.executeCommand<vscode.ColorPresentation[]>(
      "vscode.executeColorPresentationProvider", new vscode.Color(0, 1, 0, 1), { uri: doc.uri, range: red.range });
    assert.equal(ps[0].label, "#00ff00");
  }],

  ["diagnostics and the typo quick fix", async () => {
    const ed = await open("app.py");
    const doc = ed.document;
    const ds = await waitFor("diagnostics", () => {
      const d = vscode.languages.getDiagnostics(doc.uri).filter((x) => x.source === "pyxpo");
      return d.length >= 3 ? d : undefined;
    });
    const msgs = ds.map((d) => d.message).join("\n");
    assert.match(msgs, /backgroundColr.*did you mean 'backgroundColor'/);
    assert.match(msgs, /middle/);
    assert.match(msgs, /#12345/);
    const typo = ds.find((d) => /backgroundColr/.test(d.message))!;
    const acts = await vscode.commands.executeCommand<vscode.CodeAction[]>(
      "vscode.executeCodeActionProvider", doc.uri, typo.range, vscode.CodeActionKind.QuickFix.value);
    const fix = acts.find((a) => a.edit && /backgroundColor/.test(a.title));
    assert.ok(fix, acts.map((a) => a.title).join(","));
    assert.ok(await vscode.workspace.applyEdit(fix!.edit!));
    assert.ok(doc.getText().includes('"backgroundColor": "#ff0000"'));
    await waitFor("diagnostic gone", () =>
      !vscode.languages.getDiagnostics(doc.uri).some((d) => /backgroundColr/.test(d.message)) || undefined);
  }],

  ["convert style keys to snake_case and back", async () => {
    const ed = await open("app.py");
    await vscode.commands.executeCommand("pyxpo.styleKeysSnake");
    const t = ed.document.getText();
    assert.ok(t.includes('"justify_content"') && t.includes('"flex_direction"'), t);
    assert.ok(t.includes("onPress="), "props are not style keys");
    await vscode.commands.executeCommand("pyxpo.styleKeysCamel");
    assert.ok(ed.document.getText().includes('"justifyContent"'));
  }],

  ["auto-import: completing a pyxpo name adds its import", async () => {
    const ed = await open("screen.py");
    const doc = ed.document;
    const pos = after(doc, "return Vi", 0);
    const all = await items(doc, pos);
    const names = all.map(label);
    for (const n of ["View", "Text", "Pressable", "useState", "StyleSheet"]) assert.ok(names.includes(n), n);
    const view = all.find((i) => label(i) === "View")!;
    assert.ok(view.additionalTextEdits && view.additionalTextEdits.length, "View carries its import");
    // accept it the way the suggest widget does: main edit, then the additional ones
    await ed.edit((b) => {
      b.replace(view.range instanceof vscode.Range ? view.range : view.range!.replacing, "View");
      for (const e of view.additionalTextEdits!) b.replace(e.range, e.newText);
    });
    const t = doc.getText();
    assert.ok(t.startsWith("import os\nfrom pyxpo import View\n"), t);
    assert.ok(t.includes("    return View\n"), t);
    // names in strings, after a dot or on def lines get nothing from pyxpo
    await ed.edit((b) => b.insert(doc.positionAt(doc.getText().length), "x = os.Vi\n"));
    assert.ok(!(await items(doc, doc.positionAt(doc.getText().length - 1))).some((i) => label(i) === "View"));
  }],

  ["auto-import: quick fix and add missing imports", async () => {
    const ed = await open("screen.py");
    const doc = ed.document;
    const at = after(doc, "useState", -2);
    const acts = await vscode.commands.executeCommand<vscode.CodeAction[]>(
      "vscode.executeCodeActionProvider", doc.uri, new vscode.Range(at, at));
    const fix = acts.find((a) => a.title === "Import 'useState' from pyxpo");
    assert.ok(fix && fix.edit, acts.map((a) => a.title).join(","));
    assert.ok(await vscode.workspace.applyEdit(fix!.edit!));
    assert.ok(doc.getText().includes("from pyxpo import View, useState\n"), doc.getText());
    await ed.edit((b) => b.insert(doc.positionAt(doc.getText().length), 'y = Image(Text("a"), style=StyleSheet.create({}))\n'));
    await vscode.commands.executeCommand("pyxpo.addImports");
    assert.ok(doc.getText().includes("from pyxpo import Image, StyleSheet, Text, View, useState\n"), doc.getText());
    await vscode.commands.executeCommand("workbench.action.files.revert");
  }],

  ["no features in files that do not import pyxpo", async () => {
    const doc = (await open("plain.py")).document;
    const ls = await labels(doc, after(doc, "style={", 0), "{");
    assert.ok(!ls.includes("justifyContent"));
    const cs = await vscode.commands.executeCommand<vscode.ColorInformation[]>(
      "vscode.executeDocumentColorProvider", doc.uri);
    assert.equal(cs.length, 0);
  }],

  ["pyproject.toml: completion, hover, colors", async () => {
    const doc = (await open("pyproject.toml")).document;
    const ls = await labels(doc, after(doc, "# keys here\n", 0));
    for (const k of ["bundle_id", "modules", "orientation"]) assert.ok(ls.includes(k), `${k} in ${ls.join(",")}`);
    assert.ok(!ls.includes("name") && !ls.includes("scheme"), "present keys are not offered again");
    const ed = vscode.window.activeTextEditor!;
    await ed.edit((b) => b.insert(doc.positionAt(doc.getText().length), "\n[tool.pyxpo."));
    const hs = await labels(doc, doc.positionAt(doc.getText().length), ".");
    await vscode.commands.executeCommand("workbench.action.files.revert");
    assert.ok(hs.includes("tool.pyxpo.android") && hs.includes("tool.pyxpo.ios"), hs.join(","));
    assert.match(await hoverText(doc, after(doc, "\nschem", 0)), /scheme/);
    const cs = await vscode.commands.executeCommand<vscode.ColorInformation[]>(
      "vscode.executeDocumentColorProvider", doc.uri);
    assert.ok(cs.some((c) => doc.getText(c.range).includes("336699")));
  }],

  ["pyproject.toml: pyxpo config errors land on the key", async () => {
    const doc = (await open("pyproject.toml")).document;
    if (!trusted) {
      // validation runs the project's python: never in Restricted Mode
      await new Promise((r) => setTimeout(r, 3000));
      assert.equal(vscode.languages.getDiagnostics(doc.uri).length, 0);
      return;
    }
    const ds = await waitFor("config diagnostics", () => {
      const d = vscode.languages.getDiagnostics(doc.uri);
      return d.length ? d : undefined;
    }, 60000);
    const d = ds.find((x) => /nmae/.test(x.message));
    assert.ok(d, ds.map((x) => x.message).join("\n"));
    assert.equal(doc.lineAt(d!.range.start.line).text.trim().split(" ")[0], "nmae");
  }],

  ["run commands open the pyxpo terminal", async () => {
    await open("app.py");
    if (!trusted) {
      // asks for trust (a notification) and runs nothing
      void vscode.commands.executeCommand("pyxpo.doctor");
      await new Promise((r) => setTimeout(r, 1500));
      assert.ok(!vscode.window.terminals.some((x) => x.name === "pyxpo"), "no terminal in Restricted Mode");
      return;
    }
    await vscode.commands.executeCommand("pyxpo.doctor");
    const t = await waitFor("terminal", () => vscode.window.terminals.find((x) => x.name === "pyxpo"));
    assert.ok(t);
  }],
];

export async function run(): Promise<void> {
  const failed: string[] = [];
  for (const [name, fn] of cases) {
    try {
      await fn();
      console.log(`ok   ${name}`);
    } catch (e) {
      failed.push(name);
      console.log(`FAIL ${name}\n     ${(e as Error).message.split("\n").join("\n     ")}`);
    }
  }
  console.log(`${cases.length - failed.length}/${cases.length} passed (${trusted ? "trusted" : "Restricted Mode"})`);
  if (failed.length) throw new Error(`${failed.length} e2e case(s) failed`);
}
