# pyxpo-network

Network state, IP address and connectivity changes for [pyxpo](https://github.com/pyxpo/pyxpo) apps. The
API follows [expo-network](https://docs.expo.dev/versions/latest/sdk/network/).

```sh
pip install pyxpo-network
```

```toml
[tool.pyxpo]
modules = ["network"]
```

```python
import pyxpo_network as Network

state = await Network.get_network_state_async()
print(state.type, state.is_connected, state.is_internet_reachable)   # NetworkStateType.WIFI True True
print(await Network.get_ip_address_async())                          # 192.168.1.20

sub = Network.add_network_state_listener(lambda s: print("now", s.type))
sub.remove()


def OfflineBanner():
    state = Network.use_network_state()     # re-renders on every change
    if state.is_connected is False:
        return Text("You are offline")
```

Every name also has its expo-network spelling (`Network.getNetworkStateAsync`, `Network.useNetworkState`).
`NetworkState` accepts Expo's camelCase keys too (`state["isInternetReachable"]`), and `to_dict()` gives the
camelCase dict.

## Functions

| Function | Returns | Platforms |
| --- | --- | --- |
| `get_network_state_async()` | `NetworkState` | all |
| `get_ip_address_async()` | `str`, the IPv4 address; `"0.0.0.0"` without a network | all |
| `is_airplane_mode_enabled_async()` | `bool` | Android |
| `add_network_state_listener(fn)` | `Subscription` with `.remove()`. `fn(state)` runs on every change, and once with the current state when the first listener starts. | iOS, Android |
| `use_network_state()` | `NetworkState`, updated on change | iOS, Android |

## `NetworkState`

| Field | Notes |
| --- | --- |
| `type` | `NetworkStateType`: `NONE`, `UNKNOWN`, `CELLULAR`, `WIFI`, `BLUETOOTH`, `ETHERNET`, `WIMAX`, `VPN`, `OTHER`. |
| `is_connected` | There is an active network. |
| `is_internet_reachable` | Android: the system validated internet access. iOS: the path is satisfied. |

## Platforms

- iOS 15+: `NWPathMonitor` and `getifaddrs`.
- Android 7 (API 24)+: `ConnectivityManager`. Adds the `ACCESS_NETWORK_STATE` permission (granted at install).
- Desktop: `UNKNOWN` when the machine has a route out, else `NONE`. No change events.
