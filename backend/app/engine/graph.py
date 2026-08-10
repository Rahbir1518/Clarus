"""React Flow's `nodes` and `edges` parsed into something walkable.

The stored graph is the builder's own JSON, handed back unchanged by the
workflows API — `app/schemas/workflow.py` deliberately does not model it, on the
grounds that the builder owns the shape and it is the caller's own data rather
than a security boundary. That holds for storage. It stops holding the moment
the graph decides whether to phone somebody, which is what this module is for:
every assumption the walk makes is checked here, once, before any node runs.

What a walk is
--------------
Start at one trigger. Follow outgoing edges. A conditional leaves by exactly one
of its two handles; everything else fans out to all of its children. A branch
stops when a step halts it, when it runs out of edges, or when it would revisit
a node.

Depth-first, and the order is stable rather than incidental: children are
visited in the order their edges appear in the stored array, which is the order
the builder wrote them. A run that is replayed produces the same log.

Cycles
------
Refused at run time by a visited set, per run, and REBUILD_CHECKLIST.md wants
them refused at save time too — that check does not exist yet. A cycle in a
graph that places calls is an unbounded number of calls, so the run-time guard
is not a formality: it is the thing standing between a mis-drawn edge and a
patient's phone ringing until someone notices.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Final

from app.engine.catalogue import CONDITION, TRIGGER, category_of

# A ceiling on how many nodes one run may execute. A graph with no cycle can
# still be pathological — a wide fan-out several layers deep — and the visited
# set alone does not bound the work. Well above any hand-drawn workflow.
MAX_STEPS: Final[int] = 200

# The two handles a conditional may leave by. React Flow writes the handle id
# set on the <Handle> components in ConditionalNode.tsx.
TRUE_BRANCH: Final[str] = "true"
FALSE_BRANCH: Final[str] = "false"


class GraphError(ValueError):
    """The stored graph cannot be executed as written.

    A 422 to the caller. Deliberately distinct from a node failing at run time:
    this is the workflow being malformed, which is a question for whoever drew
    it, and it is decided before anything happens rather than halfway through.
    """


@dataclass(frozen=True)
class Node:
    """One node, reduced to the four things the engine reads."""

    id: str
    node_type: str
    label: str
    category: str
    params: dict[str, str]

    def param(self, name: str, default: str = "") -> str:
        value = self.params.get(name, default)
        return value.strip() if isinstance(value, str) else str(value).strip()


@dataclass(frozen=True)
class Graph:
    nodes: dict[str, Node]
    # source id -> ordered [(source handle or None, target id)]
    edges: dict[str, list[tuple[str | None, str]]]
    triggers: tuple[Node, ...]
    # sha256 over the stored nodes and edges. Pins what actually ran: a
    # workflow is editable after it has been executed, and without this a run
    # cannot be explained later because its definition has moved. Short of the
    # immutable versioning REBUILD_CHECKLIST.md Phase 6 asks for, but it is the
    # part that makes a past run's log honest, and it needs no new table.
    fingerprint: str

    def children(self, node: Node, branch: str | None = None) -> list[Node]:
        """The nodes reached from `node`, optionally through one handle only.

        With `branch` set, only edges leaving that handle are followed. An edge
        with no handle recorded is treated as belonging to neither branch: a
        conditional whose author never connected a handle has nowhere to go, and
        guessing which side they meant is how a run takes the wrong branch
        silently.
        """
        out = self.edges.get(node.id, [])
        if branch is None:
            return [self.nodes[target] for _, target in out]
        return [self.nodes[target] for handle, target in out if handle == branch]


def _as_dicts(value: Any, what: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GraphError(f"Workflow {what} must be a list")
    return [item for item in value if isinstance(item, dict)]


def _params_of(data: dict) -> dict[str, str]:
    """Coerce the params object to str -> str.

    The builder writes every param as a string because its inputs are text
    fields, but a hand-edited graph or a future numeric input could carry
    anything. Handlers parse what they need; they should not each have to
    defend against a param being a dict.
    """
    raw = data.get("params")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            out[str(key)] = ""
        elif isinstance(value, (str, int, float, bool)):
            out[str(key)] = str(value)
        else:
            out[str(key)] = json.dumps(value, sort_keys=True)
    return out


def fingerprint(nodes: Any, edges: Any) -> str:
    """A stable digest of the graph as stored.

    Sorted keys, so two graphs differing only in JSON key order agree. Position
    is included: moving a node on the canvas changes the fingerprint. That is a
    false positive for "the workflow changed", and the alternative — deciding
    which fields are semantic — is a list that goes stale the first time the
    builder adds a field. A digest that over-reports change is safe; one that
    under-reports it says two different graphs are the same.
    """
    payload = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def parse_graph(workflow: dict) -> Graph:
    """Validate the stored graph and return it in walkable form.

    Raises GraphError for anything that would make the walk ambiguous. The
    checks are all of the form "this would otherwise be resolved by a guess".
    """
    raw_nodes = _as_dicts(workflow.get("nodes"), "nodes")
    raw_edges = _as_dicts(workflow.get("edges"), "edges")

    if not raw_nodes:
        raise GraphError("Workflow has no nodes")

    nodes: dict[str, Node] = {}
    for raw in raw_nodes:
        node_id = raw.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise GraphError("Every node needs a non-empty string id")
        if node_id in nodes:
            raise GraphError(f"Duplicate node id {node_id!r}")

        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        node_type = data.get("nodeType")
        if not isinstance(node_type, str) or not node_type:
            raise GraphError(f"Node {node_id!r} has no data.nodeType")

        category = category_of(node_type)
        if category is None:
            # Not skipped. An unknown node type means this graph is not the
            # graph its author believes it is, and it is about to phone
            # somebody.
            raise GraphError(f"Node {node_id!r} has unknown nodeType {node_type!r}")

        label = data.get("label")
        nodes[node_id] = Node(
            id=node_id,
            node_type=node_type,
            label=label if isinstance(label, str) and label else node_type,
            category=category,
            params=_params_of(data),
        )

    edges: dict[str, list[tuple[str | None, str]]] = {}
    for raw in raw_edges:
        source = raw.get("source")
        target = raw.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise GraphError("Every edge needs string source and target")
        if source not in nodes:
            raise GraphError(f"Edge from unknown node {source!r}")
        if target not in nodes:
            raise GraphError(f"Edge to unknown node {target!r}")

        handle = raw.get("sourceHandle")
        handle = handle if isinstance(handle, str) and handle else None
        if nodes[source].category == CONDITION and handle not in (
            TRUE_BRANCH,
            FALSE_BRANCH,
        ):
            raise GraphError(
                f"Edge from conditional {source!r} must leave the 'true' or "
                f"'false' handle, not {handle!r}"
            )
        edges.setdefault(source, []).append((handle, target))

    triggers = tuple(n for n in nodes.values() if n.category == TRIGGER)
    if not triggers:
        raise GraphError("Workflow has no trigger node")

    return Graph(
        nodes=nodes,
        edges=edges,
        triggers=triggers,
        fingerprint=fingerprint(workflow.get("nodes"), workflow.get("edges")),
    )


def select_trigger(graph: Graph, trigger_node_type: str | None) -> Node:
    """Pick the trigger this run starts from.

    The `trigger_node_type` parameter is honoured, which is worth saying
    because REBUILD_CHECKLIST.md records it being accepted, documented and
    ignored in the previous system. A named type that the graph does not have is
    an error rather than a fallback to the first trigger — a lab-results event
    must not run a prescription-expiry workflow because the names did not match.
    """
    if trigger_node_type:
        matching = [n for n in graph.triggers if n.node_type == trigger_node_type]
        if not matching:
            raise GraphError(
                f"Workflow has no {trigger_node_type!r} trigger"
            )
        if len(matching) > 1:
            raise GraphError(
                f"Workflow has {len(matching)} {trigger_node_type!r} triggers; "
                f"which one starts the run is ambiguous"
            )
        return matching[0]

    if len(graph.triggers) > 1:
        raise GraphError(
            f"Workflow has {len(graph.triggers)} triggers, so a run must name "
            f"which one it starts from"
        )
    return graph.triggers[0]
