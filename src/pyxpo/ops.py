from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


class Op:
    op = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {"op": self.op}
        d.update(asdict(self))
        if self.op == "update" and not d["removed"]:
            del d["removed"]
        return d


@dataclass
class Create(Op):
    id: int
    type: str
    props: Dict[str, Any] = field(default_factory=dict)
    op = "create"


@dataclass
class Update(Op):
    id: int
    props: Dict[str, Any] = field(default_factory=dict)
    removed: List[str] = field(default_factory=list)
    op = "update"


@dataclass
class Insert(Op):
    parent: int
    id: int
    index: int
    op = "insert"


@dataclass
class Remove(Op):
    parent: int
    id: int
    op = "remove"


@dataclass
class Delete(Op):
    id: int
    op = "delete"


@dataclass
class Call(Op):
    """Python -> native module call. Native answers with a `call_result` event (id = call id) when `reply` is set."""
    id: int
    module: str
    method: str
    args: List[Any] = field(default_factory=list)
    reply: bool = False
    op = "call"


@dataclass
class ANode(Op):
    """Create an animated node (value / interp / add / mul). Ids are separate from view ids."""
    id: int
    node: Dict[str, Any]
    op = "anode"


@dataclass
class ANodeDel(Op):
    id: int
    op = "anode_del"


@dataclass
class AListen(Op):
    """Ask native to send `anim_value` events for this value node."""
    id: int
    on: bool
    op = "alisten"


@dataclass
class Animate(Op):
    """Start animation tree `anim` on the native driver. Native answers with `anim_end` (id = animation id)."""
    id: int
    anim: Dict[str, Any]
    op = "animate"


@dataclass
class AStop(Op):
    id: int
    op = "astop"


@dataclass
class ASet(Op):
    """Set value nodes ({node id as str: value}); also stops native animations driving them."""
    vals: Dict[str, float]
    op = "aset"


_BY_NAME = {c.op: c for c in (Create, Update, Insert, Remove, Delete, Call, ANode, ANodeDel, AListen, Animate, AStop,
                              ASet)}


def op_from_dict(d: Dict[str, Any]) -> Op:
    d = dict(d)
    cls = _BY_NAME[d.pop("op")]
    return cls(**d)


def to_json(ops: List[Op]) -> str:
    return json.dumps([o.to_dict() for o in ops], separators=(",", ":"))


def from_json(s: str) -> List[Op]:
    return [op_from_dict(d) for d in json.loads(s)]


def event_to_json(event: str, node_id: int, payload: Dict[str, Any] | None = None) -> str:
    return json.dumps({"event": event, "id": node_id, "payload": payload or {}})
