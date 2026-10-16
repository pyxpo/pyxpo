// Auto-import of pyxpo names: which names a file already has, and the edit that adds `from pyxpo import X`.
import { Scan, Tok } from "./pyscan";

export interface ImportEdit {
  /** Replace text[start:end] (empty for an insert) with `text`. */
  start: number;
  end: number;
  text: string;
}

function lineStart(text: string, offset: number): number {
  return text.lastIndexOf("\n", offset - 1) + 1;
}

function lineEnd(text: string, offset: number): number {
  const i = text.indexOf("\n", offset);
  return i < 0 ? text.length : i;
}

/** Bracket depth before each token. */
function depths(toks: Tok[]): number[] {
  const out: number[] = [];
  let d = 0;
  for (const t of toks) {
    out.push(d);
    if (t.kind !== "op") continue;
    if (t.text === "(" || t.text === "[" || t.text === "{") d++;
    else if ((t.text === ")" || t.text === "]" || t.text === "}") && d > 0) d--;
  }
  return out;
}

interface Stmt {
  first: number; // token index
  last: number;
}

/** Top-level statements: they start on a line at column 0 outside brackets and run to the next one. */
function topLevel(text: string, s: Scan): Stmt[] {
  const d = depths(s.toks);
  const out: Stmt[] = [];
  s.toks.forEach((t, i) => {
    if (d[i] !== 0 || lineStart(text, t.start) !== t.start) return;
    if (i > 0 && text.slice(s.toks[i - 1].end, t.start).trimEnd().endsWith("\\")) return;
    if (out.length) out[out.length - 1].last = i - 1;
    out.push({ first: i, last: s.toks.length - 1 });
  });
  return out;
}

/** Names the file binds: imports, def, class, assignment targets, for/as/with targets and parameters. */
export function boundNames(text: string, s: Scan): Set<string> {
  const out = new Set<string>();
  const toks = s.toks;
  const d = depths(toks);
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    const prev = toks[i - 1];
    const next = toks[i + 1];
    if (t.kind !== "name") continue;
    if (prev && prev.kind === "name" && ["def", "class", "as", "for", "global", "nonlocal"].includes(prev.text)) out.add(t.text);
    else if (next && (next.text === "=" || next.text === ":=") && (d[i] === 0 || prev?.text === "(" || prev?.text === ","))
      out.add(t.text); // also keyword arguments: harmless, they only hide a suggestion
    else if (next && next.text === "," && d[i] === 0 && lineStart(text, toks[i].start) === toks[i].start) out.add(t.text);
  }
  for (const st of topLevel(text, s).concat(nestedImports(text, s))) {
    const head = toks[st.first].text;
    if (head !== "import" && head !== "from") continue;
    let k = st.first + 1;
    if (head === "from") {
      while (k <= st.last && toks[k].text !== "import") k++;
      k++;
    }
    for (; k <= st.last; k++) {
      const t = toks[k];
      if (t.kind !== "name" || t.text === "as") continue;
      const after = toks[k + 1];
      if (after && after.text === "as") continue; // `X as Y` binds Y, read on its own turn
      if (after && after.text === "." && head === "import") { // `import a.b` binds a
        out.add(t.text);
        while (k + 2 <= st.last && toks[k + 1].text === "." && toks[k + 2].kind === "name") k += 2;
        continue;
      }
      out.add(t.text);
    }
  }
  return out;
}

/** Indented `import` / `from` statements (inside functions or `if TYPE_CHECKING:` blocks). */
function nestedImports(text: string, s: Scan): Stmt[] {
  const out: Stmt[] = [];
  const d = depths(s.toks);
  s.toks.forEach((t, i) => {
    if (d[i] !== 0 || (t.text !== "import" && t.text !== "from") || t.kind !== "name") return;
    const ls = lineStart(text, t.start);
    if (ls === t.start || text.slice(ls, t.start).trim() !== "") return;
    const end = lineEnd(text, t.start);
    let j = i;
    let depth = 0;
    while (j + 1 < s.toks.length && (s.toks[j + 1].start < end || depth > 0)) {
      j++;
      if (s.toks[j].text === "(") depth++;
      if (s.toks[j].text === ")") depth--;
    }
    out.push({ first: i, last: j });
  });
  return out;
}

/** isort / Ruff "order by type": CONSTANTS, then Classes, then functions; each group case-sensitive. */
function importOrder(a: string, b: string): number {
  const rank = (n: string) => (n.length > 1 && n === n.toUpperCase() ? 0 : /^[A-Z]/.test(n) ? 1 : 2);
  return rank(a) - rank(b) || (a < b ? -1 : a > b ? 1 : 0);
}

/** The edit that makes `name` importable from `module`, or null when the file already binds it. */
export function importEdit(text: string, s: Scan, name: string, module = "pyxpo"): ImportEdit | null {
  if (boundNames(text, s).has(name)) return null;
  const toks = s.toks;
  const stmts = topLevel(text, s);
  const modParts = module.split(".");
  for (const st of stmts) {
    if (toks[st.first].text !== "from") continue;
    // from <module> import ...
    let k = st.first + 1;
    const mod: string[] = [];
    while (k <= st.last && toks[k].text !== "import") mod.push(toks[k++].text);
    if (mod.join("") !== modParts.join(".") || k > st.last) continue;
    let first = k + 1;
    let last = st.last;
    const paren = toks[first]?.text === "(";
    if (paren) {
      first++;
      if (toks[last].text === ")") last--;
    }
    if (toks[first]?.text === "*") return null;
    const items: { start: number; end: number; name: string }[] = [];
    for (let i = first; i <= last; i++) {
      if (toks[i].kind !== "name") continue;
      const j = toks[i + 1]?.text === "as" ? i + 2 : i;
      items.push({ start: toks[i].start, end: toks[j].end, name: toks[i].text });
      i = j;
    }
    if (!items.length) continue;
    const multiline = paren && items.some((it, n) => n > 0 && text.lastIndexOf("\n", it.start) > items[n - 1].end);
    const at = items.find((it) => importOrder(it.name, name) > 0);
    if (at) {
      const sep = multiline ? `,\n${text.slice(lineStart(text, at.start), at.start)}` : ", ";
      return { start: at.start, end: at.start, text: name + sep };
    }
    const lastItem = items[items.length - 1];
    if (multiline) {
      const indent = text.slice(lineStart(text, lastItem.start), lastItem.start);
      const comma = toks.find((t) => t.start >= lastItem.end && t.text === ",");
      const closeAt = paren ? toks[st.last].start : lineEnd(text, lastItem.end);
      if (comma && comma.start < closeAt) return { start: comma.end, end: comma.end, text: `\n${indent}${name},` };
      return { start: lastItem.end, end: lastItem.end, text: `,\n${indent}${name}` };
    }
    return { start: lastItem.end, end: lastItem.end, text: `, ${name}` };
  }
  // a new line after the leading docstring and imports
  let after = -1;
  for (const st of stmts) {
    const head = toks[st.first];
    const isDoc = head.kind === "str" && st === stmts[0] && st.first === st.last;
    if (head.text === "import" || head.text === "from" || isDoc) after = toks[st.last].end;
    else break;
  }
  const line = `from ${module} import ${name}\n`;
  if (after < 0) {
    // keep a shebang, encoding line or leading comments first
    let at = 0;
    while (at < text.length && text[at] === "#") at = lineEnd(text, at) + 1;
    return { start: Math.min(at, text.length), end: Math.min(at, text.length), text: line + (toks.length && at === 0 ? "\n" : "") };
  }
  const end = lineEnd(text, after);
  return end >= text.length ? { start: end, end, text: "\n" + line.trimEnd() } : { start: end + 1, end: end + 1, text: line };
}

/** True when the identifier ending at `offset` is in a place where a pyxpo name can be used (not after `.`, in a
 * string, import line, `def`/`class` name or keyword argument name). */
export function nameContext(text: string, s: Scan, offset: number): { start: number; word: string } | null {
  let start = offset;
  while (start > 0 && /[A-Za-z0-9_]/.test(text[start - 1])) start--;
  const word = text.slice(start, offset);
  if (!/^[A-Za-z_]/.test(word || "_")) return null;
  for (const t of s.toks) {
    if (t.start >= offset) break;
    if (t.kind === "str" && t.start < offset && (t.end > offset || t.open)) return null;
  }
  let k = start - 1;
  while (k >= 0 && (text[k] === " " || text[k] === "\t")) k--;
  if (text[k] === ".") return null;
  const before = text.slice(lineStart(text, start), start);
  if (/^\s*(from|import)\b/.test(before) || /\b(def|class)\s+$/.test(before) || before.trimStart().startsWith("#")) return null;
  const rest = text.slice(offset, lineEnd(text, offset));
  if (/^\s*=[^=]/.test(rest) && /[(,]\s*$/.test(before)) return null; // keyword argument name
  return { start, word };
}

/** Names used in the file that pyxpo exports but the file does not bind (for "add missing imports"). */
export function missingNames(text: string, s: Scan, exportsList: Iterable<string>): string[] {
  const bound = boundNames(text, s);
  const wanted = new Set(exportsList);
  const out: string[] = [];
  s.toks.forEach((t, i) => {
    if (t.kind !== "name" || !wanted.has(t.text) || bound.has(t.text) || out.includes(t.text)) return;
    const prev = s.toks[i - 1];
    const next = s.toks[i + 1];
    if (prev && prev.text === ".") return;
    if (next && next.text === "=" && prev && (prev.text === "(" || prev.text === ",")) return;
    const before = text.slice(lineStart(text, t.start), t.start);
    if (/^\s*(from|import)\b/.test(before)) return;
    out.push(t.text);
  });
  return out;
}
