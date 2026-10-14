from __future__ import annotations

import asyncio
import sys
from typing import List

from .mock import MockRenderer, Node


class ConsoleRenderer(MockRenderer):
    """Terminal preview: prints the tree after each commit; type a button number to press it."""

    def after_batch(self) -> None:
        print(self.render_text(), flush=True)

    def _pressables(self) -> List[Node]:
        return [n for n in self.root.walk() if n.type == "Button"]

    def render_text(self) -> str:
        buttons = self._pressables()
        lines = ["-" * 30]

        def rec(n: Node, depth: int) -> None:
            label = n.type
            if n in buttons:
                label = "[%d] Button" % (buttons.index(n) + 1)
            if n.type == "TextInput":
                label += " %r" % n.props.get("value", "")
            if "text" in n.props:
                label += " %r" % n.props["text"]
            lines.append("  " * depth + label)
            for c in n.children:
                rec(c, depth + 1)

        for c in self.root.children:
            rec(c, 0)
        lines.append("(button number = press, 't N text' = type into Nth TextInput, q = quit)")
        return "\n".join(lines)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            line = line.strip()
            if line in ("q", "quit") or line == "" and sys.stdin.closed:
                return
            if not line:
                continue
            if line.isdigit():
                buttons = self._pressables()
                n = int(line)
                if 1 <= n <= len(buttons):
                    self.press(buttons[n - 1])
                else:
                    print("no such button")
            elif line.startswith("t "):
                parts = line.split(" ", 2)
                inputs = self.find_all("TextInput")
                if len(parts) == 3 and parts[1].isdigit() and 1 <= int(parts[1]) <= len(inputs):
                    node = inputs[int(parts[1]) - 1]
                    node.props["value"] = parts[2]
                    self.type_text(node, parts[2])
                else:
                    print("usage: t N text")
