"""Tiny shared store: picked images + last results, with a hook that re-renders on change."""
from pyxpo import useEffect, useState
from pyxpo_image_picker import ImagePicker

_state = {"images": [], "results": [], "tool": None}
_subs = set()


def update(**kw):
    _state.update(kw)
    for f in list(_subs):
        f()


def useStore():
    _, bump = useState(0)

    def sub():
        f = lambda: bump(lambda n: n + 1)  # noqa: E731
        _subs.add(f)
        return lambda: _subs.discard(f)
    useEffect(sub, [])
    return _state


async def pick(multiple=True):
    res = await ImagePicker.launchImageLibraryAsync(allowsMultipleSelection=multiple, selectionLimit=30 if multiple else 1)
    if not res["canceled"]:
        update(images=list(res["assets"]), results=[])
    return not res["canceled"]
