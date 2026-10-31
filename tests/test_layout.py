"""ctypes tests for the C flexbox engine (src/pyxpo/_native/common/pyxpo_layout.c)."""
from __future__ import annotations

import ctypes as C
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pyxpo" / "_native" / "common" / "pyxpo_layout.c"
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
    L.px_tree_set_rtl.argtypes = [C.c_void_p, C.c_int]
    L.px_tree_rtl.argtypes = [C.c_void_p]
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


FLEX1 = {"flex_grow": 1, "flex_shrink": 1, "flex_basis": 0}


def box(prop, v):
    return {"%s_%s" % (prop, e): v for e in ("left", "top", "right", "bottom")}


def test_aspect_ratio_with_stretched_width(lib):
    # A stretched width (no width style) still sets the height, as in React Native.
    t = Tree(lib)
    t.set(1, **box("padding", 10))
    a = t.add(aspect_ratio=1, **box("margin", 5))
    b = t.add(height=20)
    t.calc(300, 600)
    assert t.f(a) == (15, 15, 270, 270)
    assert t.f(b) == (10, 290, 280, 20)


def test_aspect_ratio_with_flex_width(lib):
    # In a row, flex: 1 gives the width and the aspect ratio the height; align stretch does not undo it.
    t = Tree(lib)
    row = t.add(flex_direction="row", column_gap=10)
    a = t.add(row, aspect_ratio=2, **FLEX1)
    b = t.add(row, aspect_ratio=0.5, **FLEX1)
    t.calc(310, 600)
    assert t.f(a) == (0, 0, 150, 75)
    assert t.f(b) == (160, 0, 150, 300)
    assert t.f(row) == (0, 0, 310, 300)


def test_aspect_ratio_in_a_card(lib):
    # The doodle-dance gallery card: a flex: 1 column cell holding a square box and a caption.
    t = Tree(lib)
    row = t.add(flex_direction="row")
    card = t.add(row, **FLEX1, **box("padding", 8))
    square = t.add(card, aspect_ratio=1)
    cap = t.add(card, height=16)
    t.add(row, **FLEX1)
    t.calc(216, 600)
    assert t.f(square) == (8, 8, 92, 92)
    assert t.f(cap)[1] == 100
    assert t.f(card) == (0, 0, 108, 124)


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


def test_text_wraps_at_max_width(lib):
    """A centered text with max_width is measured at that width, so its height covers the wrapped lines."""
    def m(ctx, nid, w, wm, h, hm, ow, oh):
        # text 300x20 on one line; wraps into lines of 20 when the width is limited
        if wm != 2 and w < 300:
            lines = -(-300 // int(w))
            ow[0], oh[0] = w, 20 * lines
        else:
            ow[0], oh[0] = 300, 20

    t = Tree(lib, m)
    col = t.add(align_items="center")
    txt = t.add(parent=col, max_width=100)
    lib.px_node_set_measured(t.t, txt, 1)
    t.calc(500, 600)
    assert t.f(txt)[2:] == (100, 60)
    assert t.f(col)[3] == 60
    row = t.add(flex_direction="row", align_items="flex-start")
    txt2 = t.add(parent=row, max_width=150)
    lib.px_node_set_measured(t.t, txt2, 1)
    t.calc(500, 600)
    assert t.f(txt2)[2:] == (150, 40)


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


def test_scroll_content_taller_than_viewport(lib):
    t = Tree(lib)
    sv = t.add(flex_grow=1, scroll=1)
    content = t.add(parent=sv, flex_shrink=0)
    wrap = t.add(parent=content)
    for _ in range(100):
        t.add(parent=wrap, height=48)
    t.calc(300, 600)
    assert t.f(sv) == (0, 0, 300, 600)
    assert t.f(content)[3] == 4800


def test_flex_child_in_scroll_content_keeps_its_content_height(lib):
    # flex: 1 (basis 0) inside an auto-height column has no main size to share, so it is sized by its content
    t = Tree(lib)
    sv = t.add(flex_grow=1, scroll=1)
    content = t.add(parent=sv, flex_shrink=0)
    col = t.add(parent=content)
    a = t.add(parent=col, flex_grow=1, flex_shrink=1, flex_basis=0)
    t.add(parent=a, height=80)
    b = t.add(parent=col, height=50)
    t.calc(300, 600)
    assert t.f(a) == (0, 0, 300, 80)
    assert t.f(b) == (0, 80, 300, 50)


def test_scroll_content_flex_grow_fills_viewport(lib):
    t = Tree(lib)
    sv = t.add(flex_grow=1, scroll=1)
    content = t.add(parent=sv, flex_shrink=0)
    inner = t.add(parent=content, flex_grow=1)
    t.add(parent=inner, height=40)
    t.calc(300, 600)
    assert t.f(content)[3] == 600
    assert t.f(inner)[3] == 600


def test_short_scroll_content_without_grow_stays_short(lib):
    t = Tree(lib)
    sv = t.add(flex_grow=1, scroll=1)
    content = t.add(parent=sv, flex_shrink=0)
    inner = t.add(parent=content)
    t.add(parent=inner, height=40)
    t.calc(300, 600)
    assert t.f(inner)[3] == 40


def test_auto_size_scroll_view_is_not_forced_to_full_height(lib):
    t = Tree(lib)
    col = t.add(height=600)
    sv = t.add(parent=col, scroll=1)
    content = t.add(parent=sv, flex_shrink=0)
    t.add(parent=content, height=40)
    t.calc(300, 600)
    assert t.f(sv)[3] == 40


def test_rtl_row_runs_right_to_left_and_swaps_left_and_right(lib):
    t = Tree(lib)
    t.L.px_tree_set_rtl(t.t, 1)
    row = t.add(flex_direction="row", height=40, padding_left=10)
    a = t.add(row, width=50)
    b = t.add(row, width=30, margin_left=5)
    t.calc(300, 600)
    assert t.f(row) == (0, 0, 300, 40)
    assert t.f(a) == (240, 0, 50, 40)
    assert t.f(b) == (205, 0, 30, 40)


def test_rtl_column_align_start_and_absolute_left(lib):
    t = Tree(lib)
    t.L.px_tree_set_rtl(t.t, 1)
    t.set(1, align_items="flex_start")
    a = t.add(width=100, height=20)
    b = t.add(position="absolute", left=8, top=4, width=10, height=10)
    t.calc(300, 600)
    assert t.f(a) == (200, 0, 100, 20)
    assert t.f(b) == (282, 4, 10, 10)


def test_rtl_toggle_reports_every_moved_frame(lib):
    t = Tree(lib)
    row = t.add(flex_direction="row", height=40)
    a = t.add(row, width=50)
    t.calc(300, 600)
    assert t.f(a) == (0, 0, 50, 40)
    t.L.px_tree_set_rtl(t.t, 1)
    assert t.L.px_tree_rtl(t.t) == 1
    t.calc(300, 600)
    assert t.changed() == {a: (250, 0, 50, 40)}
    t.L.px_tree_set_rtl(t.t, 0)
    t.calc(300, 600)
    assert t.changed() == {a: (0, 0, 50, 40)}


def test_rtl_horizontal_scroll_content_is_not_mirrored_against_the_viewport(lib):
    t = Tree(lib)
    t.L.px_tree_set_rtl(t.t, 1)
    sv = t.add(height=100, scroll=1, flex_direction="row")
    content = t.add(sv, flex_direction="row")
    a = t.add(content, width=200)
    b = t.add(content, width=200)
    t.calc(300, 600)
    assert t.f(content) == (0, 0, 400, 100)
    assert t.f(a) == (200, 0, 200, 100)
    assert t.f(b) == (0, 0, 200, 100)
