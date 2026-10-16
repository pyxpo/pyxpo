"""Debug-only: runs every ImageManipulator op over fixtures and prints one IMAGEKIT_SELFTEST json line."""
import asyncio
import json
import os
import sys
import traceback

from pyxpo_image_picker import ImagePicker
from pyxpo_media_library import MediaLibrary
from pyxpo_sharing import Share
from pyxpo_image_manipulator import FlipType, ImageManipulator, ImageTooLargeError, SaveFormat

from app import _ops


async def run(fix):
    out, ok = {}, True

    def check(name, cond, detail=None):
        nonlocal ok
        out[name] = {"ok": bool(cond), "detail": detail}
        ok = ok and bool(cond)

    try:
        jpg, heic, png, huge = (os.path.join(fix, n) for n in ("photo.jpg", "photo.heic", "alpha.png", "huge.jpg"))
        i = await ImageManipulator.getInfoAsync(jpg)
        check("info_jpg", i["format"] == "jpeg" and i["hasGps"] and i["hasExif"] and (i["width"], i["height"]) == (3024, 4032), i)
        i = await ImageManipulator.getInfoAsync(heic)
        check("info_heic", i["format"] == "heic" and i["hasGps"], i)
        c = await ImageManipulator.compressToSizeAsync(jpg, 1_000_000)
        check("under_1mb", c["fileSize"] <= 1_000_000, c)
        c2 = await ImageManipulator.compressToSizeAsync(jpg, 300_000)
        check("under_300kb", c2["fileSize"] <= 300_000, c2)
        ci = await ImageManipulator.getInfoAsync(c["uri"])
        check("compress_strips_gps", not ci["hasGps"] and ci["format"] == "jpeg", ci)
        r = await ImageManipulator.manipulateAsync(jpg, [{"resize": {"width": 800, "height": 600}}])
        check("resize_exact", (r["width"], r["height"]) == (800, 600), r)
        r = await ImageManipulator.manipulateAsync(jpg, [{"resize": {"width": 1000}}])
        check("resize_fit", (r["width"], r["height"]) == (1000, 1333), r)
        r = await ImageManipulator.manipulateAsync(heic)
        ri = await ImageManipulator.getInfoAsync(r["uri"])
        check("heic_to_jpg", ri["format"] == "jpeg" and not ri["hasGps"] and ri["height"] == 4032, ri)
        try:
            r = await ImageManipulator.manipulateAsync(jpg, [], {"format": SaveFormat.HEIC})
            check("jpg_to_heic", sys.platform != "android" and r["format"] == "heic", r)
        except Exception as e:  # Android cannot encode HEIC: NotSupportedError
            check("jpg_to_heic_unsupported", sys.platform == "android", str(e))
        r = await ImageManipulator.manipulateAsync(png)
        check("png_to_jpg_flatten", r["format"] == "jpeg", r)
        r = await _ops.strip_metadata(png)
        check("png_same", r["format"] == "png", r)
        r = await _ops.crop_ratio(jpg, "1:1")
        check("crop_square", r["width"] == r["height"] == 3024, r)
        r = await ImageManipulator.manipulateAsync(jpg, [{"rotate": 90}, {"flip": FlipType.Horizontal}])
        check("rotate_90_swaps", (r["width"], r["height"]) == (4032, 3024), r)
        r = await ImageManipulator.manipulateAsync(jpg, [{"crop": {"originX": 100, "originY": 200, "width": 500, "height": 400}}, {"rotate": 180}])
        check("crop_then_rotate", (r["width"], r["height"]) == (500, 400), r)
        r = await _ops.crop_ratio(jpg, "16:9")
        check("crop_16_9", (r["width"], r["height"]) == (3024, 1701), r)
        r = await _ops.optimize(huge)
        check("optimize_huge", max(r["width"], r["height"]) <= 2560 and r["fileSize"] < 8_000_000, r)
        try:
            await ImageManipulator.compressToSizeAsync(jpg, 500)
            check("too_large_error", False)
        except ImageTooLargeError as e:
            check("too_large_error", True, str(e))
        try:
            await ImageManipulator.getInfoAsync("/nonexistent.jpg")
            check("missing_file_error", False)
        except RuntimeError as e:
            check("missing_file_error", True, str(e))
        try:
            shape = {"status", "granted", "canAskAgain", "expires", "accessPrivileges"}
            g = await MediaLibrary.getPermissionsAsync()
            check("library_get_permission_shape", set(g) == shape and g["status"] in ("granted", "denied", "undetermined"), g)
            perm = await MediaLibrary.requestPermissionsAsync(writeOnly=True)
            check("library_permission", perm["granted"] and set(perm) == shape, perm)
            if perm["granted"]:
                await MediaLibrary.saveToLibraryAsync(jpg)
                check("library_save", True)
                a = await MediaLibrary.createAssetAsync(jpg)
                check("library_create_asset", a["mediaType"] == "photo" and a["id"] and a["uri"]
                      and (a["width"], a["height"]) == (3024, 4032) and a["duration"] == 0
                      and a["filename"].endswith(".jpg"), a)
        except Exception as e:  # noqa: BLE001
            check("library_save", False, str(e))
        try:
            cp = await ImagePicker.getCameraPermissionsAsync()
            check("camera_permission_shape", set(cp) == {"status", "granted", "canAskAgain", "expires"}, cp)
            if os.environ.get("SIMULATOR_DEVICE_NAME"):
                # Older simulators have no camera (clean error); iOS 27+ simulates one, so the camera UI stays open.
                # asyncio.wait does not cancel the call, so a late native reply is harmless.
                task = asyncio.ensure_future(ImagePicker.launchCameraAsync())
                done, _ = await asyncio.wait({task}, timeout=5)
                if not done:
                    check("camera_launch", True, "camera UI open")
                elif task.exception() is not None:
                    check("camera_launch", "no camera" in str(task.exception()), str(task.exception()))
                else:
                    check("camera_launch", False, task.result())
        except Exception as e:  # noqa: BLE001
            check("camera_permission_shape", False, str(e))
        try:
            await Share.share({"url": jpg + ".missing"})
            check("share_missing_file_error", False)
        except RuntimeError as e:
            check("share_missing_file_error", "not found" in str(e), str(e))
    except Exception:
        ok = False
        out["exception"] = traceback.format_exc()
    line = "IMAGEKIT_SELFTEST " + json.dumps({"ok": ok, "results": out})
    print(line, flush=True)
    if os.environ.get("IK_OUT"):
        with open(os.environ["IK_OUT"], "w") as f:
            f.write(line)
