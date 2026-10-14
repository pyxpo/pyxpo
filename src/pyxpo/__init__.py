"""Pyxpo: Python-first mobile UI framework."""
from __future__ import annotations

import os as _os

from .component import enable_registry as _enable_registry

if _os.environ.get("PYXPO_DEV_URL"):
    _enable_registry(True)  # keep Component identity across hot reloads; must run before app code

from .app import App, create_app, run_app
from .channel import Channel, LocalChannel
from .component import Component, component
from .element import Button, Element, Image, ScrollView, Text, TextInput, View
from .hooks import (HookError, create_context, use_async, use_callback, use_context, use_effect, use_memo,
                    use_ref, use_state)

__version__ = "0.1.0"

__all__ = [
    "App", "create_app", "run_app", "Channel", "LocalChannel", "Component", "component", "Element",
    "View", "Text", "Button", "Image", "TextInput", "ScrollView", "HookError", "create_context",
    "use_async", "use_callback", "use_context", "use_effect", "use_memo", "use_ref", "use_state",
]
