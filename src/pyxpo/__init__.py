"""Pyxpo: React-Native-style mobile UI framework for Python.

The top-level namespace mirrors `react-native` (components, APIs, hooks); routing lives in `pyxpo.router`
(the `expo-router` equivalent) and icons in `pyxpo.vector_icons`.
"""
from __future__ import annotations

import os as _os

from .component import enable_registry as _enable_registry

if _os.environ.get("PYXPO_DEV_URL"):
    _enable_registry(True)  # keep Component identity across hot reloads; must run before app code

from .animated import Animated, Easing, use_animated_value
from .app import App, create_app, run_app
from .channel import Channel, LocalChannel
from .component import Component, ErrorBoundary, component, memo
from .element import Element

from .components.activity_indicator import ActivityIndicator
from .components.button import Button
from .components.image import Image, ImageBackground
from .components.keyboard_avoiding_view import KeyboardAvoidingView
from .components.lists import FlatList, SectionList, VirtualizedList
from .components.modal import Modal
from .components.picker import Picker
from .components.pressable import Pressable
from .components.refresh_control import RefreshControl
from .components.safe_area_view import SafeAreaView
from .components.scroll_view import ScrollView
from .components.slider import Slider
from .components.status_bar import StatusBar
from .components.switch import Switch
from .components.text import Text
from .components.text_input import TextInput
from .components.touchables import (TouchableHighlight, TouchableNativeFeedback, TouchableOpacity,
                                    TouchableWithoutFeedback)
from .components.view import View

from .apis.alert import Alert
from .apis.appearance import Appearance
from .apis.appstate import AppState
from .apis.back_handler import BackHandler
from .apis.clipboard import Clipboard
from .apis.share import Share
from .apis.dimensions import Dimensions
from .apis.i18n_manager import I18nManager
from .apis.keyboard import Keyboard
from .apis.linking import Linking
from .apis.pan_responder import PanResponder
from .apis.pixel_ratio import PixelRatio
from .apis.platform import Platform
from .apis.toast_android import ToastAndroid
from .apis.vibration import Vibration

from .style import StyleSheet, processColor
from .hooks import (HookError, createContext, create_context, use_async, use_callback, use_context, use_debug_value,
                    use_deferred_value, use_effect, use_id, use_imperative_handle, use_layout_effect, use_memo,
                    use_reducer, use_ref, use_state, use_sync_external_store, use_transition, use_color_scheme,
                    use_safe_area_frame, use_safe_area_insets, use_window_dimensions, useAsync, useCallback, useColorScheme, useContext,
                    useDebugValue, useDeferredValue, useEffect, useId, useImperativeHandle, useLayoutEffect, useMemo,
                    useReducer, useRef, useSafeAreaFrame, useSafeAreaInsets, useState, useSyncExternalStore, useTransition,
                    useWindowDimensions)

useAnimatedValue = use_animated_value

__version__ = "0.1.0"

__all__ = [
    # app
    "App", "create_app", "run_app", "Channel", "LocalChannel", "Component", "component", "memo", "Element",
    # components
    "View", "Text", "TextInput", "Image", "ImageBackground", "ScrollView", "FlatList", "SectionList",
    "VirtualizedList", "Pressable", "TouchableOpacity", "TouchableHighlight", "TouchableWithoutFeedback",
    "TouchableNativeFeedback", "Button", "Switch", "ActivityIndicator", "Modal", "KeyboardAvoidingView",
    "SafeAreaView", "StatusBar", "RefreshControl", "Picker", "Slider", "ErrorBoundary",
    # apis
    "Alert", "Animated", "Easing", "Appearance", "AppState", "BackHandler", "Clipboard", "Dimensions", "Share",
    "I18nManager", "Keyboard", "Linking", "PanResponder", "PixelRatio", "Platform", "StyleSheet", "ToastAndroid",
    "Vibration", "processColor",
    # hooks
    "HookError", "createContext", "create_context", "use_async", "use_callback", "use_context", "use_debug_value",
    "use_deferred_value", "use_effect", "use_id", "use_imperative_handle", "use_layout_effect", "use_memo",
    "use_reducer", "use_ref", "use_state", "use_sync_external_store", "use_transition", "use_color_scheme",
    "use_safe_area_frame", "use_safe_area_insets", "use_window_dimensions", "use_animated_value", "useAnimatedValue", "useAsync",
    "useCallback", "useColorScheme", "useContext", "useDebugValue", "useDeferredValue", "useEffect", "useId",
    "useImperativeHandle", "useLayoutEffect", "useMemo", "useReducer", "useRef", "useSafeAreaFrame", "useSafeAreaInsets", "useState",
    "useSyncExternalStore", "useTransition", "useWindowDimensions",
]


_MOVED = {"MediaLibrary": "media_library", "ImagePicker": "image_picker", "ImageTools": "image_tools", "ImageTooLargeError": "image_tools"}


def __getattr__(name: str):
    if name in _MOVED:
        mod = _MOVED[name]
        raise AttributeError(
            "pyxpo.%s moved to an optional module: add '%s' to [tool.pyxpo] modules and use "
            "`from pyxpo.modules.%s import %s`" % (name, mod.replace("_", "-"), mod, name)
        )
    raise AttributeError("module 'pyxpo' has no attribute %r" % name)
