// `[tool.pyxpo]` in pyproject.toml: where the cursor is, completions and hovers from the config JSON schema, and
// mapping `pyxpo config` errors back to lines. Line based on purpose: pyproject files are small and regular.

import { toSnake } from "./analyze";

export interface Schema {
  type?: string | string[];
  description?: string;
  enum?: unknown[];
  pattern?: string;
  minimum?: number;
  maximum?: number;
  properties?: Record<string, Schema>;
  items?: Schema;
  additionalProperties?: boolean | Schema;
  anyOf?: Schema[];
  oneOf?: Schema[];
}

const HEADER = /^\s*(\[\[?)\s*([^\]]+?)\s*\]\]?\s*(#.*)?$/;
const KEY_LINE = /^(\s*)((?:[A-Za-z0-9_-]+|"[^"]*"|'[^']*')(?:\s*\.\s*(?:[A-Za-z0-9_-]+|"[^"]*"|'[^']*'))*)\s*=/;

export function splitKey(key: string): string[] {
  const out: string[] = [];
  const re = /\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_-]+))\s*(?:\.|$)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(key)) && m[0].length) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

/** The table path in effect on a line (`["tool", "pyxpo", "android"]`), or [] before any header. */
export function tableAt(lines: string[], line: number): string[] {
  for (let i = line; i >= 0; i--) {
    const m = HEADER.exec(lines[i]);
    if (m && !KEY_LINE.test(lines[i])) return splitKey(m[2]);
  }
  return [];
}

/** True when the path is `tool.pyxpo` or below it. */
export function inPyxpo(path: string[]): boolean {
  return path.length >= 2 && path[0] === "tool" && path[1] === "pyxpo";
}

function unwrap(s: Schema | undefined): Schema | undefined {
  if (!s) return s;
  const alt = s.anyOf || s.oneOf;
  if (alt) return alt.find((a) => a.properties) || alt.find((a) => a.items) || alt[0];
  return s;
}

/** The schema of a `[tool.pyxpo ...]` path below the root (`["android", "adaptive_icon"]`). camelCase keys too. */
export function schemaAt(root: Schema, path: string[]): Schema | undefined {
  let s: Schema | undefined = root;
  for (const seg of path) {
    s = unwrap(s);
    if (!s) return undefined;
    if (s.items && !s.properties) s = unwrap(s.items); // [[tool.pyxpo.x]] array of tables
    const props: Record<string, Schema> | undefined = s?.properties;
    if (!props) return undefined;
    s = props[seg] ?? props[toSnake(seg)];
  }
  return s;
}

export function isTable(s: Schema | undefined): boolean {
  const u = unwrap(s);
  return !!u && (!!u.properties || (!!u.items && !!unwrap(u.items)?.properties));
}

export function typeLabel(s: Schema): string {
  if (s.enum) return s.enum.map((v) => JSON.stringify(v)).join(" | ");
  const t = Array.isArray(s.type) ? s.type.join(" | ") : s.type || (s.anyOf || s.oneOf ? "mixed" : "any");
  if (t === "array" && s.items) return `array of ${typeLabel(s.items)}`;
  return t;
}

export function schemaMarkdown(name: string, s: Schema): string {
  let md = `**${name}**: \`${typeLabel(s)}\``;
  if (s.description) md += `\n\n${s.description}`;
  if (s.minimum !== undefined) md += `\n\nMinimum: ${s.minimum}`;
  return md;
}

export type TomlCompletion =
  | { kind: "key"; schema: Schema; present: string[]; replaceStart: number }
  | { kind: "header"; options: string[]; replaceStart: number }
  | { kind: "value"; schema: Schema; quoted: boolean; replaceStart: number };

/** What to complete at `line`/`col` (0-based), for the `[tool.pyxpo]` schema `root`. Positions are columns. */
export function tomlCompletionAt(lines: string[], line: number, col: number, root: Schema): TomlCompletion | null {
  const before = lines[line].slice(0, col);
  const hm = /^\s*\[\[?\s*([A-Za-z0-9_.-]*)$/.exec(before);
  if (hm) {
    const parts = hm[1].split(".");
    parts.pop(); // the part being typed
    const options: string[] = [];
    if (parts.join(".") === "tool") options.push("tool.pyxpo");
    if (parts.length >= 2 && parts[0] === "tool" && parts[1] === "pyxpo") {
      const s = unwrap(schemaAt(root, parts.slice(2)));
      for (const [k, v] of Object.entries(s?.properties || {})) {
        if (isTable(v)) options.push([...parts, k].join("."));
      }
    } else if (parts.length === 0) options.push("tool.pyxpo");
    return { kind: "header", options, replaceStart: col - hm[1].length };
  }
  const table = tableAt(lines, line);
  if (!inPyxpo(table)) return null;
  const km = /^\s*([A-Za-z0-9_-]*)$/.exec(before);
  if (km) {
    const s = unwrap(schemaAt(root, table.slice(2)));
    if (!s) return null;
    const own = s.properties ? s : unwrap(s.items);
    if (!own || !own.properties) return null;
    return { kind: "key", schema: own, present: keysInTable(lines, line), replaceStart: col - km[1].length };
  }
  const vm = /^\s*([A-Za-z0-9_.-]+)\s*=\s*("?)([^"]*)$/.exec(before);
  if (vm) {
    const s = unwrap(schemaAt(root, [...table.slice(2), ...splitKey(vm[1])]));
    if (!s) return null;
    return { kind: "value", schema: s, quoted: vm[2] === '"', replaceStart: col - vm[3].length };
  }
  return null;
}

/** Keys already set in the table that holds `line`. */
export function keysInTable(lines: string[], line: number): string[] {
  let start = line;
  while (start > 0 && !HEADER.test(lines[start])) start--;
  const out: string[] = [];
  for (let i = start + (HEADER.test(lines[start]) ? 1 : 0); i < lines.length; i++) {
    if (i > line && HEADER.test(lines[i]) && !KEY_LINE.test(lines[i])) break;
    if (i === line) continue;
    const m = KEY_LINE.exec(lines[i]);
    if (m) out.push(toSnake(splitKey(m[2])[0]));
  }
  return out;
}

export interface KeySpot {
  /** Full path, snake_case (`["tool", "pyxpo", "splash", "resize_mode"]`). */
  path: string[];
  line: number;
  start: number;
  end: number;
}

/** Every key and table header with its place: header names, `a.b = ` keys and keys of one-line inline tables. */
export function keySpots(lines: string[]): KeySpot[] {
  const out: KeySpot[] = [];
  let table: string[] = [];
  let depth = 0; // open [ inside a multi-line value: such lines hold no keys of the table
  for (let i = 0; i < lines.length; i++) {
    const text = lines[i];
    const h = depth === 0 ? HEADER.exec(text) : null;
    if (h && !KEY_LINE.test(text)) {
      table = splitKey(h[2]).map(toSnake);
      const s = text.indexOf(h[2]);
      out.push({ path: table, line: i, start: s, end: s + h[2].length });
      continue;
    }
    const m = depth === 0 ? KEY_LINE.exec(text) : null;
    if (m) {
      const parts = splitKey(m[2]).map(toSnake);
      const s = m[1].length;
      out.push({ path: [...table, ...parts], line: i, start: s, end: s + m[2].trimEnd().length });
      const rest = text.slice(m[0].length);
      const inline = /\{([^}]*)\}/.exec(rest);
      if (inline) {
        const base = m[0].length + inline.index + 1;
        const ik = /([A-Za-z0-9_-]+)\s*=/g;
        let k: RegExpExecArray | null;
        while ((k = ik.exec(inline[1]))) {
          out.push({ path: [...table, ...parts, toSnake(k[1])], line: i, start: base + k.index,
            end: base + k.index + k[1].length });
        }
      }
    }
    depth += bracketDelta(text);
    if (depth < 0) depth = 0;
  }
  return out;
}

function bracketDelta(text: string): number {
  let d = 0, q = "";
  for (const c of text) {
    if (q) { if (c === q) q = ""; continue; }
    if (c === "#") break;
    if (c === '"' || c === "'") q = c;
    else if (c === "[" || c === "{") d++;
    else if (c === "]" || c === "}") d--;
  }
  return d;
}

export interface ConfigProblem {
  line: number;
  start: number;
  end: number;
  message: string;
}

const ERR = /^\s*\[tool\.pyxpo\](?:\s+([^:]+?))?:\s*(.+)$/;

/** Maps `pyxpo config` error output to places in pyproject.toml. Lines it cannot read are skipped. */
export function mapConfigErrors(output: string, lines: string[]): ConfigProblem[] {
  const spots = keySpots(lines);
  const out: ConfigProblem[] = [];
  const root = spots.find((s) => s.path.length === 2 && s.path[0] === "tool" && s.path[1] === "pyxpo");
  for (const raw of output.split(/\r?\n/)) {
    const m = ERR.exec(raw);
    if (!m) continue;
    const rel = (m[1] || "").replace(/\[\d+\]/g, "").split(".").filter((x) => x);
    const unknown = /^unknown key '([^']+)'/.exec(m[2]);
    const path = ["tool", "pyxpo", ...rel, ...(unknown ? [unknown[1]] : [])];
    let best: KeySpot | undefined;
    for (const s of spots) {
      if (s.path.length > path.length) continue;
      if (!s.path.every((p, i) => p === toSnake(path[i]) || p === path[i])) continue;
      if (!best || s.path.length > best.path.length) best = s;
    }
    const at = best || root;
    const message = m[1] ? `${m[1]}: ${m[2]}` : m[2];
    out.push(at ? { line: at.line, start: at.start, end: at.end, message }
      : { line: 0, start: 0, end: (lines[0] || "").length, message });
  }
  return out;
}

/** Hex color strings in `[tool.pyxpo...]` tables: `{line, start, end, value}` with start/end inside the quotes. */
export function tomlColorSpots(lines: string[]): { line: number; start: number; end: number; value: string }[] {
  const out: { line: number; start: number; end: number; value: string }[] = [];
  let table: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const h = HEADER.exec(lines[i]);
    if (h && !KEY_LINE.test(lines[i])) { table = splitKey(h[2]); continue; }
    if (!inPyxpo(table)) continue;
    const re = /(["'])(#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}))\1/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(lines[i]))) out.push({ line: i, start: m.index + 1, end: m.index + 1 + m[2].length, value: m[2] });
  }
  return out;
}

/** The `[tool.pyxpo]` key under the cursor, for hovers: its full path below tool.pyxpo and its column range. */
export function tomlKeyAt(lines: string[], line: number, col: number): { path: string[]; start: number; end: number } | null {
  const spots = keySpots(lines).filter((s) => s.line === line && s.start <= col && col <= s.end && inPyxpo(s.path));
  if (!spots.length) return null;
  const s = spots[spots.length - 1];
  return { path: s.path.slice(2), start: s.start, end: s.end };
}
