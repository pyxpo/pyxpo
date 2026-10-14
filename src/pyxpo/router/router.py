"""The imperative `router` object (expo-router): works anywhere once the app has mounted."""
from __future__ import annotations

from typing import Any, Optional

from .matching import Href
from .store import Store


class Router:
    def __init__(self) -> None:
        self._store: Optional[Store] = None

    def _bind(self, store: Optional[Store]) -> None:
        self._store = store

    @property
    def _s(self) -> Store:
        if self._store is None:
            raise RuntimeError("router is not ready: call it after the app has mounted")
        return self._store

    def push(self, href: Href) -> None:
        self._s.push(href)

    def navigate(self, href: Href) -> None:
        self._s.navigate(href)

    def replace(self, href: Href) -> None:
        self._s.replace(href)

    def back(self) -> None:
        self._s.back()

    def canGoBack(self) -> bool:
        return self._s.can_go_back()

    def dismiss(self, count: int = 1) -> None:
        self._s.dismiss(count)

    def dismissTo(self, href: Href) -> None:
        self._s.dismiss_to(href)

    def dismissAll(self) -> None:
        self._s.dismiss_all()

    def canDismiss(self) -> bool:
        return self._s.can_dismiss()

    def setParams(self, params: Any) -> None:
        self._s.set_params(params)

    can_go_back, dismiss_to, dismiss_all = canGoBack, dismissTo, dismissAll
    can_dismiss, set_params = canDismiss, setParams


router = Router()
