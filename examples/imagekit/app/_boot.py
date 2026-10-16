"""Debug hook: runs the selftest when fixtures are present (IK_FIX env on iOS, cache/ik_fix on Android)."""
import os

from pyxpo.apis import _bridge


def start():
    fix = os.environ.get("IK_FIX")
    droid = "/data/data/com.example.imagekit/cache"  # Android has no launch env: adb pushes fixtures here
    if not fix and os.path.isdir(droid + "/ik_fix"):
        fix = droid + "/ik_fix"
        os.environ["IK_OUT"] = droid + "/ik_out.txt"
    if not fix:
        return

    async def go():
        import importlib
        await importlib.import_module("app._selftest").run(fix)
    _bridge.spawn(go())
