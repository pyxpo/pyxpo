"""ctypes tests for the C flexbox engine (native/common/pyxpo_layout.c)."""
from __future__ import annotations

import ctypes as C
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "native" / "common" / "pyxpo_layout.c"
MEASURE = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_float, C.c_int, C.c_float, C.c_int,
                      C.POINTER(C.c_float), C.POINTER(C.c_float))


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no C compiler")
    ext = ".dylib" if sys.platform == "darwin" else ".so"
    out = tmp_path_factory.mktemp("layout") / ("libpxlayout" + ext)
    subprocess.run([cc, "-O1", "-Wall", "-Wextra", "-Wno-unused-parameter", "-shared", "-fPIC", "-o", str(out),
                    str(SRC), "-lm"], check=True)
    L = C.CDLL(str(out))
    L.px_tree_new.restype = C.c_void_p
    L.px_tree_new.argtypes = [MEASURE, C.c_void_p]
    L.px_tree_free.argtypes = [C.c_void_p]
    for f in ("px_node_create", "px_node_delete", "px_node_set_measured", "px_node_mark_dirty"):
        getattr(L, f).argtypes = [C.c_void_p, C.c_int] + ([C.c_int] if f == "px_node_set_measured" else [])
    L.px_node_insert.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int]
    L.px_node_remove.argtypes = [C.c_void_p, C.c_int, C.c_int]
    L.px_prop_id.argtypes = [C.c_char_p]
    L.px_node_set_num.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_float]
    L.px_node_set_str.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_char_p]
    L.px_node_reset.argtypes = [C.c_void_p, C.c_int, C.c_int]
    L.px_tree_calc.argtypes = [C.c_void_p, C.c_float, C.c_float]
    L.px_tree_changed_count.argtypes = [C.c_void_p]
    L.px_tree_changed_at.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_float)]
    L.px_node_frame.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_float)]
    return L


class Tree:
    def __init__(self, lib, measure=None):
        self.L = lib
        self._m = MEASURE(measure) if measure else MEASURE(lambda *a: None)
        self.t = lib.px_tree_new(self._m, None)
        self.next = 2

    def add(self, parent=1, index=-1, **style):
        nid = self.next
        self.next += 1
        assert self.L.px_node_create(self.t, nid) == 0
        assert self.L.px_node_insert(self.t, parent, nid, index) == 0
        self.set(nid, **style)
        return nid

    def set(self, nid, **style):
        for k, v in style.items():
            p = self.L.px_prop_id(k.encode())
            assert p >= 0, k
            if isinstance(v, str):
                assert self.L.px_node_set_str(self.t, nid, p, v.encode()) == 0, (k, v)
            else:
                assert self.L.px_node_set_num(self.t, nid, p, float(v)) == 0, (k, v)

    def calc(self, w=300, h=600):
        return self.L.px_tree_calc(self.t, w, h)

    def f(self, nid):
        a = (C.c_float * 4)()
        assert self.L.px_node_frame(self.t, nid, a) == 0
        return tuple(round(x, 2) for x in a)

    def changed(self):
        out = {}
        a = (C.c_float * 4)()
        for i in range(self.L.px_tree_changed_count(self.t)):
            nid = self.L.px_tree_changed_at(self.t, i, a)
            out[nid] = tuple(round(x, 2) for x in a)
        return out

    def __del__(self):
        try:
            self.L.px_tree_free(self.t)
        except Exception:
            pass


def test_column_default_stretch(lib):
    t = Tree(lib)
    a = t.add(height=50)
    b = t.add(height=100)
    t.calc(300, 600)
    assert t.f(a) == (0, 0, 300, 50)
    assert t.f(b) == (0, 50, 300, 100)


def test_row_grow_and_gap(lib):
    t = Tree(lib)
    t.set(1, flex_direction="row", column_gap=10)
    a = t.add(flex_grow=1)
    b = t.add(flex_grow=2)
    t.calc(310, 100)
    assert t.f(a) == (0, 0, 100, 100)
    assert t.f(b) == (110, 0, 200, 100)


def test_shrink(lib):
    t = Tree(lib)
    t.set(1, flex_direction="row")
    a = t.add(width=200, flex_shrink=1)
    b = t.add(width=200, flex_shrink=1)
    t.calc(300, 100)
    assert t.f(a)[2] == 150 and t.f(b)[2] == 150 and t.f(b)[0] == 150


def test_min_max_clamp_in_grow(lib):
    t = Tree(lib)
    t.set(1, flex_direction="row")
    a = t.add(flex_grow=1, max_width=50)
    b = t.add(flex_grow=1)
    t.calc(300, 100)
    assert t.f(a)[2] == 50 and t.f(b)[2] == 250


def test_justify_and_align(lib):
    t = Tree(lib)
    t.set(1, flex_direction="row", justify_content="center", align_items="center")
    a = t.add(width=100, height=50)
    t.calc(300, 200)
    assert t.f(a) == (100, 75, 100, 50)
    t.set(1, justify_content="space-between")
    b = t.add(width=100, height=50)
    t.calc(300, 200)
    assert t.f(a)[0] == 0 and t.f(b)[0] == 200


def test_justify_end_and_evenly(lib):
    t = Tree(lib)
    t.set(1, justify_content="flex-end")
    a = t.add(height=100)
    t.calc(300, 600)
    assert t.f(a)[1] == 500
    t.set(1, justify_content="space-evenly")
    t.calc(300, 600)
    assert t.f(a)[1] == 250


def test_wrap(lib):
    t = Tree(lib)
    t.set(1, flex_direction="row", flex_wrap="wrap")
    ids = [t.add(width=100, height=40) for _ in range(5)]
    t.calc(250, 600)
    assert [t.f(i)[:2] for i in ids] == [(0, 0), (100, 0), (0, 40), (100, 40), (0, 80)]


def test_percent_and_padding_border(lib):
    t = Tree(lib)
    t.set(1, padding_left=10, padding_top=10, padding_right=10, padding_bottom=10, border_left_width=2,
          border_top_width=2, border_right_width=2, border_bottom_width=2)
    a = t.add(width="50%", height=20)
    t.calc(300, 600)
    assert t.f(a) == (12, 12, 138, 20)


def test_margin(lib):
    t = Tree(lib)
    a = t.add(height=50, margin_top=10, margin_left=5, margin_right=5, margin_bottom=7)
    b = t.add(height=10)
    t.calc(300, 600)
    assert t.f(a) == (5, 10, 290, 50)
    assert t.f(b)[1] == 67


def test_absolute(lib):
    t = Tree(lib)
    a = t.add(position="absolute", top=10, right=20, width=50, height=60)
    b = t.add(position="absolute", left=0, right=0, bottom=0, height=30)
    t.calc(300, 600)
    assert t.f(a) == (230, 10, 50, 60)
    assert t.f(b) == (0, 570, 300, 30)


def test_absolute_does_not_take_space(lib):
    t = Tree(lib)
    t.add(position="absolute", width=10, height=10)
    b = t.add(height=20)
    t.calc(300, 600)
    assert t.f(b)[1] == 0


def test_relative_offset(lib):
    t = Tree(lib)
    a = t.add(height=50, top=5, left=7)
    b = t.add(height=50)
    t.calc(300, 600)
    assert t.f(a)[:2] == (7, 5)
    assert t.f(b)[1] == 50


def test_aspect_ratio(lib):
    t = Tree(lib)
    a = t.add(width=200, aspect_ratio=2)
    t.calc(300, 600)
    assert t.f(a) == (0, 0, 200, 100)


def test_display_none(lib):
    t = Tree(lib)
    a = t.add(height=50, display="none")
    b = t.add(height=10)
    t.calc(300, 600)
    assert t.f(b)[1] == 0


def test_reverse_direction(lib):
    t = Tree(lib)
    t.set(1, flex_direction="row-reverse")
    a = t.add(width=100, height=10)
    b = t.add(width=50, height=10)
    t.calc(300, 100)
    assert t.f(a)[0] == 200 and t.f(b)[0] == 150


def test_nested_auto_size_and_text_measure(lib):
    def measure(ctx, nid, w, wm, h, hm, ow, oh):
        # text 100x20, wraps to 2 lines of 50 when width limited below 100
        if wm != 2 and w < 100:
            ow[0], oh[0] = w, 40
        else:
            ow[0], oh[0] = 100, 20

    def m(ctx, nid, w, wm, h, hm, ow, oh):
        measure(ctx, nid, w, wm, h, hm, ow, oh)

    t = Tree(lib, m)
    box = t.add(flex_direction="row", padding_left=5, padding_right=5, align_self="flex-start")
    txt = t.add(parent=box)
    lib.px_node_set_measured(t.t, txt, 1)
    t.calc(300, 600)
    assert t.f(box) == (0, 0, 110, 20)
    assert t.f(txt) == (5, 0, 100, 20)
    t.set(box, width=60)
    t.calc(300, 600)
    assert t.f(box)[2] == 60 and t.f(txt)[2:] == (50, 40)


def test_changed_frames_only(lib):
    t = Tree(lib)
    a = t.add(height=50)
    b = t.add(height=50)
    assert t.calc(300, 600) == 3
    assert t.calc(300, 600) == 0
    t.set(a, height=80)
    n = t.calc(300, 600)
    ch = t.changed()
    assert a in ch and b in ch and 1 not in ch and n == 2
    assert ch[b] == (0, 80, 300, 50)


def test_resize_root(lib):
    t = Tree(lib)
    a = t.add(flex_grow=1)
    t.calc(300, 600)
    assert t.f(a)[3] == 600
    t.calc(300, 400)
    assert t.f(a)[3] == 400 and a in t.changed()


def test_structure_ops(lib):
    t = Tree(lib)
    a = t.add(height=10)
    b = t.add(height=10)
    c = t.add(height=10, index=0)
    t.calc(100, 100)
    assert t.f(c)[1] == 0 and t.f(a)[1] == 10 and t.f(b)[1] == 20
    assert lib.px_node_remove(t.t, 1, a) == 0
    t.calc(100, 100)
    assert t.f(b)[1] == 10
    assert lib.px_node_delete(t.t, a) == 0
    assert lib.px_node_create(t.t, b) == -1   # duplicate id
    assert lib.px_node_insert(t.t, b, 1, 0) == -1  # cycle / root
    assert lib.px_node_delete(t.t, 1) == -1


def test_prop_lookup_and_reset(lib):
    assert lib.px_prop_id(b"nope") == -1
    t = Tree(lib)
    a = t.add(height=50)
    t.calc(100, 100)
    p = lib.px_prop_id(b"height")
    lib.px_node_reset(t.t, a, p)
    t.calc(100, 100)
    assert t.f(a)[3] == 0
    assert lib.px_node_set_str(t.t, a, lib.px_prop_id(b"flex_direction"), b"sideways") == -1
