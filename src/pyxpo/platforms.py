from __future__ import annotations

from typing import Dict, List

PYTHON_VERSION = "3.13"

# target -> pip --platform tags to check
TARGET_TAGS: Dict[str, List[str]] = {
    "android": ["android_24_arm64_v8a", "android_24_armeabi_v7a", "android_24_x86_64"],
    "ios": ["ios_13_0_arm64_iphoneos", "ios_13_0_arm64_iphonesimulator", "ios_13_0_x86_64_iphonesimulator"],
}

# Tags a build can do without: phones with a 32-bit Android get left out when a library has no wheel for them.
OPTIONAL_TAGS = {"android_24_armeabi_v7a"}
