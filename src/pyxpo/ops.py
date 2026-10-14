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


_BY_NAME = {c.op: c for c in (Create, Update, Insert, Remove, Delete, Call)}


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
