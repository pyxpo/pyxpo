"""Every bundled icon path parses and stays inside the 24x24 box."""
import pytest

from pyxpo.vector_icons import PATHS, Feather, parse_path


@pytest.mark.parametrize("name", sorted(PATHS))
def test_path_parses_inside_the_box(name):
    segments = parse_path(PATHS[name])
    assert segments
    points = [v for s in segments for v in s]
    assert all(-0.5 <= v <= 24.5 for v in points), name


def test_app_icons_exist():
    for name in ("archive", "key", "monitor", "phone", "puzzle", "sparkles"):
        assert name in Feather.glyphMap
