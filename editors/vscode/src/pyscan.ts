// A small Python scanner: tokens, bracket nodes and their key/value entries. It knows enough Python to find style
// dicts and component calls; it is not a parser and never throws on broken code.

export type TokKind = "name" | "str" | "num" | "op";

export interface Tok {
  kind: TokKind;
  start: number;
  end: number;
  text: string;
  /** For "str": the text between the quotes (escapes kept as written) and where it starts and ends. */
  value?: string;
  valueStart?: number;
  valueEnd?: number;
  /** For "str": the string was not closed before the end of the line (or file, for triple quotes). */
  open?: boolean;
}

export interface Entry {
  key: string;
  keyStart: number;
  keyEnd: number;
  /** "dict" for `"key": v`, "kw" for `key=v`. */
  form: "dict" | "kw";
  value?: Tok;
  node?: Node;
}

export interface Node {
  open: "(" | "[" | "{";
  start: number;
  /** Offset of the closing bracket, or -1 when it is not closed. */
  end: number;
  /** For "(": the dotted name being called, as written (`StyleSheet.create`). */
  callee: string | null;
  /** The key, keyword or variable this bracket is the value of. */
  owner: string | null;
  parent: Node | null;
  entries: Entry[];
  /** Positional (not key/keyword) child nodes. */
  args: Node[];
}

const NAME_START = /[A-Za-z_\u00c0-\uffff]/;
const NAME_PART = /[A-Za-z0-9_\u00c0-\uffff]/;
const TWO_CHAR_OPS = new Set(["==", "!=", "<=", ">=", "->", ":=", "**", "//", "<<", ">>", "+=", "-=", "*=", "/="]);

export function tokenize(text: string): Tok[] {
  const toks: Tok[] = [];
  const n = text.length;
  let i = 0;
  while (i < n) {
    const c = text[i];
    if (c === " " || c === "\t" || c === "\r" || c === "\n" || c === "\f" || c === "\\") { i++; continue; }
    if (c === "#") {
      while (i < n && text[i] !== "\n") i++;
      continue;
    }
    // string, with an optional prefix such as r, b, f, rb
    let j = i;
    while (j < n && j - i < 2 && /[rRbBuUfF]/.test(text[j])) j++;
    if (j < n && (text[j] === '"' || text[j] === "'")) {
      const prefix = text.slice(i, j).toLowerCase();
      const raw = prefix.includes("r");
      const q = text[j];
      const triple = text.startsWith(q + q + q, j);
      const delim = triple ? q + q + q : q;
      const vs = j + delim.length;
      let k = vs;
      let closed = false;
      while (k < n) {
        const ch = text[k];
        if (ch === "\\" && !raw) { k += 2; continue; }
        if (ch === "\\" && raw) { k += 2; continue; } // a raw string still cannot end with a lone backslash
        if (!triple && ch === "\n") break;
        if (text.startsWith(delim, k)) { closed = true; break; }
        k++;
      }
      k = Math.min(k, n);
      const end = closed ? k + delim.length : k;
      toks.push({ kind: "str", start: i, end, text: text.slice(i, end), value: text.slice(vs, k),
        valueStart: vs, valueEnd: k, open: !closed });
      i = end;
      continue;
    }
    if (NAME_START.test(c)) {
      j = i + 1;
      while (j < n && NAME_PART.test(text[j])) j++;
      toks.push({ kind: "name", start: i, end: j, text: text.slice(i, j) });
      i = j;
      continue;
    }
    if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(text[i + 1] || ""))) {
      j = i + 1;
      while (j < n && /[0-9A-Za-z_.]/.test(text[j])) j++;
      toks.push({ kind: "num", start: i, end: j, text: text.slice(i, j) });
      i = j;
      continue;
    }
    const two = text.slice(i, i + 2);
    const len = TWO_CHAR_OPS.has(two) ? 2 : 1;
    toks.push({ kind: "op", start: i, end: i + len, text: text.slice(i, i + len) });
    i += len;
  }
  return toks;
}

export interface Scan {
  toks: Tok[];
  nodes: Node[];
}

function calleeBefore(toks: Tok[], i: number): string | null {
  // tokens before index i: name ( . name )*
  let k = i - 1;
  if (k < 0 || toks[k].kind !== "name") return null;
  const parts = [toks[k].text];
  k--;
  while (k >= 1 && toks[k].text === "." && toks[k - 1].kind === "name") {
    parts.unshift(toks[k - 1].text);
    k -= 2;
  }
  return parts.join(".");
}

const KEYWORDS = new Set(["if", "elif", "while", "for", "in", "not", "and", "or", "return", "yield", "lambda",
  "else", "is", "assert", "del", "with", "as", "print", "await"]);

/** Scans the whole text. `pending` keys wait for their value: the next token or bracket after `:` / `=`. */
export function scan(text: string): Scan {
  const toks = tokenize(text);
  const nodes: Node[] = [];
  const stack: Node[] = [];
  let pending: Entry | null = null; // entry whose value starts at the next token
  let pendingNode: Node | null = null; // the node that pending belongs to
  let assign: string | null = null; // `name = ` at the top level

  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    const top = stack.length ? stack[stack.length - 1] : null;
    if (t.kind === "op" && (t.text === "(" || t.text === "[" || t.text === "{")) {
      const prev = toks[i - 1];
      let callee: string | null = null;
      if (t.text === "(" && prev && prev.kind === "name" && !KEYWORDS.has(prev.text)) callee = calleeBefore(toks, i);
      if (t.text === "(" && prev && (prev.text === ")" || prev.text === "]")) callee = "?";
      const node: Node = { open: t.text, start: t.start, end: -1, callee, owner: null, parent: top, entries: [], args: [] };
      if (pending && pendingNode === top) {
        node.owner = pending.key;
        pending.node = node;
        pending = null;
      } else if (!top && assign) {
        node.owner = assign;
      } else if (top && (!prev || prev.text === "(" || prev.text === "," || prev.text === "[" || prev.text === "{" ||
                         prev.text === "*" || prev.text === "**")) {
        top.args.push(node);
      }
      // a call's own node: `View(` is the bracket; the callee is not a value of the pending key in that case
      if (callee && callee !== "?" && pending === null && top && top.entries.length) {
        const last = top.entries[top.entries.length - 1];
        if (!last.node && !last.value && toks[i - 2] && (toks[i - 2].text === ":" || toks[i - 2].text === "=")) {
          last.node = node;
          node.owner = last.key;
        }
      }
      nodes.push(node);
      stack.push(node);
      assign = null;
      continue;
    }
    if (t.kind === "op" && (t.text === ")" || t.text === "]" || t.text === "}")) {
      // pop to the matching bracket; tolerate broken code
      const want = t.text === ")" ? "(" : t.text === "]" ? "[" : "{";
      let k = stack.length - 1;
      while (k >= 0 && stack[k].open !== want) k--;
      if (k >= 0) {
        stack[k].end = t.start;
        stack.length = k;
      }
      pending = null;
      continue;
    }
    if (!top) {
      // `name = ` at module level: the owner of a bracket that follows
      if (t.kind === "name" && toks[i + 1] && toks[i + 1].text === "=" && (!toks[i - 1] || toks[i - 1].start <
          lineStart(text, t.start))) {
        assign = t.text;
        i++;
        continue;
      }
      // keep it across a dotted callee (`styles = StyleSheet.create(`), drop it on anything else
      if (t.kind !== "name" && t.text !== ".") assign = null;
      continue;
    }
    const prev = toks[i - 1];
    const atItemStart = prev && (prev.start === top.start || prev.text === ",");
    if (pending && pendingNode === top) {
      if (t.kind === "str" || t.kind === "num" || t.kind === "name") {
        const after = toks[i + 1];
        if (!after || after.text === "," || after.text === ")" || after.text === "}" || after.text === "]") {
          pending.value = t;
        }
      }
      pending = null;
    }
    if (t.text === ",") { pending = null; continue; }
    if (atItemStart && top.open === "{" && t.kind === "str" && toks[i + 1] && toks[i + 1].text === ":") {
      const e: Entry = { key: unquote(t), keyStart: t.valueStart!, keyEnd: t.valueEnd!, form: "dict" };
      top.entries.push(e);
      pending = e; pendingNode = top;
      i++;
      continue;
    }
    if (atItemStart && top.open === "(" && t.kind === "name" && toks[i + 1] && toks[i + 1].text === "=") {
      const e: Entry = { key: t.text, keyStart: t.start, keyEnd: t.end, form: "kw" };
      top.entries.push(e);
      pending = e; pendingNode = top;
      i++;
      continue;
    }
  }
  return { toks, nodes };
}

function lineStart(text: string, pos: number): number {
  return text.lastIndexOf("\n", pos - 1) + 1;
}

/** The string's value with simple escapes resolved (enough for keys and color strings). */
export function unquote(t: Tok): string {
  return (t.value || "").replace(/\\(["'\\])/g, "$1");
}

/** The innermost node whose brackets contain `offset` (between the brackets, not on them). */
export function nodeAt(s: Scan, offset: number): Node | null {
  let best: Node | null = null;
  for (const nd of s.nodes) {
    const end = nd.end < 0 ? Infinity : nd.end;
    if (nd.start < offset && offset <= end && (!best || nd.start > best.start)) best = nd;
  }
  return best;
}

/** Index of the token that contains `offset`, or that ends right at it. */
export function tokenAt(s: Scan, offset: number): number {
  let lo = 0, hi = s.toks.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const t = s.toks[mid];
    if (t.start <= offset) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (found >= 0 && offset <= s.toks[found].end) return found;
  return -1;
}

/** Index of the last token that ends at or before `offset`. */
export function tokenBefore(s: Scan, offset: number): number {
  let lo = 0, hi = s.toks.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (s.toks[mid].end <= offset) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}
