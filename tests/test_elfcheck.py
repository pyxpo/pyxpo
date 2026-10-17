import importlib
import struct

elfcheck = importlib.import_module("pyxpo.build.elfcheck")
android = importlib.import_module("pyxpo.build.android")


def fake_elf(path, align):
    hdr = bytearray(64)
    hdr[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<Q", hdr, 32, 64)
    struct.pack_into("<HH", hdr, 54, 56, 2)
    ph = bytearray(56 * 2)
    struct.pack_into("<I", ph, 0, 1)
    struct.pack_into("<Q", ph, 48, align)
    struct.pack_into("<I", ph, 56, 1)
    struct.pack_into("<Q", ph, 56 + 48, align)
    path.write_bytes(bytes(hdr) + bytes(ph))


def test_min_load_align(tmp_path):
    fake_elf(tmp_path / "a.so", 0x4000)
    fake_elf(tmp_path / "b.so", 0x1000)
    (tmp_path / "c.so").write_bytes(b"nope")
    assert elfcheck.min_load_align(tmp_path / "a.so") == 0x4000
    assert elfcheck.min_load_align(tmp_path / "b.so") == 0x1000
    assert elfcheck.min_load_align(tmp_path / "c.so") is None


def relro_elf(path, relro_end, load_memsz=0x2000, align=0x10000):
    """64 KB-aligned ELF whose RW LOAD at 0x20000 starts with a RELRO segment ending at relro_end."""
    rows = [(1, 0, 0, 0x1000, align), (1, 0x10000, 0x20000, load_memsz, align),
            (0x6474E552, 0x10000, 0x20000, relro_end - 0x20000, 1)]
    hdr = bytearray(64)
    hdr[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<Q", hdr, 32, 64)
    struct.pack_into("<HH", hdr, 54, 56, len(rows))
    ph = b"".join(struct.pack("<IIQQQQQQ", t, 6, off, va, va, ms, ms, al) for t, off, va, ms, al in rows)
    path.write_bytes(bytes(hdr) + ph)


def test_min_load_align_follows_bionic_relro_rule(tmp_path):
    relro_elf(tmp_path / "gfortran.so", 0x21000)  # Chaquopy libgfortran.so.3: RELRO ends on a 4 KB boundary
    relro_elf(tmp_path / "ok.so", 0x24000, load_memsz=0x8000)
    relro_elf(tmp_path / "whole.so", 0x21000, load_memsz=0x1000)  # whole segment is RELRO: no extra check
    relro_elf(tmp_path / "odd.so", 0x20ba0)  # below 4 KB: bionic ignores it
    assert elfcheck.min_load_align(tmp_path / "gfortran.so") == 0x1000
    assert elfcheck.min_load_align(tmp_path / "ok.so") == 0x4000
    assert elfcheck.min_load_align(tmp_path / "whole.so") == 0x10000
    assert elfcheck.min_load_align(tmp_path / "odd.so") == 0x10000
    assert [p.name for p, _ in elfcheck.find_unaligned([tmp_path])] == ["gfortran.so"]


def test_check_16kb_blocks_unless_allowed(tmp_path, capsys):
    site, jni = tmp_path / "site", tmp_path / "jni"
    (site / "numpy").mkdir(parents=True)
    jni.mkdir()
    fake_elf(site / "numpy" / "_x.so", 0x1000)
    fake_elf(jni / "libok.so", 0x4000)
    try:
        android._check_16kb(site, jni, "arm64-v8a", False)
        raise AssertionError("expected BuildError")
    except android.BuildError as e:
        assert "numpy/_x.so" in str(e)
    android._check_16kb(site, jni, "arm64-v8a", True)
    assert "warning" in capsys.readouterr().out
    (site / "numpy" / "_x.so").unlink()
    android._check_16kb(site, jni, "arm64-v8a", False)
