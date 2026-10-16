// Color strings as pyxpo parses them (pyxpo.style.parse_color): #rgb, #rgba, #rrggbb, #rrggbbaa (CSS order),
// rgb(), rgba() and a few names. Channels are 0..1 here, like vscode.Color.

export interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

const RGB = /^(rgba?)\(\s*([^)]*)\)$/i;

function chan(p: string): number {
  const v = p.endsWith("%") ? parseFloat(p.slice(0, -1)) * 2.55 : parseFloat(p);
  if (!isFinite(v) || !/^[+-]?(\d+\.?\d*|\.\d+)%?$/.test(p)) return NaN;
  return Math.max(0, Math.min(255, Math.round(v))) / 255;
}

function alpha(p: string): number {
  const v = p.endsWith("%") ? parseFloat(p.slice(0, -1)) / 100 : parseFloat(p);
  if (!isFinite(v) || !/^[+-]?(\d+\.?\d*|\.\d+)%?$/.test(p)) return NaN;
  return Math.max(0, Math.min(255, Math.round(v * 255))) / 255;
}

/** Parses a color string; `named` maps lower-case names to #rrggbb / #rrggbbaa. Null when it is not a color. */
export function parseColor(value: string, named: Record<string, string> = {}): Rgba | null {
  const s = value.trim().toLowerCase();
  if (named[s]) return parseColor(named[s]);
  if (s.startsWith("#")) {
    let h = s.slice(1);
    if (!/^[0-9a-f]+$/.test(h)) return null;
    if (h.length === 3 || h.length === 4) h = h.split("").map((c) => c + c).join("");
    if (h.length !== 6 && h.length !== 8) return null;
    const n = (i: number) => parseInt(h.slice(i, i + 2), 16) / 255;
    return { r: n(0), g: n(2), b: n(4), a: h.length === 8 ? n(6) : 1 };
  }
  const m = RGB.exec(s);
  if (m) {
    const parts = m[2].trim().split(/[,\s/]+/).filter((p) => p);
    if (parts.length !== 3 && parts.length !== 4) return null;
    const [r, g, b] = parts.slice(0, 3).map(chan);
    const a = parts.length === 4 ? alpha(parts[3]) : 1;
    if ([r, g, b, a].some((x) => isNaN(x))) return null;
    return { r, g, b, a };
  }
  return null;
}

/** True when the string is meant as a color literal (a hex or rgb() form), even when it is a bad one. */
export function looksLikeColor(value: string): boolean {
  return /^\s*(#|rgba?\()/i.test(value);
}

function hex2(v: number): string {
  return Math.round(v * 255).toString(16).padStart(2, "0");
}

function num(v: number): string {
  return String(Math.round(v * 1000) / 1000);
}

/**
 * Writes `c` in the same form as `original`: a hex keeps its length class and letter case, rgb()/rgba() stay
 * functions (rgb becomes rgba when the alpha is not 1), a name becomes a hex.
 */
export function formatColor(c: Rgba, original: string): string {
  const o = original.trim();
  const fn = /^(rgba?)\(/i.exec(o);
  if (fn) {
    const upper = fn[1] === fn[1].toUpperCase();
    const rgb = [c.r, c.g, c.b].map((v) => Math.round(v * 255)).join(", ");
    const name = c.a < 1 ? "rgba" : fn[1].toLowerCase();
    const body = name === "rgba" ? `${rgb}, ${num(c.a)}` : rgb;
    return `${upper ? name.toUpperCase() : name}(${body})`;
  }
  const upper = /^#[^a-f]*[A-F]/.test(o);
  const len = o.startsWith("#") ? o.length - 1 : 6;
  const short = (len === 3 || len === 4) && [c.r, c.g, c.b, c.a].every((v) => hex2(v)[0] === hex2(v)[1]);
  let out: string;
  if (short) {
    out = "#" + [c.r, c.g, c.b].map((v) => hex2(v)[0]).join("") + (c.a < 1 || len === 4 ? hex2(c.a)[0] : "");
  } else {
    out = "#" + hex2(c.r) + hex2(c.g) + hex2(c.b) + (c.a < 1 || len === 8 ? hex2(c.a) : "");
  }
  return upper ? out.toUpperCase() : out;
}
