"""iOS runtime fixes that only show on a device, pinned in the Swift source so they do not come undone."""
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "src" / "pyxpo" / "templates" / "ios" / "gen" / "runtime"


def test_image_decodes_off_main_thread_at_view_size():
    swift = (RUNTIME / "Images.swift").read_text()
    # ImageIO decodes now on a background queue; UIImage(data:) alone decodes lazily on the main thread at draw
    assert "kCGImageSourceShouldCacheImmediately: true" in swift
    assert "kCGImageSourceThumbnailMaxPixelSize: side" in swift
    # the image keeps the source size in points, so the load event and intrinsic size do not change
    assert "scale: CGFloat(long) / CGFloat(max(cg.width, cg.height))" in swift
    # one decode serves every cell that shows the same photo
    assert "if waiting[key] != nil { waiting[key]!.append(done); return }" in swift
    assert "for cb in self.waiting.removeValue(forKey: key) ?? [] { cb(img, err) }" in swift
    ops = (RUNTIME / "OpApplier.swift").read_text()
    # the load waits for the batch's layout, so the frame is known
    assert "self.images.load(uri, px: px)" in ops
    assert ops.index("DispatchQueue.main.async { [weak self, weak v] in") < ops.index("self.images.load(uri, px: px)")
