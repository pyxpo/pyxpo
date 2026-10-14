from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..channel import LocalChannel
from ..ops import Create, Delete, Insert, Remove, Update, event_to_json, from_json


class MockError(RuntimeError):
    pass


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
            if n.parent is not None:
                raise MockError("delete of attached node %d" % op.id)
            del self.nodes[op.id]
        else:
            raise MockError("unknown op %r" % (op,))

    # -- query helpers -------------------------------------------------
    def find_all(self, type: str) -> List[Node]:
        return [n for n in self.root.walk() if n.type == type]

    def find_text(self, text: str) -> Optional[Node]:
        for n in self.root.walk():
            if n.props.get("text") == text:
                return n
        return None

    def texts(self) -> List[str]:
        return [n.props["text"] for n in self.root.walk() if n.type == "Text"]

    def attached_ids(self) -> List[int]:
        return [n.id for n in self.root.walk()]

    # -- interaction ---------------------------------------------------
    def emit(self, event: str, node: Any, payload: Optional[Dict[str, Any]] = None) -> None:
        node_id = node.id if isinstance(node, Node) else node
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
