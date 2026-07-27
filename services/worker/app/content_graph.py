"""Revision-aware content graph and deterministic cycle detection.

The graph separates structural cycles from duplicate inclusion. Nodes are
identified by ``object_id@revision`` and edges retain their binding context.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, order=True)
class ContentGraphNode:
    object_id: str
    revision: int

    @property
    def key(self) -> str:
        return f"{self.object_id}@{self.revision}"

    def to_dict(self) -> dict[str, Any]:
        return {"object_id": self.object_id, "revision": self.revision}


@dataclass(frozen=True)
class ContentGraphEdge:
    source: ContentGraphNode
    target: ContentGraphNode
    edge_type: str
    binding_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "edge_type": self.edge_type,
            "binding_id": self.binding_id,
        }


@dataclass(frozen=True)
class ContentCycle:
    nodes: tuple[ContentGraphNode, ...]
    edge_types: tuple[str, ...]

    @property
    def cycle_type(self) -> str:
        kinds = set(self.edge_types)
        if kinds == {"inherits-from"}:
            return "inheritance-cycle"
        if kinds == {"composes"}:
            return "composition-cycle"
        if kinds == {"alias-of"}:
            return "alias-cycle"
        return "mixed-content-cycle"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.cycle_type,
            "path": [node.key for node in self.nodes],
            "edge_types": list(self.edge_types),
        }


class ContentGraph:
    """Small deterministic directed graph for content resolution."""

    def __init__(self) -> None:
        self._nodes: set[ContentGraphNode] = set()
        self._edges: list[ContentGraphEdge] = []

    def add_node(self, node: ContentGraphNode) -> None:
        self._nodes.add(node)

    def add_edge(self, edge: ContentGraphEdge) -> None:
        self._nodes.add(edge.source)
        self._nodes.add(edge.target)
        self._edges.append(edge)

    @property
    def nodes(self) -> tuple[ContentGraphNode, ...]:
        return tuple(sorted(self._nodes))

    @property
    def edges(self) -> tuple[ContentGraphEdge, ...]:
        return tuple(
            sorted(
                self._edges,
                key=lambda edge: (
                    edge.source.key,
                    edge.target.key,
                    edge.edge_type,
                    edge.binding_id,
                ),
            )
        )

    def outgoing(self, node: ContentGraphNode) -> tuple[ContentGraphEdge, ...]:
        return tuple(edge for edge in self.edges if edge.source == node)

    def find_cycles(self) -> list[ContentCycle]:
        """Return deterministic simple DFS cycles without diamond false positives."""
        state: dict[ContentGraphNode, int] = {}
        node_stack: list[ContentGraphNode] = []
        edge_stack: list[ContentGraphEdge] = []
        cycles: dict[tuple[str, ...], ContentCycle] = {}

        def canonicalize(
            nodes: list[ContentGraphNode], edge_types: list[str]
        ) -> ContentCycle:
            # nodes includes the repeated first node at the end.
            body = nodes[:-1]
            if not body:
                return ContentCycle(tuple(nodes), tuple(edge_types))
            rotations: list[tuple[tuple[str, ...], int]] = []
            for index in range(len(body)):
                rotated = body[index:] + body[:index]
                rotations.append((tuple(node.key for node in rotated), index))
            _, start = min(rotations)
            rotated_nodes = body[start:] + body[:start]
            rotated_edges = edge_types[start:] + edge_types[:start]
            rotated_nodes.append(rotated_nodes[0])
            return ContentCycle(tuple(rotated_nodes), tuple(rotated_edges))

        def visit(node: ContentGraphNode) -> None:
            state[node] = 1
            node_stack.append(node)
            for edge in self.outgoing(node):
                target = edge.target
                target_state = state.get(target, 0)
                if target_state == 0:
                    edge_stack.append(edge)
                    visit(target)
                    edge_stack.pop()
                elif target_state == 1:
                    start = node_stack.index(target)
                    cycle_nodes = node_stack[start:] + [target]
                    cycle_edges = [item.edge_type for item in edge_stack[start:]] + [
                        edge.edge_type
                    ]
                    cycle = canonicalize(cycle_nodes, cycle_edges)
                    key = tuple(node.key for node in cycle.nodes) + cycle.edge_types
                    cycles[key] = cycle
            node_stack.pop()
            state[node] = 2

        for node in self.nodes:
            if state.get(node, 0) == 0:
                visit(node)
        return [cycles[key] for key in sorted(cycles)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def checksum(self) -> str:
        raw = json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def graph_from_edges(edges: Iterable[ContentGraphEdge]) -> ContentGraph:
    graph = ContentGraph()
    for edge in edges:
        graph.add_edge(edge)
    return graph
