import { strict as assert } from "assert";
import * as fs from "fs";
import * as path from "path";
import { test } from "node:test";

import {
  Data, colorSpots, completionAt, convertStyleKeys, detectNaming, diagnose, hoverAt, isPyxpoFile, toCamel, toSnake,
} from "../src/analyze";
import { formatColor, parseColor } from "../src/colors";
import { scan, tokenize } from "../src/pyscan";
import { mapConfigErrors, schemaAt, tomlColorSpots, tomlCompletionAt, tomlKeyAt, Schema } from "../src/toml";

const data: Data = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "data", "pyxpo.json"), "utf8"));

const HEAD = "from pyxpo import StyleSheet, Text, View, Pressable, component\n";

/** Text with a `|` cursor marker: returns the text without it and the offset. */
function at(src: string): [string, number] {
  const i = src.indexOf("|");
  return [src.slice(0, i) + src.slice(i + 1), i];
}

test("names convert like pyxpo._keys", () => {
  assert.equal(toSnake("fontSize"), "font_size");
  assert.equal(toSnake("borderTopLeftRadius"), "border_top_left_radius");
  assert.equal(toSnake("testID"), "test_id");
  assert.equal(toSnake("flex"), "flex");
  assert.equal(toCamel("font_size"), "fontSize");
  assert.equal(toCamel("test_id"), "testID");
});

test("tokenizer handles prefixes, triple quotes, comments and open strings", () => {
  const t = tokenize('x = rb"a\\"b" # c "d"\ny = """m\n"n"""\nz = "open');
  const strs = t.filter((k) => k.kind === "str");
  assert.deepEqual(strs.map((s) => s.value), ['a\\"b', 'm\n"n', "open"]);
  assert.equal(strs[2].open, true);
  assert.ok(!t.some((k) => k.text === "c"));
});

test("only files that import pyxpo get features", () => {
  assert.ok(isPyxpoFile(HEAD));
  assert.ok(isPyxpoFile("import pyxpo_notifications as N\n"));
  assert.ok(!isPyxpoFile("import os\n# from pyxpo import View\n"));
});

test("style key completion in StyleSheet.create sheets, style= and dict()", () => {
  for (const src of [
    HEAD + 'styles = StyleSheet.create({"box": {|}})',
    HEAD + 'styles = StyleSheet.create({"box": {"flex": 1, |}})',
    HEAD + "View(style={|})",
    HEAD + 'View(style=[styles.a, {"flex": 1, |}])',
    HEAD + "styles = StyleSheet.create(box=dict(|))",
  ]) {
    const [text, off] = at(src);
    const c = completionAt(text, off, data);
    assert.ok(c && c.kind === "styleKey", src);
  }
  const [text, off] = at(HEAD + 'styles = StyleSheet.create({"box": {"flex": 1, "ju|"}})');
  const c = completionAt(text, off, data);
  assert.ok(c && c.kind === "styleKey" && c.form === "str");
  assert.deepEqual(c.present, ["flex"]);
});

test("no style completion for the sheet's own keys or unrelated dicts", () => {
  for (const src of [HEAD + 'styles = StyleSheet.create({|})', HEAD + 'payload = {"name": 1, |}', HEAD + "foo(|)"]) {
    const [text, off] = at(src);
    assert.equal(completionAt(text, off, data), null, src);
  }
});

test("prop completion for component calls", () => {
  const [text, off] = at(HEAD + 'Pressable(Text("hi"), on_press=go, |)');
  const c = completionAt(text, off, data);
  assert.ok(c && c.kind === "prop" && c.component === "Pressable");
  assert.ok(c.present.includes("on_press"));
  const [t2, o2] = at(HEAD + "pyxpo.View(te|");
  const c2 = completionAt(t2, o2, data);
  assert.ok(c2 && c2.kind === "prop" && c2.replaceEnd - c2.replaceStart === 2);
});

test("value completion for enum and color keys", () => {
  const [text, off] = at(HEAD + 'View(style={"justifyContent": "|"})');
  const c = completionAt(text, off, data);
  assert.ok(c && c.kind === "value" && c.key === "justify_content" && c.quoted);
  const [t2, o2] = at(HEAD + "View(style=dict(color=|))");
  const c2 = completionAt(t2, o2, data);
  assert.ok(c2 && c2.kind === "value" && c2.key === "color" && !c2.quoted);
});

test("diagnostics: unknown key with a suggestion, unsupported key, bad enum, bad color", () => {
  const text = HEAD + [
    "styles = StyleSheet.create({",
    '    "box": {"flx": 1, "tintColor": "red", "justifyContent": "middle", "backgroundColor": "#12345"},',
    '    "ok": {"justifyContent": "space_between", "alignItems": "FLEX-START", "color": "rgba(0, 0, 0, 0.5)",',
    '           "fontWeight": "700", "textDecorationLine": "underline", "borderColor": "transparent"},',
    "})",
  ].join("\n");
  const ps = diagnose(text, data);
  const by = (code: string) => ps.filter((p) => p.code === code);
  assert.equal(by("unknown-key").length, 1 + (data.style.keys["text_decoration_line"] ? 0 : 1));
  const flx = by("unknown-key")[0];
  assert.equal(text.slice(flx.start, flx.end), "flx");
  assert.equal(flx.fix, "flex");
  assert.equal(by("unsupported-key").length, 1);
  assert.equal(by("bad-value").length, 1);
  assert.equal(by("bad-color").length, 1);
  assert.equal(text.slice(by("bad-color")[0].start, by("bad-color")[0].end), "#12345");
});

test("diagnostics skip dicts that are not styles", () => {
  const text = HEAD + 'payload = {"flx": 1}\nconfig = dict(colr="x")\nView(data={"zz": 1})\n';
  assert.deepEqual(diagnose(text, data), []);
});

test("camelCase suggestion keeps the file's spelling", () => {
  const text = HEAD + 'View(style={"backgroundColr": "#fff"})';
  const [p] = diagnose(text, data);
  assert.equal(p.fix, "backgroundColor");
});

test("naming follows the file; camelCase by default", () => {
  assert.equal(detectNaming(scan(HEAD), data), "camelCase");
  assert.equal(detectNaming(scan(HEAD + 'View(style={"font_size": 1, "background_color": "red"})'), data), "snake_case");
});

test("convert style keys both ways, only in style dicts", () => {
  const text = HEAD + 'styles = StyleSheet.create({"box": {"fontSize": 1, "flex": 1}})\nother = {"fontSize": 2}';
  const edits = convertStyleKeys(text, "snake_case", data);
  assert.equal(edits.length, 1);
  assert.equal(edits[0].text, "font_size");
  const back = convertStyleKeys(text.replace("fontSize", "font_size"), "camelCase", data);
  assert.equal(back.length, 1);
  assert.equal(back[0].text, "fontSize");
});

test("hover on style keys and components", () => {
  const [text, off] = at(HEAD + 'View(style={"justi|fyContent": "center"})');
  const h = hoverAt(text, off, data);
  assert.ok(h && h.markdown.includes("justify_content"));
  const [t2, o2] = at(HEAD + "Vi|ew(style=None)");
  assert.ok(hoverAt(t2, o2, data)?.markdown.startsWith("**View**"));
});

test("colors parse like pyxpo.style.parse_color", () => {
  assert.deepEqual(parseColor("#1234"), parseColor("#11223344"));
  const c = parseColor("rgba(255, 0, 0, 0.5)")!;
  assert.equal(c.r, 1);
  assert.equal(Math.round(c.a * 255), 128);
  assert.equal(parseColor("red", data.named_colors)!.r, 1);
  assert.equal(parseColor("#12345"), null);
  assert.equal(parseColor("rgb(1, 2)"), null);
});

test("color presentation keeps the original form", () => {
  const c = { r: 1, g: 0, b: 0, a: 1 };
  assert.equal(formatColor(c, "#00f"), "#f00");
  assert.equal(formatColor(c, "#0000FF"), "#FF0000");
  assert.equal(formatColor({ ...c, a: 0.5 }, "#0000ff"), "#ff000080");
  assert.equal(formatColor({ ...c, a: 0.5 }, "rgb(0, 0, 255)"), "rgba(255, 0, 0, 0.5)");
  assert.equal(formatColor(c, "red"), "#ff0000");
});

test("color swatches: hex anywhere, names only as color values", () => {
  const text = HEAD + 'View(style={"color": "red", "fontFamily": "red"})\nx = "#abc"\nmsg = "red"\ny = f"#fff"';
  const spots = colorSpots(text, data).map((s) => s.value);
  assert.deepEqual(spots, ["red", "#abc"]);
});

const schema = data.config as Schema;

test("toml: key, header and value completion from the config schema", () => {
  const lines = ["[project]", 'name = "x"', "[tool.pyxpo]", 'name = "App"', "orien", "[tool.pyxpo.android]", "orientation = "];
  const k = tomlCompletionAt(lines, 4, 5, schema);
  assert.ok(k && k.kind === "key" && k.schema.properties!["orientation"] && k.present.includes("name"));
  assert.equal(tomlCompletionAt(lines, 1, 0, schema), null);
  const v = tomlCompletionAt(lines, 6, 14, schema);
  assert.ok(v && v.kind === "value" && v.schema.enum!.includes("portrait"));
  const h = tomlCompletionAt(["[tool.pyxpo."], 0, 12, schema);
  assert.ok(h && h.kind === "header" && h.options.includes("tool.pyxpo.android"));
});

test("toml: hover path and schema lookup with camelCase keys", () => {
  const lines = ["[tool.pyxpo]", 'backgroundColor = "#fff"', 'splash = { resize_mode = "cover" }'];
  assert.deepEqual(tomlKeyAt(lines, 1, 3)?.path, ["background_color"]);
  assert.deepEqual(tomlKeyAt(lines, 2, 14)?.path, ["splash", "resize_mode"]);
  assert.ok(schemaAt(schema, ["splash", "resizeMode"]));
});

test("toml: pyxpo config errors land on their lines", () => {
  const lines = ["[project]", 'name = "x"', "", "[tool.pyxpo]", 'orientaton = "portrait"',
    'background_color = "red"', "", "[tool.pyxpo.splash]", 'resize_mode = "big"'];
  const out = [
    "Error: invalid pyproject.toml:",
    "  [tool.pyxpo]: unknown key 'orientaton' (did you mean 'orientation'?)",
    "  [tool.pyxpo] background_color: expected a color like #RRGGBB or #RRGGBBAA, got 'red'",
    "  [tool.pyxpo] splash.resize_mode: expected one of contain, cover, native, got 'big'",
    "  [tool.pyxpo] ios.bundle_id: expected a reverse-DNS id like com.acme.app, got 'x'",
  ].join("\n");
  const ps = mapConfigErrors(out, lines);
  assert.deepEqual(ps.map((p) => p.line), [4, 5, 8, 3]);
  assert.equal(lines[4].slice(ps[0].start, ps[0].end), "orientaton");
});

test("toml: hex color swatches only under [tool.pyxpo]", () => {
  const lines = ["[project]", 'x = "#fff"', "[tool.pyxpo]", 'background_color = "#FFAA00"'];
  assert.deepEqual(tomlColorSpots(lines).map((s) => [s.line, s.value]), [[3, "#FFAA00"]]);
});
