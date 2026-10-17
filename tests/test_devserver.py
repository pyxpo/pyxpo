from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from pyxpo.dev import server as srv
from pyxpo.dev.client import DevClient


def get(s, path, token="tok"):
    req = urllib.request.Request(s.url + path, headers={"X-Pyxpo-Token": token})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "POLL_TIMEOUT", 1.0)
    monkeypatch.setattr(srv, "SCAN_INTERVAL", 0.05)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n")
    s = srv.DevServer(str(tmp_path), port=0, token="tok")
    s.start()
    yield s, tmp_path
    s.stop()


def test_token_required(server):
    s, _ = server
    with pytest.raises(urllib.error.HTTPError) as e:
        get(s, "/poll?since=0&session=", token="bad")
    assert e.value.code == 403


def test_snapshot_then_change_then_delete(server):
    s, p = server
    snap = get(s, "/poll?since=0&session=")
    assert set(snap["files"]) == {"app/main.py"}
    (p / "app" / "main.py").write_text("x = 2\n")
    (p / "app" / "new.py").write_text("y = 1\n")
    upd = get(s, "/poll?since=%d&session=%s" % (snap["version"], snap["session"]))
    assert set(upd["files"]) == {"app/main.py", "app/new.py"}
    (p / "app" / "new.py").unlink()
    upd2 = get(s, "/poll?since=%d&session=%s" % (upd["version"], upd["session"]))
    assert upd2["deleted"] == ["app/new.py"]


def test_idle_poll_times_out_empty(server):
    s, _ = server
    snap = get(s, "/poll?since=0&session=")
    t = time.monotonic()
    idle = get(s, "/poll?since=%d&session=%s" % (snap["version"], snap["session"]))
    assert idle["files"] == {} and time.monotonic() - t >= 0.9


def test_client_hands_update_to_loop(server):
    s, p = server

    class Loop:
        got = []

        def call_soon_threadsafe(self, fn, upd):
            self.got.append(upd)

    loop = Loop()
    c = DevClient(type("R", (), {"apply": lambda self, u: None})(), loop, s.url, "tok")
    c.poll_once()
    assert loop.got and "app/main.py" in loop.got[0]["files"]


def test_post_reload_triggers_full_reload(server):
    s, _ = server
    calls = []

    class Loop:
        def call_soon_threadsafe(self, fn, *a):
            fn(*a)

    class Reloader:
        apply = staticmethod(lambda upd: calls.append("apply"))
        reload_all = staticmethod(lambda: calls.append("reload"))

    c = DevClient(Reloader, Loop(), s.url, "tok")
    c.poll_once()
    assert calls == ["apply"]
    del calls[:]
    req = urllib.request.Request(s.url + "/reload", data=b"", method="POST", headers={"X-Pyxpo-Token": "tok"})
    assert urllib.request.urlopen(req, timeout=5).status == 204
    c.poll_once()
    assert calls == ["reload"]


def test_polled_set_only_by_authorised_poll(server):
    s, _ = server
    assert not s.polled.is_set()
    with pytest.raises(urllib.error.HTTPError):
        get(s, "/poll?since=0&session=", token="bad")
    assert not s.polled.is_set()
    get(s, "/poll?since=0&session=")
    assert s.polled.is_set()


def test_native_config_change_warns(tmp_path, capsys):
    (tmp_path / "app").mkdir()
    (tmp_path / "pyproject.toml").write_text('[tool.pyxpo]\nname = "A"\n')
    s = srv.DevServer(str(tmp_path), port=0, token="tok")
    try:
        s._tick()
        assert "native config changed" not in capsys.readouterr().err
        (tmp_path / "pyproject.toml").write_text('[tool.pyxpo]\nname = "B"\n')
        (tmp_path / "app_config.py").write_text("def config(c): return c\n")
        s._tick()
        err = capsys.readouterr().err
        assert "native config changed (app_config.py, pyproject.toml)" in err
        s._tick()
        assert "native config changed" not in capsys.readouterr().err  # warned once per change
    finally:
        s.httpd.server_close()


def test_client_does_not_need_urllib_request():
    # The Mac (Catalyst) Python has no _scproxy, so `import urllib.request` fails there.
    import subprocess
    import sys
    code = "import sys; sys.modules['urllib.request'] = None; import pyxpo.dev.client"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_client_rejects_bad_token(server):
    s, _ = server
    c = DevClient(None, None, s.url, "wrong")
    with pytest.raises(OSError):
        c.poll_once()
