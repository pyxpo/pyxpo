import sys

from pyxpo._internal import apple


def test_scproxy_stand_in_when_missing(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delitem(sys.modules, "_scproxy", raising=False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def no_scproxy(name, *args, **kwargs):
        if name == "_scproxy":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_scproxy)
    apple.install()
    monkeypatch.setattr("builtins.__import__", real_import)
    mod = sys.modules["_scproxy"]
    assert mod._get_proxies() == {}
    assert mod._get_proxy_settings() == {"exclude_simple": False, "exceptions": ()}
    monkeypatch.delitem(sys.modules, "_scproxy")


def test_scproxy_left_alone_off_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delitem(sys.modules, "_scproxy", raising=False)
    apple.install()
    assert "_scproxy" not in sys.modules
