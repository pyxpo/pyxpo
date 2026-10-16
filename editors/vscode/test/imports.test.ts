import { strict as assert } from "assert";
import { test } from "node:test";

import { boundNames, importEdit, ImportEdit, missingNames, nameContext } from "../src/imports";
import { scan } from "../src/pyscan";

function apply(text: string, e: ImportEdit | null): string {
  assert.ok(e, "expected an edit");
  return text.slice(0, e.start) + e.text + text.slice(e.end);
}

function add(text: string, name: string): string {
  return apply(text, importEdit(text, scan(text), name));
}

test("adds to an existing one-line import, sorted", () => {
  assert.equal(add("from pyxpo import Text, View\n\nx = 1\n", "StyleSheet"), "from pyxpo import StyleSheet, Text, View\n\nx = 1\n");
  assert.equal(add("from pyxpo import Text\n", "View"), "from pyxpo import Text, View\n");
  assert.equal(add("from pyxpo import Text as T\n", "View"), "from pyxpo import Text as T, View\n");
});

test("adds to a parenthesized import, one per line or inline", () => {
  assert.equal(add("from pyxpo import (\n    Text,\n    View,\n)\n", "StyleSheet"),
    "from pyxpo import (\n    StyleSheet,\n    Text,\n    View,\n)\n");
  assert.equal(add("from pyxpo import (\n    Text,\n    View,\n)\n", "useState"),
    "from pyxpo import (\n    Text,\n    View,\n    useState,\n)\n");
  assert.equal(add("from pyxpo import (\n    Text,\n    View\n)\n", "useState"),
    "from pyxpo import (\n    Text,\n    View,\n    useState\n)\n");
  assert.equal(add("from pyxpo import (Text, View)\n", "Image"), "from pyxpo import (Image, Text, View)\n");
});

test("new import line after the docstring and imports, not in a sub-module import", () => {
  assert.equal(add('"""Doc."""\nimport os\nfrom pyxpo.router import Link\n\nx = 1\n', "View"),
    '"""Doc."""\nimport os\nfrom pyxpo.router import Link\nfrom pyxpo import View\n\nx = 1\n');
  assert.equal(add("x = 1\n", "View"), "from pyxpo import View\n\nx = 1\n");
  assert.equal(add("#!/usr/bin/env python\nx = 1\n", "View"), "#!/usr/bin/env python\nfrom pyxpo import View\nx = 1\n");
  assert.equal(add("", "View"), "from pyxpo import View\n");
  assert.equal(add("import os", "View"), "import os\nfrom pyxpo import View");
});

test("no edit when the name is bound or star-imported", () => {
  for (const src of ["from pyxpo import View\n", "def View():\n    pass\n", "View = 1\n", "from pyxpo import *\n",
    "import View\n", "class View:\n    pass\n", "def f():\n    from pyxpo import View\n"]) {
    assert.equal(importEdit(src, scan(src), "View"), null, src);
  }
});

test("bound names", () => {
  const src = "import os.path\nfrom a import b as c, d\nfor i, j in x:\n    pass\nwith o as w:\n    pass\nk = 1\n";
  const b = boundNames(src, scan(src));
  for (const n of ["os", "c", "d", "i", "w", "k"]) assert.ok(b.has(n), n);
  assert.ok(!b.has("b") && !b.has("path"));
});

test("name context: identifiers only where a pyxpo name fits", () => {
  const ok = (src: string) => {
    const i = src.indexOf("|");
    const t = src.slice(0, i) + src.slice(i + 1);
    return nameContext(t, scan(t), i);
  };
  assert.deepEqual(ok("x = Vi|"), { start: 4, word: "Vi" });
  assert.ok(ok("return View(Te|)"));
  for (const src of ["x = a.Vi|", 'x = "Vi|"', "from pyxpo import Vi|", "def Vi|", "View(sty|=1)", "# Vi|"]) {
    assert.equal(ok(src), null, src);
  }
});

test("missing names: used, exported and not bound", () => {
  const src = "from pyxpo import View\n\ndef Screen():\n    n, set_n = useState(0)\n    return View(Text('x'), style=1)\n";
  assert.deepEqual(missingNames(src, scan(src), ["View", "Text", "useState", "StyleSheet", "style"]), ["useState", "Text"]);
});
