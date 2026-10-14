from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional


class Channel(ABC):
    """Python <-> native transport. Both directions carry JSON strings."""

    @abstractmethod
    def post(self, payload: str) -> None:
        """Send an ops batch to native."""

    @abstractmethod
    def set_event_handler(self, fn: Callable[[str], None]) -> None:
        """Register the Python function that receives native events."""


class LocalChannel(Channel):
    """In-process channel connecting an App to a renderer (mock/console)."""

    def __init__(self) -> None:
        self._native: Optional[Callable[[str], None]] = None
        self._events: Optional[Callable[[str], None]] = None

    def post(self, payload: str) -> None:
        if self._native is None:
            raise RuntimeError("no renderer attached to LocalChannel")
        self._native(payload)

    def set_event_handler(self, fn: Callable[[str], None]) -> None:
        self._events = fn

    def set_native_handler(self, fn: Callable[[str], None]) -> None:
        self._native = fn

    def emit_event(self, payload: str) -> None:
        if self._events is None:
            raise RuntimeError("no app attached to LocalChannel")
        self._events(payload)
