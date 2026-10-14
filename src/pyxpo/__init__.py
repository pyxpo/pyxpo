"""Pyxpo: Python-first mobile UI framework."""
from __future__ import annotations

import os as _os

from .component import enable_registry as _enable_registry

if _os.environ.get("PYXPO_DEV_URL"):
    _enable_registry(True)  # keep Component identity across hot reloads; must run before app code

from .animated import Animated, Easing, use_animated_value
from .app import App, create_app, run_app
from .channel import Channel, LocalChannel
from .component import Component, component, memo
from .modules import Clipboard, Keyboard, Linking, Picker, StatusBar, Toast, Vibration
from .element import Button, Element, Image, Path, ScrollView, Text, TextInput, View
from .theme import ThemeProvider, create_theme, dark_theme, light_theme, use_theme
from .kit import AppButton, Avatar, Badge, Card, Divider, Field, ListItem, ProgressBar, Screen, Typography
from .widgets import (Alert, Chip, DatePicker, Dropdown, Icon, InputField, LabeledCheckbox, MultiSelect, NumberInput,
                      PasswordInput, Radio, RadioGroup, SearchInput, Sheet, Stepper, TabBar, TextArea, TimePicker)
from .navigation import Drawer, Navigation, Stack, Tabs, TopTabs, use_navigation
from .scroll import FlatList, ScrollRef, use_scroll_ref
from .ui import (ActivityIndicator, Checkbox, Gesture, KeyboardAvoidingView, Modal, Pressable, SafeArea, Slider, Switch,
                 use_pan_responder)
from .env import (Dimensions, Platform, PixelRatio, responsive, use_breakpoint, use_color_scheme, use_keyboard,
                  use_orientation, use_responsive, use_safe_area_insets, use_window_dimensions)
from .style import StyleSheet, parse_color
from .hooks import (HookError, create_context, use_async, use_callback, use_context, use_effect, use_memo,
                    use_ref, use_state)

__version__ = "0.1.0"

__all__ = [
    "Animated", "Easing", "use_animated_value",
    "App", "create_app", "run_app", "Channel", "LocalChannel", "Component", "component", "memo", "Element",
    "Alert", "Picker", "Toast", "StatusBar", "Clipboard", "Keyboard", "Linking", "Vibration", "FlatList", "ScrollRef", "use_scroll_ref", "SafeArea", "KeyboardAvoidingView", "Navigation", "Stack", "Tabs", "TopTabs", "Drawer", "use_navigation", "Modal", "Slider", "Gesture", "use_pan_responder", "Pressable", "Switch", "Checkbox", "ActivityIndicator", "View", "Text", "Button", "Image", "Path", "TextInput", "ScrollView", "HookError", "create_context",
    "Alert", "Chip", "DatePicker", "Dropdown", "Icon", "InputField", "LabeledCheckbox", "MultiSelect", "NumberInput", "PasswordInput", "Radio", "RadioGroup", "SearchInput", "Sheet", "Stepper", "TabBar", "TextArea", "TimePicker",
    "ThemeProvider", "create_theme", "dark_theme", "light_theme", "use_theme", "AppButton", "Avatar", "Badge", "Card", "Divider", "Field", "ListItem", "ProgressBar", "Screen", "Typography",
    "StyleSheet", "parse_color", "Dimensions", "Platform", "PixelRatio", "responsive", "use_breakpoint",
    "use_color_scheme", "use_keyboard", "use_orientation", "use_responsive", "use_safe_area_insets",
    "use_window_dimensions", "use_async", "use_callback", "use_context", "use_effect", "use_memo", "use_ref", "use_state",
]
