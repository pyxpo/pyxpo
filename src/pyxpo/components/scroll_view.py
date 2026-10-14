from __future__ import annotations

from typing import Any

from .._keys import alias_props
from ..element import Element, flatten


def ScrollView(*children: Any, key: Any = None, **props: Any) -> Element:
    """Scrollable container. RN props: horizontal, contentContainerStyle, onScroll, scrollEventThrottle,
    showsVerticalScrollIndicator, showsHorizontalScrollIndicator, bounces, pagingEnabled, scrollEnabled,
    keyboardShouldPersistTaps, keyboardDismissMode, stickyHeaderIndices, refreshControl, contentOffset,
    onContentSizeChange, onScrollBeginDrag, onScrollEndDrag, onMomentumScrollEnd, nestedScrollEnabled.
    `ref.current` has scrollTo({x, y, animated}) and scrollToEnd({animated})."""
    if props and not "".join(props).islower():
        props = alias_props(props)
    kids = flatten(children)
    ccs = props.pop("content_container_style", None)
    if ccs is not None:
        kids = [Element("View", {"style": [{"flex_direction": "row"}, ccs] if props.get("horizontal") else ccs}, kids)]
    rc = props.pop("refresh_control", None)
    if isinstance(rc, Element):
        props["refreshing"] = bool(rc.props.get("refreshing"))
        for k in ("on_refresh", "colors", "tint_color", "progress_background_color", "progress_view_offset"):
            if k in rc.props:
                props[k] = rc.props[k]
        props["refresh_control"] = True
    return Element("ScrollView", props, kids, key)
