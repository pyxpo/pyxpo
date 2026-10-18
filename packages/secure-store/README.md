# pyxpo-secure-store

Encrypted key-value storage for secrets in [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in Python: sign-in
tokens, API keys and PINs in the iOS Keychain or the Android Keystore, with an optional Face ID, Touch ID or
fingerprint check. The names follow [expo-secure-store](https://docs.expo.dev/versions/latest/sdk/securestore/), in
Python style.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/secure-store/docs/images/hero.png" width="820" alt="The secure store module on Android and iOS: a token saved, then read back">
</p>

```python
import pyxpo_secure_store as SecureStore

await SecureStore.set_item_async("session_token", "tok_8f2c41d9")
token = await SecureStore.get_item_async("session_token")      # "tok_8f2c41d9", or None
await SecureStore.delete_item_async("session_token")
```

## Features

- **Real encryption:** iOS keeps values in the Keychain. Android encrypts them with an AES-256-GCM key that never
  leaves the Android Keystore, and keeps the ciphertext in the app's private `SharedPreferences`.
- **Biometric lock:** `requireAuthentication` asks for Face ID, Touch ID or a fingerprint before a value is read
  (and, on Android, written).
- **Small, string-only API:** `get_item_async`, `set_item_async`, `delete_item_async`, plus two helpers that tell
  you what the device can do.
- **Checked input:** keys and option names are validated, and a value that is not a string raises `TypeError` with a
  hint to use `json.dumps`.
- **Keychain control (iOS):** accessibility class, service name and access group.
- **Desktop fallback:** an in-memory dict, so tests and previews run without a phone. It is not encrypted.
- **Typed:** ships `py.typed`. Every name also has its expo spelling (`SecureStore.setItemAsync`).

## Contents

| If you are... | Start here |
| --- | --- |
| Saving a login token | [Quick start](#quick-start) |
| Protecting a value with Face ID or a fingerprint | [Biometric lock](#biometric-lock) |
| Choosing when the Keychain releases a value | [Options](#options) |
| Wondering what survives a reinstall | [Where the data lives](#where-the-data-lives) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: keep a user signed in](#recipe-keep-a-user-signed-in) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Get, set, delete. Encryption with an Android Keystore key. `requireAuthentication` needs Android 10 or newer. |
| iOS 15+ | Get, set, delete in the Keychain, with `keychainAccessible`, `keychainService` and `accessGroup`. Face ID or Touch ID with `requireAuthentication`. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`) | An in-memory dict that is lost when the process ends. `is_available_async()` is `False`. Nothing is encrypted. |

Requires Python 3.9+ and `pyxpo>=0.1.0a1`.

## Install

```sh
pip install pyxpo-secure-store
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["secure-store"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`). On Android it
adds the `USE_BIOMETRIC` permission (granted at install). On iOS it adds the `NSFaceIDUsageDescription` key to
`Info.plist`. Change its text with a module option:

```toml
[tool.pyxpo.module_options.secure-store]
faceIDPermission = "Use Face ID to unlock your saved sign-in details."
```

## Quick start

```python
import pyxpo_secure_store as SecureStore
from pyxpo import Pressable, Text, View, component, use_state


@component
def Token():
    shown, set_shown = use_state("nothing yet")

    async def save():
        await SecureStore.set_item_async("session_token", "tok_8f2c41d9")
        set_shown("saved")

    async def read():
        set_shown(await SecureStore.get_item_async("session_token") or "no token")

    return View(
        Pressable(Text("Save"), on_press=save),
        Pressable(Text("Read"), on_press=read),
        Text(shown),
    )
```

> **Tip:** keep only secrets here: tokens, keys, PINs. Values should be small, a few KB at most. Use
> `pyxpo-storage` for ordinary settings and `pyxpo-file-system` for bulk data. A real token is shown above only as a
> dummy value.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/secure-store/docs/images/read.png" width="720" alt="Save and read on Android and iOS">
</p>

## Reading, writing and deleting

```python
await SecureStore.set_item_async("token", "abc")         # replaces what "token" held
value = await SecureStore.get_item_async("token")        # "abc", or None when missing
await SecureStore.delete_item_async("token")             # no error when it does not exist
```

| Function | Returns | Notes |
| --- | --- | --- |
| `set_item_async(key, value, options=None)` | `None` | `value` must be a `str`. Use `json.dumps` for anything else. |
| `get_item_async(key, options=None)` | `str` or `None` | May show the biometric prompt (see below). |
| `delete_item_async(key, options=None)` | `None` | Safe when the key is missing. |
| `is_available_async()` | `bool` | `True` on a phone with the module linked, `False` on the desktop. |
| `can_use_biometric_authentication_async()` | `bool` | `True` when biometrics are enrolled, so `requireAuthentication` items work. |

Keys may use letters, digits, `.`, `-` and `_`. Anything else raises `ValueError`. Pass the same `options`
(especially `keychainService`) when you read, write and delete one item.

## Biometric lock

```python
if await SecureStore.can_use_biometric_authentication_async():
    await SecureStore.set_item_async("pin", "1234", {
        "requireAuthentication": True,
        "authenticationPrompt": "Unlock your PIN",
    })

pin = await SecureStore.get_item_async("pin", {"requireAuthentication": True,
                                               "authenticationPrompt": "Unlock your PIN"})
```

The system shows Face ID, Touch ID or the fingerprint sheet with your `authenticationPrompt` text. If the user
cancels, the call raises an error (see [Errors](#errors)) and you get no value. The screenshots in this README do not
show the biometric prompt, because an emulator or simulator has no enrolled face or finger by default.

## Options

All keys are optional. An unknown key raises `ValueError`.

| Option | Default | Platform | Meaning |
| --- | --- | --- | --- |
| `keychainService` | `"app"` | both | A namespace. Items with different services do not clash. Letters, digits, `.`, `-`, `_`. |
| `requireAuthentication` | `False` | both | Ask for biometrics before the value is read (Android: also when written). |
| `authenticationPrompt` | `""` | both | The text in the biometric prompt. |
| `keychainAccessible` | `WHEN_UNLOCKED` | iOS | When the Keychain gives the value out. One of the constants below. |
| `accessGroup` | `""` | iOS | A Keychain access group, to share items between your own apps. |

`keychainAccessible` constants (the same numbers as expo-secure-store):

| Constant | Value |
| --- | --- |
| `AFTER_FIRST_UNLOCK` | 0 |
| `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY` | 1 |
| `ALWAYS` | 2 |
| `WHEN_PASSCODE_SET_THIS_DEVICE_ONLY` | 3 |
| `ALWAYS_THIS_DEVICE_ONLY` | 4 |
| `WHEN_UNLOCKED` (default) | 5 |
| `WHEN_UNLOCKED_THIS_DEVICE_ONLY` | 6 |

Use `AFTER_FIRST_UNLOCK` for a token a background task must read while the phone is locked.

## Where the data lives

| | iOS | Android |
| --- | --- | --- |
| Storage | Keychain | App `SharedPreferences`, as ciphertext |
| Key | Managed by the Keychain | AES-256-GCM key in the Android Keystore |
| After the app is deleted | Items **survive** and come back on reinstall | Data is removed with the app |
| Backup | Follows the accessibility class (`..._THIS_DEVICE_ONLY` stays off backups) | Not backed up with the keystore key, so a restored backup cannot be read |

Do not rely on a value being there after a reinstall. On iOS a returning item can be a stale token, so check it with
your server.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | A key with a bad character, an unknown option, a bad `keychainService`, or a `keychainAccessible` outside 0-6. | Fix the argument. The message names it. |
| `TypeError` | A value that is not a string. | `json.dumps(obj)` first. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | The app was built without `"secure-store"` in `modules`. | Add it and rebuild. |
| Native error from `get_item_async` / `set_item_async` | The user cancelled or failed the biometric prompt, or no biometrics are enrolled. | Show your own fallback, such as a password field. |

## Web and desktop

Values live in a Python dict for the life of the process:

```python
await SecureStore.set_item_async("k", "v")
await SecureStore.get_item_async("k")            # "v", until the process ends
await SecureStore.is_available_async()           # False
await SecureStore.can_use_biometric_authentication_async()   # False
```

Treat this as a stand-in for tests and previews. Do not rely on it for real secrets, and `requireAuthentication` has
no effect there.

## Recipe: keep a user signed in

Save the token after login, restore it on start, and sign out by deleting it.

```python
import pyxpo_secure_store as SecureStore
from pyxpo import Pressable, Text, View, component, use_async, use_state

OPTS = {"keychainService": "myapp.auth", "keychainAccessible": SecureStore.AFTER_FIRST_UNLOCK}


async def log_in(user: str, password: str) -> str:
    return "tok_8f2c41d9"                       # your server call; a dummy token here


async def restore():
    return await SecureStore.get_item_async("session", OPTS)


@component
def App():
    stored = use_async(restore, [])
    token, set_token = use_state(None)
    current = token or stored.value

    async def sign_in():
        value = await log_in("asha", "not-a-real-password")
        await SecureStore.set_item_async("session", value, OPTS)
        set_token(value)

    async def sign_out():
        await SecureStore.delete_item_async("session", OPTS)
        set_token("")

    if stored.loading:
        return Text("Loading...")
    if current:
        return View(Text("Signed in"), Pressable(Text("Sign out"), on_press=sign_out))
    return View(Text("Signed out"), Pressable(Text("Sign in"), on_press=sign_in))
```

## Production checklist

- [ ] Only secrets are stored here, and each value is small.
- [ ] Every read, write and delete of one item uses the same `keychainService` and options.
- [ ] A restored token (it can come back after an iOS reinstall) is checked with your server.
- [ ] A cancelled biometric prompt has a fallback (a password field) and does not crash.
- [ ] `faceIDPermission` text explains why the app wants Face ID, if you use `requireAuthentication` on iOS.
- [ ] You never log a secret or put one in a screenshot, a crash report or an analytics event.
- [ ] The desktop in-memory fallback is not mistaken for secure storage.

## Testing

On the desktop test host the module is an in-memory dict, so ordinary tests need no fakes. Clear it between tests:

```python
import asyncio

import pyxpo_secure_store as SecureStore


def test_round_trip():
    SecureStore._memory.clear()
    asyncio.run(SecureStore.set_item_async("token", "abc"))
    assert asyncio.run(SecureStore.get_item_async("token")) == "abc"
    asyncio.run(SecureStore.delete_item_async("token"))
    assert asyncio.run(SecureStore.get_item_async("token")) is None
```

To test a biometric failure, replace the function with a fake that raises:

```python
def test_cancelled_prompt(monkeypatch):
    async def cancelled(key, options=None):
        raise RuntimeError("user cancelled")

    monkeypatch.setattr(SecureStore, "get_item_async", cancelled)
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ValueError: invalid key` | The key has a space or a symbol. Use letters, digits, `.`, `-`, `_`. |
| `TypeError: SecureStore values must be strings` | Pass `json.dumps(value)` and `json.loads` it when you read. |
| `get_item_async` returns `None` after a restart on the desktop | The desktop store is in memory only. Run on a phone. |
| A value is missing after a reinstall on Android | Android removes the data with the app. Ask the user to sign in again. |
| A value is still there after a reinstall on iOS | Keychain items survive app deletion. Delete it on first launch if that is not what you want. |
| Reading fails while the phone is locked | The item uses `WHEN_UNLOCKED`. Save it with `AFTER_FIRST_UNLOCK` if a background task needs it. |
| `requireAuthentication` fails on an old Android | It needs Android 10 or newer. |
| The Face ID prompt is missing on iOS | Check `faceIDPermission` and that Face ID is enrolled. The Simulator needs Features > Face ID > Enrolled. |
| `ModuleNotLinkedError` | Add `"secure-store"` to `modules` and rebuild. |

## FAQ

**Is it safe for passwords?** It stores them in the platform's secure store, which is the right place. Prefer
short-lived tokens over raw passwords.

**How large can a value be?** Keep it to a few KB. The Keychain and the Keystore are not built for bulk data.

**Can I store a dict?** Yes, as `json.dumps(d)`, and `json.loads` it after reading.

**Does it sync across devices?** Not by itself. iOS can sync Keychain items through iCloud Keychain depending on the
accessibility class. Use `..._THIS_DEVICE_ONLY` to keep an item on one device.

**Is `setItemAsync` the same as `set_item_async`?** Yes. Every function has both spellings.

## API reference

### Functions

| Function (expo name) | Returns |
| --- | --- |
| `set_item_async(key, value, options=None)` (`setItemAsync`) | `None` |
| `get_item_async(key, options=None)` (`getItemAsync`) | `str` or `None` |
| `delete_item_async(key, options=None)` (`deleteItemAsync`) | `None` |
| `is_available_async()` (`isAvailableAsync`) | `bool` |
| `can_use_biometric_authentication_async()` (`canUseBiometricAuthenticationAsync`, `canUseBiometricAuthentication`) | `bool` |

### Constants

`AFTER_FIRST_UNLOCK`, `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`, `ALWAYS`, `WHEN_PASSCODE_SET_THIS_DEVICE_ONLY`,
`ALWAYS_THIS_DEVICE_ONLY`, `WHEN_UNLOCKED`, `WHEN_UNLOCKED_THIS_DEVICE_ONLY` (see [Options](#options)).

### Module options

| Option (`[tool.pyxpo.module_options.secure-store]`) | Meaning |
| --- | --- |
| `faceIDPermission` | The `NSFaceIDUsageDescription` text on iOS. |

## License

MIT
