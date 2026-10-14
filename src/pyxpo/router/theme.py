"""Navigation theme (react-navigation / expo-router `ThemeProvider`, `DefaultTheme`, `DarkTheme`)."""
from __future__ import annotations

from typing import Any, Dict

from ..hooks import create_context, use_color_scheme, use_context

DefaultTheme: Dict[str, Any] = {
    "dark": False,
    "colors": {"primary": "rgb(0, 122, 255)", "background": "rgb(242, 242, 242)", "card": "rgb(255, 255, 255)",
               "text": "rgb(28, 28, 30)", "border": "rgb(216, 216, 216)", "notification": "rgb(255, 59, 48)"},
}
DarkTheme: Dict[str, Any] = {
    "dark": True,
    "colors": {"primary": "rgb(10, 132, 255)", "background": "rgb(1, 1, 1)", "card": "rgb(18, 18, 18)",
               "text": "rgb(229, 229, 231)", "border": "rgb(39, 39, 41)", "notification": "rgb(255, 69, 58)"},
}

_ThemeContext = create_context(None)
ThemeProvider = _ThemeContext.Provider


def useTheme() -> Dict[str, Any]:
    """Theme from the nearest ThemeProvider; without one, DefaultTheme/DarkTheme by device color scheme."""
    theme = use_context(_ThemeContext)
    scheme = use_color_scheme()
    if theme is not None:
        return theme
    return DarkTheme if scheme == "dark" else DefaultTheme


use_theme = useTheme
