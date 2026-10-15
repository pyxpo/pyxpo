"""Encrypted key-value storage for secrets (tokens, passwords): the expo-secure-store API.

    import pyxpo_secure_store as SecureStore

    await SecureStore.set_item_async("token", "abc")      # or SecureStore.setItemAsync
    await SecureStore.get_item_async("token")             # "abc", or None
    await SecureStore.delete_item_async("token")

iOS keeps values in the Keychain. Android encrypts them with an AES-256-GCM key held in the Android
Keystore and keeps the ciphertext in the app's SharedPreferences. With `requireAuthentication` the
system asks for Face ID / Touch ID / fingerprint before the value can be read (and, on Android, written).

Values are strings. Keep them small (a few KB); use pyxpo-storage or pyxpo-file-system for bulk data.
iOS Keychain items survive app deletion; Android data does not.
On the desktop (tests, previews) values live in memory only and nothing is encrypted.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pyxpo.module_api import call, platform, require_linked

__version__ = "0.1.0a1"

# keychainAccessible values (iOS); same numbers as expo-secure-store.
AFTER_FIRST_UNLOCK = 0
AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY = 1
ALWAYS = 2
WHEN_PASSCODE_SET_THIS_DEVICE_ONLY = 3
ALWAYS_THIS_DEVICE_ONLY = 4
WHEN_UNLOCKED = 5
WHEN_UNLOCKED_THIS_DEVICE_ONLY = 6

_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")
_OPTIONS = {"keychainService", "requireAuthentication", "authenticationPrompt", "keychainAccessible", "accessGroup"}
_memory: Dict[str, str] = {}


def _check_key(key: Any) -> str:
    if not isinstance(key, str) or not _KEY.match(key):
        raise ValueError("invalid key %r: use letters, digits, '.', '-' and '_' only" % (key,))
    return key


def _options(options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    o = dict(options or {})
    unknown = set(o) - _OPTIONS
    if unknown:
        raise ValueError("unknown SecureStore option(s): %s" % ", ".join(sorted(unknown)))
    service = o.get("keychainService", "app")
    if not isinstance(service, str) or not _KEY.match(service):
        raise ValueError("invalid keychainService %r" % (service,))
    acc = o.get("keychainAccessible", WHEN_UNLOCKED)
    if not isinstance(acc, int) or isinstance(acc, bool) or not 0 <= acc <= 6:
        raise ValueError("keychainAccessible must be one of the SecureStore constants (0-6)")
    return {
        "keychainService": service,
        "requireAuthentication": bool(o.get("requireAuthentication")),
        "authenticationPrompt": str(o.get("authenticationPrompt") or ""),
        "keychainAccessible": acc,
        "accessGroup": str(o.get("accessGroup") or ""),
    }


def _native() -> bool:
    if platform() == "desktop":
        return False
    require_linked("SecureStore", "secure-store", package="pyxpo-secure-store")
    return True


async def is_available_async() -> bool:
    """True on iOS and Android when the module is linked; False on the desktop."""
    if platform() == "desktop":
        return False
    try:
        require_linked("SecureStore", "secure-store", package="pyxpo-secure-store")
    except Exception:  # noqa: BLE001 - not linked means unavailable
        return False
    return True


async def get_item_async(key: str, options: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The stored string, or None. Prompts for biometrics when the item was saved with `requireAuthentication`."""
    _check_key(key)
    o = _options(options)
    if not _native():
        return _memory.get(o["keychainService"] + "-" + key)
    return await call("SecureStore", "get", key, o, reply=True)


async def set_item_async(key: str, value: str, options: Optional[Dict[str, Any]] = None) -> None:
    """Stores `value`, replacing what `key` held. `options`: `keychainService`, `requireAuthentication`,
    `authenticationPrompt`, `keychainAccessible` (iOS) and `accessGroup` (iOS)."""
    _check_key(key)
    if not isinstance(value, str):
        raise TypeError("SecureStore values must be strings, got %s (use json.dumps for objects)" % type(value).__name__)
    o = _options(options)
    if not _native():
        _memory[o["keychainService"] + "-" + key] = value
        return
    await call("SecureStore", "set", key, value, o, reply=True)


async def delete_item_async(key: str, options: Optional[Dict[str, Any]] = None) -> None:
    """Removes `key`. No error when it does not exist."""
    _check_key(key)
    o = _options(options)
    if not _native():
        _memory.pop(o["keychainService"] + "-" + key, None)
        return
    await call("SecureStore", "delete", key, o, reply=True)


async def can_use_biometric_authentication_async() -> bool:
    """True when the device has biometrics enrolled, so `requireAuthentication` items can be used."""
    if not _native():
        return False
    return bool(await call("SecureStore", "canUseBiometric", reply=True))


isAvailableAsync = is_available_async
getItemAsync = get_item_async
setItemAsync = set_item_async
deleteItemAsync = delete_item_async
canUseBiometricAuthenticationAsync = can_use_biometric_authentication_async
canUseBiometricAuthentication = can_use_biometric_authentication_async
