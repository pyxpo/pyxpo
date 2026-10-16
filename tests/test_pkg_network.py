"""pyxpo-network: expo-network API, the state listener and the desktop fallback."""
import asyncio

import pytest

from pyxpo.module_api import NotSupportedError, dispatch
from pyxpo.module_testing import FakeBridge

import pyxpo_network as Network


def run(coro):
    return asyncio.run(coro)


WIFI = {"type": "WIFI", "isConnected": True, "isInternetReachable": True}


def test_desktop():
    state = run(Network.get_network_state_async())
    assert state.type in (Network.NetworkStateType.UNKNOWN, Network.NetworkStateType.NONE)
    assert state.is_connected == (state.type == Network.NetworkStateType.UNKNOWN)
    ip = run(Network.getIpAddressAsync())
    assert ip.count(".") == 3
    with pytest.raises(NotSupportedError):
        run(Network.is_airplane_mode_enabled_async())
    sub = Network.add_network_state_listener(lambda s: None)  # no events on the desktop
    sub.remove()
    sub.remove()


def test_native_calls():
    with FakeBridge("android") as fb:
        fb.on("Network", "getState", lambda: WIFI)
        fb.on("Network", "getIpAddress", lambda: "10.0.2.16")
        fb.on("Network", "isAirplaneModeEnabled", lambda: False)
        state = run(Network.get_network_state_async())
        assert state == Network.NetworkState(Network.NetworkStateType.WIFI, True, True)
        assert state["isInternetReachable"] is True and state.to_dict() == WIFI
        assert run(Network.get_ip_address_async()) == "10.0.2.16"
        assert run(Network.isAirplaneModeEnabledAsync()) is False
    with FakeBridge("ios") as fb:
        fb.on("Network", "getState", lambda: {"type": "SATELLITE", "isConnected": True})
        state = run(Network.get_network_state_async())
        assert state.type is Network.NetworkStateType.UNKNOWN and state.is_internet_reachable is None
        with pytest.raises(NotSupportedError):
            run(Network.is_airplane_mode_enabled_async())
        assert fb.calls == [("Network", "getState", ())]


def test_listener_starts_once_and_stops_with_last():
    with FakeBridge("ios") as fb:
        fb.on("Network", "startObserving", lambda: None)
        fb.on("Network", "stopObserving", lambda: None)
        got_a, got_b = [], []
        a = Network.add_network_state_listener(got_a.append)
        b = Network.addNetworkStateListener(got_b.append)
        dispatch({"name": "Network.state", "data": WIFI})
        assert got_a[0].type is Network.NetworkStateType.WIFI and len(got_b) == 1
        a.remove()
        dispatch({"name": "Network.state", "data": {"type": "NONE", "isConnected": False, "isInternetReachable": False}})
        assert len(got_a) == 1 and got_b[-1].is_connected is False
        b.remove()
        dispatch({"name": "Network.state", "data": WIFI})
        assert len(got_b) == 2
        assert [c[1] for c in fb.calls] == ["startObserving", "stopObserving"]


def test_not_linked():
    from pyxpo.module_api import ModuleNotLinkedError
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            run(Network.get_network_state_async())
