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
