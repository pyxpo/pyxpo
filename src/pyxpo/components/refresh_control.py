from __future__ import annotations

from typing import Any

from ..element import Element


def RefreshControl(key: Any = None, **props: Any) -> Element:
    """Pull-to-refresh. Only meaningful as `ScrollView(refreshControl=RefreshControl(refreshing=..., onRefresh=...))`
    (also FlatList / SectionList). Props: refreshing, onRefresh, colors, tintColor, progressBackgroundColor."""
    from .._keys import alias_props
    return Element("RefreshControl", alias_props(props) if props and not "".join(props).islower() else props, [], key)
