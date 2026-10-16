"""Network state, IP address and connectivity changes: the expo-network API.

    import pyxpo_network as Network

    state = await Network.get_network_state_async()    # or Network.getNetworkStateAsync()
    state.type, state.is_connected, state.is_internet_reachable
    ip = await Network.get_ip_address_async()          # "192.168.1.20", or "0.0.0.0" without a network

    sub = Network.add_network_state_listener(lambda s: print(s.type))
    sub.remove()

    def Status():
        state = Network.use_network_state()            # re-renders on every change

On the desktop the state is a best guess (`UNKNOWN` or `NONE`) from whether the machine has a route out.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pyxpo.module_api import NotSupportedError, call, on_event, platform, require_linked, require_supported

__version__ = "0.1.0a1"

_EVENT = "Network.state"


class NetworkStateType(str, Enum):
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"
    CELLULAR = "CELLULAR"
    WIFI = "WIFI"
    BLUETOOTH = "BLUETOOTH"
    ETHERNET = "ETHERNET"
    WIMAX = "WIMAX"
    VPN = "VPN"
    OTHER = "OTHER"


_CAMEL = {"type": "type", "isConnected": "is_connected", "isInternetReachable": "is_internet_reachable"}


@dataclass(frozen=True)
class NetworkState:
    """`is_connected`: there is an active network. `is_internet_reachable`: the system checked that it reaches
    the internet. Either is None when unknown."""
    type: NetworkStateType = NetworkStateType.UNKNOWN
    is_connected: Optional[bool] = None
    is_internet_reachable: Optional[bool] = None

    def __getitem__(self, key: str) -> Any:
        if key not in _CAMEL:
            raise KeyError(key)
        return getattr(self, _CAMEL[key])

    def to_dict(self) -> Dict[str, Any]:
        """The state with Expo's camelCase keys; `type` is the plain string."""
        return {"type": self.type.value, "isConnected": self.is_connected, "isInternetReachable": self.is_internet_reachable}


def _state(raw: Dict[str, Any]) -> NetworkState:
    t = raw.get("type")
    kind = NetworkStateType(t) if t in NetworkStateType._value2member_map_ else NetworkStateType.UNKNOWN
    return NetworkState(kind, raw.get("isConnected"), raw.get("isInternetReachable"))


def _desktop_ip() -> Optional[str]:
    # A UDP connect picks the outgoing interface without sending anything.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        return None if ip.startswith("0.") else ip
    except OSError:
        return None
    finally:
        s.close()


def _native() -> bool:
    if platform() == "desktop":
        return False
    require_linked("Network", "network", package="pyxpo-network")
    return True


async def get_network_state_async() -> NetworkState:
    """The current network: its type, whether it is connected and whether the internet is reachable."""
    if not _native():
        up = _desktop_ip() is not None
        return NetworkState(NetworkStateType.UNKNOWN if up else NetworkStateType.NONE, up, None if up else False)
    return _state(await call("Network", "getState", reply=True) or {})


async def get_ip_address_async() -> str:
    """The device's IPv4 address on the active network, "0.0.0.0" when there is none."""
    if not _native():
        return _desktop_ip() or "0.0.0.0"
    return str(await call("Network", "getIpAddress", reply=True) or "0.0.0.0")


async def is_airplane_mode_enabled_async() -> bool:
    """Android: whether airplane mode is on. Raises `NotSupportedError` on iOS and the desktop."""
    require_supported("is_airplane_mode_enabled_async", ios=False)
    if not _native():
        raise NotSupportedError("is_airplane_mode_enabled_async needs Android")
    return bool(await call("Network", "isAirplaneModeEnabled", reply=True))


class Subscription:
    def __init__(self, fn: Callable[[NetworkState], Any]) -> None:
        self._fn: Optional[Callable[[NetworkState], Any]] = fn

    def remove(self) -> None:
        """Stops this listener. Safe to call twice."""
        if self._fn is None:
            return
        _listeners.remove(self._fn)
        self._fn = None
        if not _listeners:
            _stop()


_listeners: List[Callable[[NetworkState], Any]] = []
_off: Optional[Callable[[], None]] = None
_last: Optional[NetworkState] = None


def _on_state(raw: Any) -> None:
    global _last
    _last = _state(raw or {})
    for fn in list(_listeners):
        fn(_last)


def _stop() -> None:
    global _off, _last
    if _off is not None:
        _off()
        _off = None
        _last = None
        call("Network", "stopObserving")


def add_network_state_listener(listener: Callable[[NetworkState], Any]) -> Subscription:
    """Calls `listener(state)` on every network change, and once with the current state after the first
    listener starts. Returns a subscription; call `.remove()` to stop. No events on the desktop."""
    global _off
    _listeners.append(listener)
    if _off is None and _native():
        _off = on_event(_EVENT, _on_state)
        call("Network", "startObserving")
    return Subscription(listener)


def use_network_state() -> NetworkState:
    """The current network state; the component re-renders when it changes."""
    from pyxpo import use_effect, use_state
    state, set_state = use_state(lambda: _last or NetworkState())

    def subscribe() -> Callable[[], None]:
        sub = add_network_state_listener(set_state)
        if _last is not None:
            set_state(_last)
        return sub.remove

    use_effect(subscribe, [])
    return state


getNetworkStateAsync = get_network_state_async
getIpAddressAsync = get_ip_address_async
isAirplaneModeEnabledAsync = is_airplane_mode_enabled_async
addNetworkStateListener = add_network_state_listener
useNetworkState = use_network_state

__all__ = [
    "NetworkStateType", "NetworkState", "Subscription", "get_network_state_async", "get_ip_address_async",
    "is_airplane_mode_enabled_async", "add_network_state_listener", "use_network_state",
    "getNetworkStateAsync", "getIpAddressAsync", "isAirplaneModeEnabledAsync", "addNetworkStateListener",
    "useNetworkState",
]
