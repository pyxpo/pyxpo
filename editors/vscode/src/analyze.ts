// What the extension knows about pyxpo code: style dicts, component calls, completions, checks and hovers.
// No vscode import here, so node:test can run it.

import { Entry, Node, Scan, Tok, nodeAt, scan, tokenAt, tokenBefore, unquote } from "./pyscan";
import { looksLikeColor, parseColor } from "./colors";

export interface StyleKeyInfo {
  kind: "enum" | "color" | "gradient" | "transform" | "bool" | "string" | "number";
  doc: string;
  values?: string[];
}

export interface ComponentInfo {
  doc: string;
  props: string[];
}

export interface Data {
  pyxpo: string;
  style: { keys: Record<string, StyleKeyInfo>; unsupported: string[] };
  named_colors: Record<string, string>;
  components: Record<string, ComponentInfo>;
  /** `pyxpo.__all__`, for auto-import. */
  exports: Record<string, { kind: "component" | "class" | "hook" | "function"; doc: string }>;
  config: any;
}

export type Naming = "camelCase" | "snake_case";

// RN spellings that do not follow the mechanical camelCase rule (pyxpo._keys)
const SNAKE_OVERRIDES: Record<string, string> = { testID: "test_id", nativeID: "native_id" };
const CAMEL_OVERRIDES: Record<string, string> = { test_id: "testID", native_id: "nativeID" };

/** `fontSize` -> `font_size`, like pyxpo._keys.to_snake. */
export function toSnake(name: string): string {
  if (name === name.toLowerCase()) return name;
  if (SNAKE_OVERRIDES[name]) return SNAKE_OVERRIDES[name];
  return name.replace(/([a-z0-9])(?=[A-Z])|([A-Z])(?=[A-Z][a-z])/g, "$1$2_").toLowerCase();
}

export function toCamel(name: string): string {
  if (CAMEL_OVERRIDES[name]) return CAMEL_OVERRIDES[name];
  return name.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
}

export function spell(snake: string, naming: Naming): string {
  return naming === "camelCase" ? toCamel(snake) : snake;
}

/** Edit distance, for "did you mean". */
export function levenshtein(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cur = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
  }
  return row[b.length];
}

export function closest(word: string, options: Iterable<string>, max = 2): string | null {
  let best: string | null = null;
  let bestD = max + 1;
  for (const o of options) {
    const d = levenshtein(word, o);
    if (d < bestD) { best = o; bestD = d; }
  }
  return best;
}

/** True when the file uses pyxpo (imports it); other Python files get no pyxpo features. */
export function isPyxpoFile(text: string): boolean {
  return /^\s*(from\s+pyxpo\b|import\s+pyxpo\b|from\s+pyxpo_\w+|import\s+pyxpo_\w+)/m.test(text);
}

const STYLE_OWNER = /^style$|_style$|Style$/;
const SHEET_OWNER = /^styles$|_styles$|Styles$/;

function lastSegment(callee: string | null): string {
  if (!callee) return "";
  const i = callee.lastIndexOf(".");
  return i < 0 ? callee : callee.slice(i + 1);
}

function isCreate(n: Node | null): boolean {
  return !!n && n.open === "(" && !!n.callee && /(^|\.)StyleSheet\.create$/.test(n.callee);
}

/** A bracket that holds key/values: `{...}` or `dict(...)`. */
export function isMapping(n: Node): boolean {
  return n.open === "{" || (n.open === "(" && n.callee === "dict");
}

/** A mapping of style names to styles: the dict given to StyleSheet.create, or `styles = {...}`. */
export function isSheet(n: Node): boolean {
  if (!isMapping(n)) return false;
  if (n.parent && isCreate(n.parent) && n.parent.args.includes(n)) return true;
  return !n.parent && !!n.owner && SHEET_OWNER.test(n.owner);
}

/** A style mapping by its place in the code. Diagnostics run only on these. */
export function isStyleDict(n: Node): boolean {
  if (!isMapping(n)) return false;
  if (n.owner && STYLE_OWNER.test(n.owner) && !(n.parent && isSheet(n.parent))) return true;
  const p = n.parent;
  if (!p) return false;
  if (p.open === "[" && p.owner && STYLE_OWNER.test(p.owner)) return true; // style=[styles.a, {...}]
  if (isCreate(p) && !p.args.includes(n)) return true; // StyleSheet.create(card={...})
  if (isSheet(p) && !p.args.includes(n)) return true; // {"card": {...}}
  return false;
}

/** Looser test for completions: also a mapping that already has style keys or is named like a style. */
export function looksLikeStyleDict(n: Node, data: Data): boolean {
  if (!isMapping(n)) return false;
  if (isStyleDict(n)) return true;
  if (isSheet(n)) return false;
  if (n.entries.some((e) => data.style.keys[toSnake(e.key)])) return true;
  return !!n.owner && /style/i.test(n.owner) && !SHEET_OWNER.test(n.owner);
}

/** The component a call node creates, by the last segment of its callee (`pyxpo.View(` too). */
export function componentOf(n: Node | null, data: Data): string | null {
  if (!n || n.open !== "(") return null;
  const name = lastSegment(n.callee);
  return data.components[name] ? name : null;
}

/** The naming a file already uses for style keys; camelCase (the templates' spelling) when it has none. */
export function detectNaming(s: Scan, data: Data): Naming {
  let camel = 0, snake = 0;
  for (const n of s.nodes) {
    if (!isStyleDict(n)) continue;
    for (const e of n.entries) {
      if (/[A-Z]/.test(e.key) && data.style.keys[toSnake(e.key)]) camel++;
      else if (e.key.includes("_") && data.style.keys[e.key]) snake++;
    }
  }
  return snake > camel ? "snake_case" : "camelCase";
}

/** Props are Python keywords: snake_case unless the file already passes camelCase props. */
export function detectPropNaming(s: Scan, data: Data): Naming {
  let camel = 0, snake = 0;
  for (const n of s.nodes) {
    const c = componentOf(n, data);
    if (!c) continue;
    for (const e of n.entries) {
      if (/[A-Z]/.test(e.key)) camel++;
      else if (e.key.includes("_")) snake++;
    }
  }
  return camel > snake ? "camelCase" : "snake_case";
}

// ---- completion -------------------------------------------------------------------------------------------

export type Completion =
  | { kind: "styleKey"; form: "dict" | "kw" | "str"; replaceStart: number; replaceEnd: number; present: string[] }
  | { kind: "prop"; component: string; replaceStart: number; replaceEnd: number; present: string[] }
  | { kind: "value"; key: string; quoted: boolean; replaceStart: number; replaceEnd: number };

function itemStart(s: Scan, node: Node, beforeIdx: number): boolean {
  if (beforeIdx < 0) return false;
  const p = s.toks[beforeIdx];
  return p.start === node.start || p.text === ",";
}

/** The key an entry value at token index `idx` belongs to: `"key": <idx>` or `key=<idx>`. */
function keyBefore(s: Scan, idx: number): string | null {
  const sep = s.toks[idx - 1];
  const key = s.toks[idx - 2];
  if (!sep || !key) return null;
  if (sep.text === ":" && key.kind === "str") return unquote(key);
  if (sep.text === "=" && key.kind === "name") return key.text;
  return null;
}

export function completionAt(text: string, offset: number, data: Data, s: Scan = scan(text)): Completion | null {
  const ti = tokenAt(s, offset);
  const t: Tok | undefined = ti >= 0 ? s.toks[ti] : undefined;
  if (t && t.kind === "str" && offset >= t.valueStart! && offset <= t.valueEnd!) {
    const node = nodeAt(s, offset);
    if (!node) return null;
    if (node.open === "{" && itemStart(s, node, ti - 1)) {
      if (!looksLikeStyleDict(node, data)) return null;
      return { kind: "styleKey", form: "str", replaceStart: t.valueStart!, replaceEnd: t.valueEnd!,
        present: node.entries.filter((e) => e.keyStart !== t.valueStart).map((e) => toSnake(e.key)) };
    }
    const key = keyBefore(s, ti);
    if (key && isMapping(node) && looksLikeStyleDict(node, data)) {
      return { kind: "value", key: toSnake(key), quoted: true, replaceStart: t.valueStart!, replaceEnd: t.valueEnd! };
    }
    return null;
  }
  if (t && t.kind === "str") return null; // on a quote, or in a prefix
  // the word being typed, if any
  let wordStart = offset;
  if (t && t.kind === "name" && offset > t.start) wordStart = t.start;
  const bi = tokenBefore(s, wordStart);
  const node = nodeAt(s, wordStart);
  if (!node) return null;
  const prev = bi >= 0 ? s.toks[bi] : undefined;
  if (prev && (prev.text === ":" || prev.text === "=") && isMapping(node) && looksLikeStyleDict(node, data)) {
    const key = keyBefore(s, bi + 1);
    if (key) return { kind: "value", key: toSnake(key), quoted: false, replaceStart: wordStart, replaceEnd: offset };
  }
  if (!itemStart(s, node, bi)) return null;
  const present = node.entries.map((e) => toSnake(e.key));
  if (node.open === "{" && looksLikeStyleDict(node, data)) {
    return { kind: "styleKey", form: "dict", replaceStart: wordStart, replaceEnd: offset, present };
  }
  if (node.open === "(" && node.callee === "dict" && looksLikeStyleDict(node, data)) {
    return { kind: "styleKey", form: "kw", replaceStart: wordStart, replaceEnd: offset, present };
  }
  const comp = componentOf(node, data);
  if (comp) return { kind: "prop", component: comp, replaceStart: wordStart, replaceEnd: offset, present };
  return null;
}

/** Values to offer for a style key (snake_case): enum words, named colors, booleans. */
export function valuesFor(key: string, data: Data): { values: string[]; quote: boolean } {
  const info = data.style.keys[key];
  if (!info) return { values: [], quote: true };
  if (info.kind === "enum") return { values: info.values || [], quote: true };
  if (info.kind === "color") return { values: Object.keys(data.named_colors), quote: true };
  if (info.kind === "bool") return { values: ["True", "False"], quote: false };
  return { values: [], quote: true };
}

// ---- diagnostics ------------------------------------------------------------------------------------------

export type Severity = "error" | "warning" | "info";

export interface Problem {
  start: number;
  end: number;
  severity: Severity;
  message: string;
  code: "unknown-key" | "unsupported-key" | "bad-value" | "bad-color";
  /** For unknown keys: the suggested key, spelled like the original. */
  fix?: string;
}

function normEnum(v: string): string {
  return v.toLowerCase().replace(/-/g, "_");
}

/** Enum words native accepts besides the offered RN spellings (pyxpo_layout.c norm_eq). */
const ENUM_EXTRA: Record<string, string[]> = {
  justify_content: ["start", "end"],
  align_items: ["start", "end", "auto", "space_between", "space_around", "space_evenly"],
  align_self: ["start", "end", "space_between", "space_around", "space_evenly"],
  align_content: ["start", "end", "auto", "baseline"],
  position: ["static"],
  text_align: ["justify", "start", "end"],
};

function enumOk(key: string, value: string, info: StyleKeyInfo): boolean {
  const v = normEnum(value.trim());
  const ok = (info.values || []).concat(ENUM_EXTRA[key] || []).map(normEnum);
  if (key === "text_decoration") {
    return v.split(/\s+/).every((w) => ok.includes(w) || ["underline", "line_through", "none"].includes(w));
  }
  return ok.includes(v);
}

export function diagnose(text: string, data: Data, s: Scan = scan(text)): Problem[] {
  const out: Problem[] = [];
  const known = Object.keys(data.style.keys);
  const unsupported = new Set(data.style.unsupported);
  for (const n of s.nodes) {
    if (!isStyleDict(n)) continue;
    for (const e of n.entries) {
      checkEntry(e, data, known, unsupported, out);
    }
  }
  return out;
}

function checkEntry(e: Entry, data: Data, known: string[], unsupported: Set<string>, out: Problem[]): void {
  const key = toSnake(e.key);
  const info = data.style.keys[key];
  if (!info) {
    if (unsupported.has(key)) {
      out.push({ start: e.keyStart, end: e.keyEnd, severity: "info", code: "unsupported-key",
        message: `pyxpo ignores '${e.key}' (React Native style not supported on native yet).` });
      return;
    }
    const hit = closest(key, known);
    const camel = /[A-Z]/.test(e.key);
    const fix = hit ? (camel ? toCamel(hit) : hit) : undefined;
    out.push({ start: e.keyStart, end: e.keyEnd, severity: "warning", code: "unknown-key", fix,
      message: `Unknown style key '${e.key}'` + (fix ? ` (did you mean '${fix}'?)` : ".") });
    return;
  }
  const v = e.value;
  if (!v || v.kind !== "str" || v.open || /^[fF]|^[rRbB][fF]/.test(v.text)) return;
  const value = unquote(v);
  if (info.kind === "enum" && !enumOk(key, value, info) && !(key === "font_weight" && /^\d00$/.test(value))) {
    out.push({ start: v.valueStart!, end: v.valueEnd!, severity: "warning", code: "bad-value",
      message: `'${value}' is not a value for ${e.key}: ${(info.values || []).join(", ")}.` });
  } else if (info.kind === "color" && !parseColor(value, data.named_colors)) {
    out.push({ start: v.valueStart!, end: v.valueEnd!, severity: "warning", code: "bad-color",
      message: `'${value}' is not a color: use #rgb, #rrggbb, #rrggbbaa, rgb(), rgba() or a name (` +
        Object.keys(data.named_colors).slice(0, 6).join(", ") + ", ...)." });
  }
}

// ---- colors -----------------------------------------------------------------------------------------------

export interface ColorSpot {
  start: number;
  end: number;
  value: string;
}

/**
 * Color strings to show a swatch for: hex and rgb() strings anywhere in the file, and names when they are the
 * value of a color key (`"color": "red"`) so ordinary words never get a swatch.
 */
export function colorSpots(text: string, data: Data, s: Scan = scan(text)): ColorSpot[] {
  const named = new Set<number>();
  for (const n of s.nodes) {
    if (!isMapping(n)) continue;
    for (const e of n.entries) {
      const info = data.style.keys[toSnake(e.key)];
      if (info && info.kind === "color" && e.value && e.value.kind === "str") named.add(e.value.start);
    }
  }
  const out: ColorSpot[] = [];
  for (const t of s.toks) {
    if (t.kind !== "str" || t.open || /^[a-zA-Z]*[fF]/.test(t.text)) continue;
    const value = unquote(t);
    const literal = looksLikeColor(value) && /^\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))\s*$/.test(value);
    if (!literal && !(named.has(t.start) && data.named_colors[value.trim().toLowerCase()])) continue;
    if (!parseColor(value, data.named_colors)) continue;
    out.push({ start: t.valueStart!, end: t.valueEnd!, value });
  }
  return out;
}

// ---- hover ------------------------------------------------------------------------------------------------

export interface HoverInfo {
  start: number;
  end: number;
  markdown: string;
}

export function styleKeyMarkdown(key: string, info: StyleKeyInfo): string {
  let md = `**${toCamel(key)}** · \`${key}\` — ${info.doc}`;
  if (info.values && info.values.length) md += `\n\nValues: ${info.values.map((v) => "`" + v + "`").join(", ")}`;
  return md;
}

export function componentMarkdown(name: string, c: ComponentInfo): string {
  let md = `**${name}** (pyxpo)`;
  if (c.doc) md += `\n\n${c.doc}`;
  if (c.props.length) md += `\n\nProps: ${c.props.map((p) => "`" + p + "`").join(", ")}`;
  return md;
}

export function hoverAt(text: string, offset: number, data: Data, s: Scan = scan(text)): HoverInfo | null {
  const ti = tokenAt(s, offset);
  if (ti < 0) return null;
  const t = s.toks[ti];
  if (t.kind === "str") {
    const node = nodeAt(s, offset);
    if (!node) return null;
    const e = node.entries.find((x) => x.keyStart === t.valueStart && x.form === "dict");
    if (!e || !looksLikeStyleDict(node, data)) return null;
    const info = data.style.keys[toSnake(e.key)];
    return info ? { start: t.valueStart!, end: t.valueEnd!, markdown: styleKeyMarkdown(toSnake(e.key), info) } : null;
  }
  if (t.kind !== "name") return null;
  const next = s.toks[ti + 1];
  if (next && next.text === "(" && data.components[t.text]) {
    const node = s.nodes.find((n) => n.start === next.start);
    if (node && componentOf(node, data) === t.text) {
      return { start: t.start, end: t.end, markdown: componentMarkdown(t.text, data.components[t.text]) };
    }
  }
  if (next && next.text === "=") {
    const node = nodeAt(s, offset);
    if (node && node.callee === "dict" && looksLikeStyleDict(node, data)) {
      const info = data.style.keys[toSnake(t.text)];
      if (info) return { start: t.start, end: t.end, markdown: styleKeyMarkdown(toSnake(t.text), info) };
    }
    const comp = componentOf(node, data);
    if (comp && node!.entries.some((e) => e.keyStart === t.start)) {
      return { start: t.start, end: t.end, markdown: `**${t.text}** — prop of \`${comp}\`` };
    }
  }
  return null;
}

// ---- style key conversion ---------------------------------------------------------------------------------

export interface Edit {
  start: number;
  end: number;
  text: string;
}

/** Renames the known style keys in style dicts to one naming. */
export function convertStyleKeys(text: string, naming: Naming, data: Data, s: Scan = scan(text)): Edit[] {
  const out: Edit[] = [];
  for (const n of s.nodes) {
    if (!isStyleDict(n)) continue;
    for (const e of n.entries) {
      const snake = toSnake(e.key);
      if (!data.style.keys[snake]) continue;
      const want = spell(snake, naming);
      if (want !== e.key) out.push({ start: e.keyStart, end: e.keyEnd, text: want });
    }
  }
  return out;
}
