# pyxpo-secure-store

Encrypted key-value storage for secrets (tokens, passwords) in pyxpo apps. The API follows
expo-secure-store.

This is an optional [pyxpo](https://github.com/pyxpo/pyxpo) native module. Apps that do not
list it carry none of its code, permissions or dependencies.

## Install

```bash
pip install pyxpo-secure-store
```

Then link it into your app in `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["secure-store"]
```

and rebuild (`pyxpo run ios`, `pyxpo build android`, ...).

## Use

```python
import pyxpo_secure_store as SecureStore

await SecureStore.set_item_async("token", "abc")    # or SecureStore.setItemAsync
await SecureStore.get_item_async("token")           # "abc", or None
await SecureStore.delete_item_async("token")

# Ask for Face ID / Touch ID / fingerprint before the value can be read
await SecureStore.set_item_async("pin", "1234", {
    "requireAuthentication": True,
    "authenticationPrompt": "Unlock your PIN",
})
```

Options: `keychainService`, `requireAuthentication`, `authenticationPrompt`, `keychainAccessible`
(iOS, one of the `SecureStore.WHEN_UNLOCKED`, `AFTER_FIRST_UNLOCK`, ... constants) and `accessGroup` (iOS).

Keys use letters, digits, `.`, `-` and `_`. Values are strings: use `json.dumps` for objects. Keep values
small (a few KB).

- iOS keeps values in the Keychain. Keychain items survive app deletion.
- Android encrypts values with an AES-256-GCM key held in the Android Keystore and keeps the ciphertext
  in the app's SharedPreferences. `requireAuthentication` needs Android 10 or newer.
- On the desktop (tests, previews) values live in memory only and are not encrypted.

Permissions and Info.plist keys: `NSFaceIDUsageDescription` (set its text with the `faceIDPermission`
option) and Android `USE_BIOMETRIC`.

## What is in the package

- `pyxpo_secure_store/__init__.py`: the Python API.
- `pyxpo_secure_store/pyxpo-module.json`: autolink metadata.
- `pyxpo_secure_store/ios/`: Swift sources compiled into the iOS app.
- `pyxpo_secure_store/android/src/main/`: Kotlin sources and the manifest merged into the Android app.
