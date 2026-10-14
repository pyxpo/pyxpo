import sys

import pytest


@pytest.fixture
def tmp_app(tmp_path):
    """Write an `app/` package from {relative path: source}; yields its directory."""
    def make(files):
        root = tmp_path / "app"
        root.mkdir(exist_ok=True)
        (root / "__init__.py").write_text("")
        for rel, src in files.items():
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(src)
        if str(tmp_path) not in sys.path:
            sys.path.insert(0, str(tmp_path))
        return str(root)
    yield make
    for k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[k]
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


@pytest.fixture(autouse=True)
def _reset_globals():
    from pyxpo.apis.back_handler import _Back
    from pyxpo.router import router
    yield
    _Back.handlers.clear()
    router._bind(None)
