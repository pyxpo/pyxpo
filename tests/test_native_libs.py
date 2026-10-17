import struct
from importlib.machinery import ExtensionFileLoader

import pytest

from pyxpo import native_libs


def fake_so(path, needed, is64=True, vaddr=0x10000):
    """ELF shared library with one PT_LOAD over the whole file, a PT_DYNAMIC and a string table."""
    strtab = b"\0" + b"".join(n.encode() + b"\0" for n in needed)
    offs, pos = [], 1
    for n in needed:
        offs.append(pos)
        pos += len(n) + 1
    if is64:
        ehsize, phentsize, dyn_fmt, ph_fmt = 64, 56, "<qQ", "<IIQQQQQQ"
    else:
        ehsize, phentsize, dyn_fmt, ph_fmt = 52, 32, "<iI", "<IIIIIIII"
    dyn_off = ehsize + 2 * phentsize
    dyn = [(native_libs.DT_NEEDED, o) for o in offs] + [(native_libs.DT_STRTAB, 0), (native_libs.DT_NULL, 0)]
    dyn_size = len(dyn) * struct.calcsize(dyn_fmt)
    str_off = dyn_off + dyn_size
    dyn[-2] = (native_libs.DT_STRTAB, vaddr + str_off)
    total = str_off + len(strtab)
    head = bytearray(ehsize)
    head[:6] = b"\x7fELF" + bytes([2 if is64 else 1, 1])
    if is64:
        struct.pack_into("<Q", head, 32, ehsize)
        struct.pack_into("<HH", head, 54, phentsize, 2)
        load = struct.pack(ph_fmt, 1, 5, 0, vaddr, vaddr, total, total, 0x4000)
        dynamic = struct.pack(ph_fmt, 2, 6, dyn_off, vaddr + dyn_off, vaddr + dyn_off, dyn_size, dyn_size, 8)
    else:
        struct.pack_into("<I", head, 28, ehsize)
        struct.pack_into("<HH", head, 42, phentsize, 2)
        load = struct.pack(ph_fmt, 1, 0, vaddr, vaddr, total, total, 5, 0x1000)
        dynamic = struct.pack(ph_fmt, 2, dyn_off, vaddr + dyn_off, vaddr + dyn_off, dyn_size, dyn_size, 6, 4)
    body = b"".join(struct.pack(dyn_fmt, t, v) for t, v in dyn)
    path.write_bytes(bytes(head) + load + dynamic + body + strtab)
    return str(path)


@pytest.mark.parametrize("is64", [True, False])
def test_needed_reads_dt_needed(tmp_path, is64):
    p = fake_so(tmp_path / "x.so", ["libopenblas.so", "libm.so", "libc.so"], is64=is64)
    assert native_libs.needed(p) == ["libopenblas.so", "libm.so", "libc.so"]


def test_needed_is_empty_for_non_elf(tmp_path):
    (tmp_path / "a.so").write_bytes(b"not an elf")
    (tmp_path / "b.so").write_bytes(b"\x7fELF\x02\x01" + b"\0" * 10)  # truncated
    assert native_libs.needed(str(tmp_path / "a.so")) == []
    assert native_libs.needed(str(tmp_path / "b.so")) == []
    assert native_libs.needed(str(tmp_path / "missing.so")) == []
    assert native_libs.needed(fake_so(tmp_path / "c.so", [])) == []


def make_site(tmp_path):
    site = tmp_path / "site"
    lib = site / "chaquopy" / "lib"
    lib.mkdir(parents=True)
    (site / "numpy" / "core").mkdir(parents=True)
    (site / "scipy.libs").mkdir()
    fake_so(lib / "libopenblas.so", ["libgfortran.so.3", "libc++_shared.so", "libm.so"])
    fake_so(lib / "libgfortran.so.3", ["libc++_shared.so"])
    fake_so(lib / "libc++_shared.so", ["libc.so"])
    fake_so(site / "scipy.libs" / "libfoo-ab12.so", ["libopenblas.so"])
    ext = fake_so(site / "numpy" / "core" / "_multiarray_umath.so", ["libopenblas.so", "libc.so"])
    return site, ext


def test_lib_dirs(tmp_path):
    site, _ = make_site(tmp_path)
    assert native_libs.lib_dirs([str(site), "", str(tmp_path / "nope")]) == [
        str(site / "chaquopy" / "lib"), str(site / "scipy.libs")]


def test_preloader_loads_dependencies_first_and_once(tmp_path):
    site, ext = make_site(tmp_path)
    calls = []
    pre = native_libs.Preloader(native_libs.lib_dirs([str(site)]), load=lambda name, path: calls.append(name))
    pre.before(ext)
    assert calls == ["libc++_shared.so", "libgfortran.so.3", "libopenblas.so"]  # libc/libm: not shipped
    pre.before(ext)
    pre.before(str(site / "scipy.libs" / "libfoo-ab12.so"))
    assert calls == ["libc++_shared.so", "libgfortran.so.3", "libopenblas.so"]


def test_preloader_survives_load_failure(tmp_path, capsys):
    site, ext = make_site(tmp_path)
    calls = []

    def load(name, path):
        calls.append(name)
        if name == "libgfortran.so.3":
            raise OSError("not 16 KB aligned")

    pre = native_libs.Preloader(native_libs.lib_dirs([str(site)]), load=load)
    pre.before(ext)
    assert calls == ["libc++_shared.so", "libgfortran.so.3", "libopenblas.so"]
    assert "libgfortran.so.3: not 16 KB aligned" in capsys.readouterr().err
    assert pre.loaded == {"libc++_shared.so", "libopenblas.so"}


def test_preloader_handles_cycles(tmp_path):
    lib = tmp_path / "x.libs"
    lib.mkdir()
    fake_so(lib / "liba.so", ["libb.so"])
    fake_so(lib / "libb.so", ["liba.so"])
    ext = fake_so(tmp_path / "ext.so", ["liba.so"])
    calls = []
    native_libs.Preloader([str(lib)], load=lambda n, p: calls.append(n)).before(ext)
    assert calls == ["libb.so", "liba.so"]


def test_install_hooks_extension_loader(tmp_path, monkeypatch):
    site, ext = make_site(tmp_path)
    monkeypatch.setattr(native_libs, "_installed", False)
    monkeypatch.setattr(ExtensionFileLoader, "create_module", lambda self, spec: "module")
    calls = []
    monkeypatch.setattr(native_libs, "_dlopen", lambda name, path: calls.append(name))
    assert native_libs.install([str(tmp_path / "empty")]) is None  # no wheel ships libraries
    assert native_libs.install([str(site)]) is not None
    assert ExtensionFileLoader("numpy.core._multiarray_umath", ext).create_module(None) == "module"
    assert calls == ["libc++_shared.so", "libgfortran.so.3", "libopenblas.so"]
    assert native_libs.install([str(site)]) is None  # once
