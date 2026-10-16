"""ImageKit design tokens: light/dark palettes + spacing."""
from pyxpo import useColorScheme

LIGHT = {
    "bg": "#F4F5FB", "card": "#FFFFFF", "text": "#12142B", "sub": "#6B6F8A", "line": "#E6E8F2",
    "accent": "#6C5CE7", "accent2": "#A66BFF", "onAccent": "#FFFFFF", "chip": "#ECEBFD", "chipText": "#4B3FC9",
    "good": "#12B76A", "goodBg": "#DDF7EA", "bad": "#E5484D", "shadow": "#1B1F4B",
}
DARK = {
    "bg": "#0C0D1A", "card": "#171933", "text": "#F2F3FF", "sub": "#9A9DBE", "line": "#272A4A",
    "accent": "#8B7CFF", "accent2": "#C08BFF", "onAccent": "#FFFFFF", "chip": "#25264A", "chipText": "#C9C3FF",
    "good": "#3DDC97", "goodBg": "#12382B", "bad": "#FF6B70", "shadow": "#000000",
}
TOOLS = [
    {"id": "compress", "title": "Compress", "sub": "Make it under…", "icon": "minimize-2", "colors": ["#6C5CE7", "#A66BFF"]},
    {"id": "resize", "title": "Resize", "sub": "Exact dimensions", "icon": "maximize", "colors": ["#0EA5E9", "#38D6F5"]},
    {"id": "convert", "title": "Convert", "sub": "HEIC · JPG · PNG", "icon": "refresh-cw", "colors": ["#F97316", "#FFB347"]},
    {"id": "metadata", "title": "Remove Metadata", "sub": "EXIF & GPS", "icon": "shield", "colors": ["#10B981", "#5BE3A8"]},
    {"id": "crop", "title": "Crop", "sub": "Ratios", "icon": "crop", "colors": ["#EC4899", "#FF8AC4"]},
    {"id": "info", "title": "Image Info", "sub": "Size · format · GPS", "icon": "info", "colors": ["#64748B", "#94A3B8"]},
    {"id": "optimize", "title": "Quick Optimize", "sub": "Batch, one tap", "icon": "zap", "colors": ["#EAB308", "#FFD84D"]},
]
TOOL = {t["id"]: t for t in TOOLS}


def useTheme():
    return DARK if useColorScheme() == "dark" else LIGHT


def fmt_bytes(n):
    n = float(n or 0)
    if n >= 1024 * 1024:
        return "%.2f MB" % (n / 1048576.0)
    if n >= 1024:
        return "%.0f KB" % (n / 1024.0)
    return "%d B" % n
