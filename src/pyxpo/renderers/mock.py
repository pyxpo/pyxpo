from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..channel import LocalChannel
from ..animated import engine
from ..style import flatten
from ..ops import ANode, ANodeDel, AListen, Animate, AStop, ASet, Call, Create, Delete, Insert, Mark, Remove, Update, event_to_json, from_json


class MockError(RuntimeError):
    pass


_BUBBLING = ("press", "long_press", "press_in", "press_out")


class Node:
    def __init__(self, id: int, type: str, props: Optional[Dict[str, Any]] = None) -> None:
        self.id = id
        self.type = type
        self.props = props or {}
        self.children: List[Node] = []
        self.parent: Optional[Node] = None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def __repr__(self) -> str:
        return "Node(%d %s %r)" % (self.id, self.type, self.props)


class MockRenderer:
    """Applies ops to an in-memory tree, strictly validating them. Used for tests and the console preview."""

    def __init__(self, channel: LocalChannel) -> None:
        self.channel = channel
        self.root = Node(1, "Root")
        self.nodes: Dict[int, Node] = {1: self.root}
        self.batches = 0
        self.calls: List[Call] = []
        self.driver = engine.Driver()
        self.clock = 0.0          # virtual ms, moved by advance()
        self.anim_ops = 0         # animation ops received (Python must not send per-frame ops for native anims)
        self.marks: List[int] = []
        channel.set_native_handler(self.apply_json)

    def apply_json(self, payload: str) -> None:
        for op in from_json(payload):
            self._apply(op)
        self.batches += 1
        self.after_batch()

    def after_batch(self) -> None:
        pass

    def _node(self, id: int) -> Node:
        try:
            return self.nodes[id]
        except KeyError:
            raise MockError("unknown node id %r" % id)

    def _apply(self, op: Any) -> None:
        if isinstance(op, Create):
            if op.id in self.nodes:
                raise MockError("duplicate create %d" % op.id)
            self.nodes[op.id] = Node(op.id, op.type, dict(op.props))
        elif isinstance(op, Update):
            n = self._node(op.id)
            n.props.update(op.props)
            for k in op.removed:
                n.props.pop(k, None)
        elif isinstance(op, Insert):
            parent, n = self._node(op.parent), self._node(op.id)
            if n.parent is not None:
                raise MockError("insert of already attached node %d" % op.id)
            if not 0 <= op.index <= len(parent.children):
                raise MockError("insert index %d out of range" % op.index)
            parent.children.insert(op.index, n)
            n.parent = parent
        elif isinstance(op, Remove):
            parent, n = self._node(op.parent), self._node(op.id)
            if n.parent is not parent:
                raise MockError("remove of node %d not child of %d" % (op.id, op.parent))
            parent.children.remove(n)
            n.parent = None
        elif isinstance(op, Delete):
            n = self._node(op.id)
            top = n
            while top.parent is not None:
                top = top.parent
            if top is self.root:
                raise MockError("delete of attached node %d" % op.id)
            if n.parent is not None:
                n.parent.children.remove(n)
                n.parent = None
            del self.nodes[op.id]
        elif isinstance(op, Call):
            self.calls.append(op)
        elif isinstance(op, Mark):
            self.marks.append(op.n)
        elif isinstance(op, (ANode, ANodeDel, AListen, Animate, AStop, ASet)):
            self.anim_ops += 1
            d = self.driver
            if isinstance(op, ANode):
                d.anode(op.id, op.node)
            elif isinstance(op, ANodeDel):
                self._events(d.anode_del(op.id))
            elif isinstance(op, AListen):
                d.alisten(op.id, op.on)
            elif isinstance(op, Animate):
                self._events(d.animate(op.id, op.anim))
            elif isinstance(op, AStop):
                self._events(d.astop(op.id))
            else:
                self._events(d.aset(op.vals))
        else:
            raise MockError("unknown op %r" % (op,))

    # -- animation -------------------------------------------------------
    def _events(self, evs: List[Dict[str, Any]]) -> None:
        for e in evs:
            self.channel.emit_event(json.dumps(e))

    def advance(self, ms: float, step: float = 16.0) -> None:
        """Move the virtual clock forward in frame-sized steps, ticking the animation driver."""
        end = self.clock + ms
        while self.clock < end:
            self.clock = min(end, self.clock + step)
            self._events(self.driver.tick(self.clock))

    def scroll(self, node: Any, x: float = 0, y: float = 0, width: float = 360, height: float = 640,
               content_width: float = 360, content_height: float = 2000) -> None:
        """Act like a native scroll view: write bound animated values, emit `scroll` when Python listens."""
        n = node if isinstance(node, Node) else self._node(node)
        prop = n.props.get("on_scroll")
        value = {"x": x, "y": y, "width": width, "height": height,
                 "content_width": content_width, "content_height": content_height}
        emit = bool(prop)
        if isinstance(prop, dict) and "$ae" in prop:
            self._events(self.driver.aset({str(nid): float(value[k]) for k, nid in prop["$ae"].items() if k in value}))
            emit = bool(prop.get("emit"))
        if emit:
            self.channel.emit_event(json.dumps({"event": "scroll", "id": n.id, "payload": {"value": value}}))

    def resolved(self, node: Any, key: str) -> Any:
        """Effective style value: animated binding if the style key is bound, else the static value."""
        n = node if isinstance(node, Node) else self._node(node)
        v = flatten(n.props.get("style")).get(key)
        if isinstance(v, dict) and "$a" in v:
            return self.driver.resolve(v["$a"])
        return v

    # -- query helpers -------------------------------------------------
    def find_all(self, type: str) -> List[Node]:
        return [n for n in self.root.walk() if n.type == type]

    def find_text(self, text: str) -> Optional[Node]:
        for n in self.root.walk():
            if n.props.get("text") == text:
                return n
        for n in self.root.walk():  # Text applies text_transform in Python, so Button("go") shows "GO"
            t = n.props.get("text")
            if isinstance(t, str) and t.upper() == text.upper():
                return n
        return None

    def texts(self, buttons: bool = False) -> List[str]:
        """Text of every Text node; labels inside accessibility_role="button" views (Button) only with `buttons`."""
        def inside_button(n: Node) -> bool:
            p = n.parent
            while p is not None:
                if p.props.get("accessibility_role") == "button":
                    return True
                p = p.parent
            return False
        return [n.props["text"] for n in self.root.walk()
                if n.type == "Text" and (buttons or not inside_button(n))]

    def attached_ids(self) -> List[int]:
        return [n.id for n in self.root.walk()]

    # -- interaction ---------------------------------------------------
    def emit(self, event: str, node: Any, payload: Optional[Dict[str, Any]] = None) -> None:
        n = node if isinstance(node, Node) else self.nodes[node]
        if event in _BUBBLING:  # native hit-testing hands touches to the nearest ancestor with a handler
            while n.parent is not None and not n.props.get("on_" + event):
                n = n.parent
        node_id = n.id
        self.channel.emit_event(event_to_json(event, node_id, payload))

    def press(self, node: Any) -> None:
        self.emit("press", node)

    def type_text(self, node: Any, text: str) -> None:
        self.emit("change_text", node, {"value": text})

    def dump(self) -> str:
        lines: List[str] = []

        def rec(n: Node, depth: int) -> None:
            label = n.type
            if "text" in n.props:
                label += " %r" % n.props["text"]
            lines.append("  " * depth + label)
            for c in n.children:
                rec(c, depth + 1)

        for c in self.root.children:
            rec(c, 0)
        return "\n".join(lines)
