"""Native bridge tests: UTF-16 <-> UTF-8 conversion used by the JNI layer (native/common/pyxpo_utf.c) and
the init/finalize lifecycle of native/common/pyxpo_bridge.c, driven by a small embedding harness."""
from __future__ import annotations

import ctypes as C
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

COMMON = Path(__file__).resolve().parents[1] / "native" / "common"


def _cc() -> str:
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no C compiler")
    return cc


@pytest.fixture(scope="module")
def utf(tmp_path_factory):
    ext = ".dylib" if sys.platform == "darwin" else ".so"
    out = tmp_path_factory.mktemp("utf") / ("libpxutf" + ext)
    subprocess.run([_cc(), "-O1", "-Wall", "-Wextra", "-shared", "-fPIC", "-o", str(out),
                    str(COMMON / "pyxpo_utf.c")], check=True)
    L = C.CDLL(str(out))
    L.pyxpo_utf16_to_utf8.restype = C.c_void_p
    L.pyxpo_utf16_to_utf8.argtypes = [C.POINTER(C.c_uint16), C.c_size_t, C.POINTER(C.c_size_t)]
    L.pyxpo_utf8_to_utf16.restype = C.c_void_p
    L.pyxpo_utf8_to_utf16.argtypes = [C.c_char_p, C.POINTER(C.c_size_t)]
    libc = C.CDLL(None)
    libc.free.argtypes = [C.c_void_p]

    def to8(units):
        arr = (C.c_uint16 * max(len(units), 1))(*units)
        n = C.c_size_t()
        p = L.pyxpo_utf16_to_utf8(arr, len(units), C.byref(n))
        try:
            return C.string_at(p, n.value)
        finally:
            libc.free(p)

    def to16(data: bytes):
        n = C.c_size_t()
        p = L.pyxpo_utf8_to_utf16(data, C.byref(n))
        try:
            return list((C.c_uint16 * n.value).from_address(p)) if n.value else []
        finally:
            libc.free(p)

    return to8, to16


def _units(s: str):
    b = s.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)]


@pytest.mark.parametrize("text", ["", "abc", "héllo", "日本語", "😀", '{"event":"change","payload":{"value":"hi 👋🏽 𝄞"}}'])
def test_utf16_to_utf8_matches_python(utf, text):
    to8, to16 = utf
    assert to8(_units(text)) == text.encode("utf-8")
    assert to16(text.encode("utf-8")) == _units(text)


def test_non_bmp_is_real_utf8_not_cesu8(utf):
    to8, _ = utf
    out = to8(_units("😀"))
    assert out == b"\xf0\x9f\x98\x80"
    assert out.decode("utf-8") == "😀"  # CESU-8 (what GetStringUTFChars gives) would raise here


def test_lone_surrogates_become_replacement(utf):
    to8, _ = utf
    assert to8([0x61, 0xD83D]) == "a�".encode()
    assert to8([0xDE00, 0x62]) == "�b".encode()
    assert to8([0xD83D, 0xD83D, 0xDE00]) == "�😀".encode()


def test_invalid_utf8_becomes_replacement(utf):
    _, to16 = utf
    assert to16(b"a\xffb") == [0x61, 0xFFFD, 0x62]
    assert to16(b"\xc0\xaf") == [0xFFFD, 0xFFFD]          # overlong
    assert to16(b"\xed\xa0\xbd") == [0xFFFD] * 3          # encoded surrogate (CESU-8 half)
    assert to16(b"\xf0\x9f\x98") == [0xFFFD] * 3          # truncated
    assert to16(b"\xf4\x90\x80\x80") == [0xFFFD] * 4      # > U+10FFFF


HARNESS = r"""
#include <Python.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "pyxpo_bridge.h"

static atomic_int stop, ok_running, phase; /* phase: 0 before init, 1 running, 2 after finalize */
static atomic_int bad_after, posts;
static const char *EV = "{\"event\":\"change\",\"id\":1,\"payload\":{\"value\":\"hi \xf0\x9f\x98\x80\"}}";

static void on_post(const char *json) {
    if (strcmp(json, "[\"\xf0\x9f\x91\x8b\"]") == 0) atomic_fetch_add(&posts, 1);
}

static void *hammer(void *arg) {
    while (!atomic_load(&stop)) {
        int ph = atomic_load(&phase);
        int rc = pyxpo_bridge_dispatch_event(EV);
        if (rc == 0) atomic_fetch_add(&ok_running, 1);
        if (rc == 0 && ph == 2) atomic_fetch_add(&bad_after, 1);
    }
    return NULL;
}

int main(int argc, char **argv) {
    pyxpo_bridge_set_post_callback(on_post);
    if (pyxpo_bridge_register() != 0) return 10;
    pthread_t th[4];
    for (int i = 0; i < 4; i++) pthread_create(&th[i], NULL, hammer, NULL);
    usleep(20000); /* events before init must be refused, not crash */

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.install_signal_handlers = 0;
    wchar_t *home = Py_DecodeLocale(argv[1], NULL);
    PyStatus st = PyConfig_SetString(&config, &config.home, home);
    PyMem_RawFree(home);
    if (PyStatus_Exception(st)) return 11;
    st = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(st)) return 12;
    pyxpo_bridge_mark_running();
    atomic_store(&phase, 1);

    int r = PyRun_SimpleString(
        "import _pyxpo_bridge, json, time\n"
        "got = []\n"
        "_pyxpo_bridge.set_event_handler(got.append)\n"
        "deadline = time.time() + 5\n"
        "while len(got) < 50 and time.time() < deadline: time.sleep(0.01)\n"
        "assert len(got) >= 50, len(got)\n"
        "assert json.loads(got[0])['payload']['value'] == 'hi \\U0001F600', got[0]\n"
        "_pyxpo_bridge.post(json.dumps(['\\U0001F44B'], ensure_ascii=False))\n");
    if (r != 0) return 13;
    /* finalize while 4 threads keep dispatching */
    if (pyxpo_bridge_finalize() != 0) return 14;
    atomic_store(&phase, 2);
    usleep(50000); /* events after finalize must be refused, not crash */
    atomic_store(&stop, 1);
    for (int i = 0; i < 4; i++) pthread_join(th[i], NULL);
    if (atomic_load(&bad_after) != 0) return 15;
    if (atomic_load(&posts) != 1) return 16;
    printf("delivered=%d\n", atomic_load(&ok_running));
    return 0;
}
"""


def _embed_flags():
    inc = sysconfig.get_paths().get("include")
    if not inc or not (Path(inc) / "Python.h").exists():
        pytest.skip("no Python headers")
    fw = sysconfig.get_config_var("PYTHONFRAMEWORK")
    if fw:
        prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
        return ["-I" + inc], ["-F" + prefix, "-Wl,-rpath," + prefix, "-framework", fw]
    libdir = sysconfig.get_config_var("LIBDIR")
    ver = sysconfig.get_config_var("LDVERSION") or sysconfig.get_config_var("VERSION")
    return ["-I" + inc], ["-L" + libdir, "-Wl,-rpath," + libdir, "-lpython" + ver, "-lpthread"]


def test_bridge_init_finalize_race(tmp_path):
    cc = _cc()
    cflags, ldflags = _embed_flags()
    src = tmp_path / "harness.c"
    src.write_text(HARNESS)
    exe = tmp_path / "harness"
    build = subprocess.run([cc, "-O1", "-Wall", *cflags, "-I" + str(COMMON), "-o", str(exe), str(src),
                            str(COMMON / "pyxpo_bridge.c"), *ldflags], capture_output=True, text=True)
    if build.returncode != 0:
        if "pyxpo_bridge" in build.stderr:
            pytest.fail(build.stderr)
        pytest.skip("cannot link an embedded Python here: " + build.stderr[-300:])
    run = subprocess.run([str(exe), sys.base_prefix], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, (run.returncode, run.stdout, run.stderr)
    assert "delivered=" in run.stdout
