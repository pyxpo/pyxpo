from __future__ import annotations

import asyncio
import time

from pyxpo import App, Button, LocalChannel, Text, View, component, use_async, use_effect, use_state
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


def test_async_event_handler_runs_as_task():
    errors = []

    @component
    def C():
        n, set_n = use_state(0)

        async def add():
            await asyncio.sleep(0)
            set_n(n + 1)

        async def boom():
            await asyncio.sleep(0)
            raise ValueError("bad press")

        return View(Text("n=%d" % n), Button(title="add", onPress=add), Button(title="boom", onPress=boom))

    async def main():
        ch = LocalChannel()
        r = MockRenderer(ch)
        app = App(C, ch, asyncio.get_running_loop())
        app.on_error = errors.append
        app.start()
        await asyncio.sleep(0.05)
        r.press(r.find_text("add"))
        await asyncio.sleep(0.05)
        r.press(r.find_text("boom"))
        await asyncio.sleep(0.05)
        return r

    r = asyncio.run(main())
    assert r.texts() == ["n=1"]
    assert [str(e) for e in errors] == ["bad press"]
