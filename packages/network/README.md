# pyxpo-network

Network state, IP address and connectivity changes for [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in
Python: is the phone online, over what, what is its IP address, and a live feed when that changes. The names follow
[expo-network](https://docs.expo.dev/versions/latest/sdk/network/), in Python style.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-network/main/docs/images/hero.png" width="820" alt="The network module on Android and iOS: online badge, connection type, reachability and IP address">
</p>

```python
import pyxpo_network as Network

state = await Network.get_network_state_async()
print(state.type, state.is_connected, state.is_internet_reachable)    # NetworkStateType.WIFI True True
print(await Network.get_ip_address_async())                           # "192.168.1.20"
```

## Features

- **One snapshot:** `get_network_state_async()` gives the type (Wi-Fi, cellular, VPN, ...), whether there is an
  active network and whether the internet is reachable.
- **Live updates:** `add_network_state_listener(fn)` and the `use_network_state()` hook, so a banner follows the
  connection.
- **IP address:** the IPv4 address on the active network, or `"0.0.0.0"` when there is none.
- **Airplane mode:** `is_airplane_mode_enabled_async()` on Android.
- **Light permission:** Android adds `ACCESS_NETWORK_STATE`, which is granted at install. iOS needs nothing.
- **Desktop fallback:** a best guess from whether the machine has a route out.
- **Typed:** ships `py.typed`. Every name also has its expo spelling (`Network.getNetworkStateAsync`).

## Contents

| If you are... | Start here |
| --- | --- |
| Showing an offline banner | [Quick start](#quick-start) |
| Checking once before an upload | [A snapshot](#a-snapshot) |
| Reacting to changes outside components | [Listening for changes](#listening-for-changes) |
| Reading the IP address | [IP address](#ip-address) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: queue writes while offline](#recipe-queue-writes-while-offline) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | All functions, through `ConnectivityManager`. `is_internet_reachable` is the system's validation of the network. |
| iOS 15+ | `get_network_state_async`, `get_ip_address_async`, listener and hook, through `NWPathMonitor` and `getifaddrs`. `is_airplane_mode_enabled_async` raises `NotSupportedError`. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`) | State and IP are a best guess. No change events, so the listener never fires. |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-network
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["network"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`).

## Quick start

```python
import pyxpo_network as Network
from pyxpo import Text, View, component


@component
def OfflineBanner():
    state = Network.use_network_state()          # re-renders on every change
    if state.is_connected is False:
        return View(Text("You are offline"))
    return View(Text("Online over %s" % state.type.value))
```

> **Tip:** `is_connected` and `is_internet_reachable` can each be `None` while the system is still working it out.
> Test `is False` for "offline", not `not state.is_connected`, so a moment of "unknown" does not flash a banner.

## A snapshot

```python
state = await Network.get_network_state_async()
if state.type == Network.NetworkStateType.CELLULAR:
    ...   # ask before a big download
```

| Field | Notes |
| --- | --- |
| `type` | `NetworkStateType`: `NONE`, `UNKNOWN`, `CELLULAR`, `WIFI`, `BLUETOOTH`, `ETHERNET`, `WIMAX`, `VPN`, `OTHER`. |
| `is_connected` | There is an active network. |
| `is_internet_reachable` | Android: the system validated internet access (a captive portal gives `False`). iOS: the path is satisfied. |

`NetworkState` is a frozen dataclass. `state["isConnected"]` works with Expo's camelCase keys and `state.to_dict()`
gives `{"type": "WIFI", "isConnected": True, "isInternetReachable": True}`.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-network/main/docs/images/state.png" width="720" alt="The network state fields on Android and iOS">
</p>

The Android emulator reports Wi-Fi (`10.0.2.16`). The iOS Simulator shares the Mac's network and here reported `VPN`
with address `192.0.0.3`, which is what its network stack exposed on this Mac. A real phone shows its real network.

## Listening for changes

```python
def on_change(state):
    print("now", state.type)

sub = Network.add_network_state_listener(on_change)
...
sub.remove()                       # safe to call twice
```

The listener is called on every change and once with the current state when the first listener starts. The native
observer runs only while at least one listener exists, and stops when the last one is removed.

Inside a component, `use_network_state()` does the subscribe and the cleanup for you.

## IP address

```python
ip = await Network.get_ip_address_async()      # "192.168.1.20", or "0.0.0.0"
```

It is the IPv4 address on the active network. It is a local address, not your public one. Use a server call to learn
the public address.

## Airplane mode

```python
if Platform.OS == "android":
    airplane = await Network.is_airplane_mode_enabled_async()
```

Android only. It raises `NotSupportedError` on iOS, which has no API for it.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `NotSupportedError` | `is_airplane_mode_enabled_async()` on iOS, or on the desktop. | Guard with `Platform.OS == "android"`. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | The app was built without `"network"` in `modules`. | Add it and rebuild. |

## Config

There are no module options and no config plugin. The only setup is the `modules` entry. On Android the module adds
`ACCESS_NETWORK_STATE` to the manifest for you.

## Web and desktop

The desktop host has no connectivity API, so:

| Call | Desktop result |
| --- | --- |
| `get_network_state_async()` | `UNKNOWN` with `is_connected=True` when the machine has a route out, else `NONE` with `is_connected=False`. `is_internet_reachable` is `None` when up. |
| `get_ip_address_async()` | The address of the interface that would be used to go out, else `"0.0.0.0"`. |
| `add_network_state_listener` | Accepted, never called. |
| `is_airplane_mode_enabled_async()` | Raises `NotSupportedError`. |

## Recipe: queue writes while offline

Keep edits in a list while offline and flush them when the connection returns.

```python
import pyxpo_network as Network
from pyxpo import Text, View, component, use_async, use_state


async def send(item) -> None:
    ...                                        # your own upload


@component
def Notes():
    state = Network.use_network_state()
    queue, set_queue = use_state(["note 1", "note 2"])
    online = state.is_connected is not False

    async def flush():
        if online and queue:
            items = list(queue)
            set_queue([])
            for item in items:
                try:
                    await send(item)
                except Exception:
                    set_queue(lambda q: q + [item])     # keep it for the next time

    use_async(flush, [online])                 # runs again when `online` changes
    return View(Text("Pending: %d" % len(queue)), Text("Online" if online else "Offline"))
```

`send` is a placeholder for your own upload.

## Production checklist

- [ ] "Offline" is shown only when `is_connected is False`, not on `None`.
- [ ] A network call that fails is handled even when `is_connected` is `True`. The state is a hint, not a promise.
- [ ] Large downloads ask before using `CELLULAR`.
- [ ] A listener you add outside a component is removed when you are done with it.
- [ ] `is_airplane_mode_enabled_async` is guarded with `Platform.OS`.

## Testing

Replace the getters with fakes:

```python
import asyncio

import pyxpo_network as Network


def test_cellular_warning(monkeypatch):
    async def fake():
        return Network.NetworkState(Network.NetworkStateType.CELLULAR, True, True)

    monkeypatch.setattr(Network, "get_network_state_async", fake)
    state = asyncio.run(Network.get_network_state_async())
    assert state.type == Network.NetworkStateType.CELLULAR
```

To test a listener, call the registered function yourself with a `NetworkState`. On the desktop test host the real
function returns `UNKNOWN` or `NONE`, so a UI test of the offline banner can also be done by faking the hook.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `is_internet_reachable` is `False` on Wi-Fi | Android: a captive portal or a network with no route out. Open the sign-in page. |
| The iOS Simulator shows `VPN` and `192.0.0.3` | The Simulator reports what the Mac's network stack exposes. Use a real iPhone for real values. |
| The listener never fires on the desktop | There are no change events there. |
| `get_ip_address_async` gives `"0.0.0.0"` | There is no network, or only IPv6. The module returns IPv4. |
| `NotSupportedError` for airplane mode | It is Android only. |
| `ModuleNotLinkedError` | Add `"network"` to `modules` and rebuild. |

## FAQ

**Is `is_connected` the same as "the internet works"?** No. Use `is_internet_reachable` for that, and still handle a
failed request.

**Can I see the Wi-Fi name?** No. This module reports the type, not the SSID.

**Does the hook cost battery?** The native observer is a system callback. It runs only while a listener exists.

**IPv6?** `get_ip_address_async` returns IPv4 only.

## API reference

### Functions

| Function (expo name) | Platforms | Returns |
| --- | --- | --- |
| `get_network_state_async()` (`getNetworkStateAsync`) | all | `NetworkState` |
| `get_ip_address_async()` (`getIpAddressAsync`) | all | `str` |
| `is_airplane_mode_enabled_async()` (`isAirplaneModeEnabledAsync`) | Android | `bool` |
| `add_network_state_listener(listener)` (`addNetworkStateListener`) | iOS, Android | `Subscription` |
| `use_network_state()` (`useNetworkState`) | iOS, Android | `NetworkState` |

### Types

| Name | Description |
| --- | --- |
| `NetworkState` | `type`, `is_connected`, `is_internet_reachable`, `to_dict()`, `state["camelKey"]`. |
| `NetworkStateType` | `str` enum: `NONE`, `UNKNOWN`, `CELLULAR`, `WIFI`, `BLUETOOTH`, `ETHERNET`, `WIMAX`, `VPN`, `OTHER`. |
| `Subscription` | `.remove()` stops the listener. |

## License

MIT
