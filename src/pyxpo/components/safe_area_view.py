from __future__ import annotations

from typing import Any

from ..component import component
from ..hooks import use_safe_area_insets
from ..style import flatten
from .view import View


@component
def SafeAreaView(*children: Any, edges: Any = ("top", "right", "bottom", "left"), mode: str = "padding",
                 style: Any = None, **props: Any):
    """View inset by the system bars, notch and home indicator (`react-native-safe-area-context` API).
    `mode`: "padding" (default) or "margin"."""
    ins = use_safe_area_insets()
    st = flatten(style)
    base = "margin" if mode == "margin" else "padding"
    for e in ("top", "right", "bottom", "left"):
        axis = "vertical" if e in ("top", "bottom") else "horizontal"
        v = st.get("%s_%s" % (base, e), st.get("%s_%s" % (base, axis), st.get(base, 0)))
        v = v if isinstance(v, (int, float)) else 0
        if v or e in edges:
            st["%s_%s" % (base, e)] = v + (ins[e] if e in edges else 0)
    for k in (base, base + "_vertical", base + "_horizontal"):
        st.pop(k, None)
    st.setdefault("flex", 1)
    return View(*children, style=st, **props)
