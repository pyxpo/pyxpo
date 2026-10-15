import shutil
import struct
import sys
import zlib

import pytest

from pyxpo.app_config import images


def _chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def _png(w, h, ctype, depth, raw_row, extra=()):
    ihdr = struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, 0)
    body = zlib.compress((b"\x00" + raw_row) * h)
    return images.SIG + _chunk(b"IHDR", ihdr) + b"".join(_chunk(t, d) for t, d in extra) + _chunk(b"IDAT", body) + _chunk(b"IEND", b"")


def test_info_rejects_non_png(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"GIF89a....")
    with pytest.raises(ValueError, match="not a PNG"):
        images.info(f)


def test_info_color_types(tmp_path):
    cases = {
        "rgb": (_png(2, 2, 2, 8, b"\x01\x02\x03" * 2), False),
        "gray_alpha_opaque": (_png(2, 2, 4, 8, b"\x10\xff" * 2), False),
        "gray_alpha_clear": (_png(2, 2, 4, 8, b"\x10\x00" * 2), True),
        "palette_trns": (_png(2, 2, 3, 8, b"\x00\x00", [(b"tRNS", b"\x80")]), True),
        "palette_plain": (_png(2, 2, 3, 8, b"\x00\x00"), False),
    }
    for name, (data, alpha) in cases.items():
        f = tmp_path / (name + ".png")
        f.write_bytes(data)
        i = images.info(f)
        assert (i["width"], i["height"], i["has_alpha"]) == (2, 2, alpha), name


def test_info_partial_alpha_is_alpha(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(images.solid_png(3, 3, (1, 2, 3, 254)))
    assert images.info(f)["has_alpha"] is True


def test_solid_png_non_square_rgb(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(images.solid_png(5, 3, (9, 8, 7, 255), alpha=False))
    assert images.info(f) == {"width": 5, "height": 3, "has_alpha": False}


def test_resize_creates_parent_and_scales(tmp_path):
    src = tmp_path / "a.png"
    src.write_bytes(images.solid_png(64, 64, (200, 30, 60, 255)))
    dst = tmp_path / "deep" / "dir" / "b.png"
    backend = images.resize(src, dst, 16)
    assert backend in ("sips", "pillow", "copy")
    if backend != "copy":
        assert images.info(dst)["width"] == 16 and images.info(dst)["height"] == 16


def test_resize_width_keeps_aspect(tmp_path):
    src = tmp_path / "a.png"
    src.write_bytes(images.solid_png(80, 40, (1, 2, 3, 255)))
    dst = tmp_path / "out" / "b.png"
    backend = images.resize_width(src, dst, 20)
    assert backend in ("sips", "pillow", "copy")
    if backend != "copy":
        assert (images.info(dst)["width"], images.info(dst)["height"]) == (20, 10)


def test_resize_falls_back_to_pillow(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.setattr(images.shutil, "which", lambda n: None)
    src = tmp_path / "a.png"
    src.write_bytes(images.solid_png(80, 40, (1, 2, 3, 255)))
    assert images.resize(src, tmp_path / "s.png", 10) == "pillow"
    assert images.resize_width(src, tmp_path / "w.png", 20) == "pillow"
    assert images.info(tmp_path / "s.png")["width"] == 10
    assert (images.info(tmp_path / "w.png")["width"], images.info(tmp_path / "w.png")["height"]) == (20, 10)


def test_resize_falls_back_to_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(images.shutil, "which", lambda n: None)
    monkeypatch.setitem(sys.modules, "PIL", None)  # import PIL raises ImportError
    src = tmp_path / "a.png"
    src.write_bytes(images.solid_png(8, 8))
    for fn, name in ((images.resize, "s.png"), (images.resize_width, "w.png")):
        assert fn(src, tmp_path / name, 4) == "copy"
        assert (tmp_path / name).read_bytes() == src.read_bytes()


def test_resize_sips_failure_falls_through(tmp_path, monkeypatch):
    monkeypatch.setattr(images.shutil, "which", lambda n: "/usr/bin/sips")

    class R:
        returncode = 1
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setitem(sys.modules, "PIL", None)
    src = tmp_path / "a.png"
    src.write_bytes(images.solid_png(8, 8))
    assert images.resize(src, tmp_path / "s.png", 4) == "copy"
    assert images.resize_width(src, tmp_path / "w.png", 4) == "copy"


@pytest.mark.skipif(not shutil.which("sips"), reason="sips only on macOS")
def test_sips_backend(tmp_path):
    src = tmp_path / "a.png"
    src.write_bytes(images.solid_png(80, 40, (1, 2, 3, 255)))
    assert images.resize_width(src, tmp_path / "w.png", 20) == "sips"
    assert (images.info(tmp_path / "w.png")["width"], images.info(tmp_path / "w.png")["height"]) == (20, 10)
