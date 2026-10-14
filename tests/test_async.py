from __future__ import annotations

import asyncio
import time

from pyxpo import App, LocalChannel, Text, View, component, use_async, use_effect, use_state
from pyxpo.renderers.mock import MockRenderer


def test_use_async_and_batched_setstate():
    renders = []

    @component
    def C():
        a, set_a = use_state(0)
        b, set_b = use_state(0)
        res = use_async(lambda: (time.sleep(0.01), 42)[1], [])
        renders.append((a, b))
        use_effect(lambda: (set_a(1), set_b(1)) and None, [])
        return View(Text("loading" if res.loading else "v=%s" % res.value))

    async def main():
        ch = LocalChannel()
        r = MockRenderer(ch)
        app = App(C, ch, asyncio.get_running_loop())
        app.start()
        await asyncio.sleep(0.3)
        return r, app

    r, app = asyncio.run(main())
    assert r.texts() == ["v=42"]
    assert (1, 1) in renders and (1, 0) not in renders and (0, 1) not in renders  # one batched render
