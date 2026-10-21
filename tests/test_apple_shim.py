import os
import sys

import pytest

from pyxpo._internal import apple


@pytest.fixture(autouse=True)
def no_ca_env(monkeypatch):
    # set first so monkeypatch records them and removes what install() sets
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


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


def test_ca_file_points_at_the_system_bundle(monkeypatch, tmp_path):
    ca = tmp_path / "cert.pem"
    ca.write_text("")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(apple, "MAC_CA_FILE", str(ca))
    apple.install()
    assert os.environ["SSL_CERT_FILE"] == str(ca)


def test_ca_file_keeps_the_app_choice(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(apple, "MAC_CA_FILE", str(tmp_path / "cert.pem"))
    monkeypatch.setenv("SSL_CERT_DIR", "/own/certs")
    apple.install()
    assert "SSL_CERT_FILE" not in os.environ


def test_ca_file_skipped_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(apple, "MAC_CA_FILE", str(tmp_path / "missing.pem"))
    apple.install()
    assert "SSL_CERT_FILE" not in os.environ
