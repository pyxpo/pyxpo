"""ImageKit operations built on the generic pyxpo_image_manipulator API."""
from pyxpo_image_manipulator import ImageManipulator, SaveFormat, centered_crop, parse_ratio


def _same(info):
    return SaveFormat.PNG if info["format"] == "png" else SaveFormat.JPEG


async def resize(uri, w, h):
    return await ImageManipulator.manipulateAsync(uri, [{"resize": {"width": w or None, "height": h or None}}], {"compress": 0.9})


async def convert(uri, fmt):
    return await ImageManipulator.manipulateAsync(uri, [], {"compress": 0.92, "format": fmt})


async def strip_metadata(uri):
    info = await ImageManipulator.getInfoAsync(uri)
    out = await ImageManipulator.manipulateAsync(uri, [], {"compress": 0.85, "format": _same(info)})
    if out["fileSize"] > info["fileSize"] and info["format"] == "jpeg":
        # Re-encoding a low-quality source can grow it; keep the result no bigger than the original.
        out = await ImageManipulator.compressToSizeAsync(uri, info["fileSize"])
    return out


async def crop_ratio(uri, ratio):
    info = await ImageManipulator.getInfoAsync(uri)
    c = centered_crop(info["width"], info["height"], parse_ratio(ratio))
    act = {"crop": {"originX": c["x"], "originY": c["y"], "width": c["width"], "height": c["height"]}}
    return await ImageManipulator.manipulateAsync(uri, [act], {"compress": 0.92, "format": _same(info)})


async def optimize(uri, max_edge=2560):
    """Quick Optimize: long edge <= max_edge, JPEG quality 0.8."""
    info = await ImageManipulator.getInfoAsync(uri)
    acts = []
    if max(info["width"], info["height"]) > max_edge:
        acts = [{"resize": {"width": max_edge} if info["width"] >= info["height"] else {"height": max_edge}}]
    return await ImageManipulator.manipulateAsync(uri, acts, {"compress": 0.8})
