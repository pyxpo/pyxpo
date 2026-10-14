"""Pyxpo: Python-first mobile UI framework."""
from __future__ import annotations

import os as _os

from .component import enable_registry as _enable_registry

if _os.environ.get("PYXPO_DEV_URL"):
    _enable_registry(True)  # keep Component identity across hot reloads; must run before app code

from .app import App, create_app, run_app
from .channel import Channel, LocalChannel
from .component import Component, component
from .modules import Alert, Clipboard, Keyboard, Linking, Vibration
from .element import Button, Element, Image, ScrollView, Text, TextInput, View
from .ui import Checkbox, KeyboardAvoidingView, Pressable, SafeArea, Switch
from .env import (Dimensions, Platform, PixelRatio, responsive, use_breakpoint, use_color_scheme, use_keyboard,
                  use_orientation, use_responsive, use_safe_area_insets, use_window_dimensions)
from .style import StyleSheet, parse_color
from .hooks import (HookError, create_context, use_async, use_callback, use_context, use_effect, use_memo,
                    use_ref, use_state)

__version__ = "0.1.0"

__all__ = [
    "App", "create_app", "run_app", "Channel", "LocalChannel", "Component", "component", "Element",
    "Alert", "Clipboard", "Keyboard", "Linking", "Vibration", "SafeArea", "KeyboardAvoidingView", "Pressable", "Switch", "Checkbox", "View", "Text", "Button", "Image", "TextInput", "ScrollView", "HookError", "create_context",
    "StyleSheet", "parse_color", "Dimensions", "Platform", "PixelRatio", "responsive", "use_breakpoint",
    "use_color_scheme", "use_keyboard", "use_orientation", "use_responsive", "use_safe_area_insets",
    "use_window_dimensions", "use_async", "use_callback", "use_context", "use_effect", "use_memo", "use_ref", "use_state",
]
