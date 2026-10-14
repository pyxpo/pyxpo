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
