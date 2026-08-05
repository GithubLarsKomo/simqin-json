"""Deterministic validation of sibling composition placement constraints."""

from __future__ import annotations

from dataclasses import dataclass, field

from .content_objects import CompositionBinding


@dataclass(frozen=True)
class CompositionPlacementFinding:
    code: str
    message: str
    composition_id: str = ""
    anchor: str = ""
    path: tuple[str, ...] = field(default_factory=tuple)


def validate_composition_placements(
    bindings: list[CompositionBinding],
) -> list[CompositionPlacementFinding]:
    """Validate before/after constraints and detect ordering cycles.

    Anchors address sibling ``child_object_id`` values. They must resolve to
    exactly one sibling. The resulting precedence graph is checked
    deterministically for cycles and reports an exact composition-id path.
    """
    findings: list[CompositionPlacementFinding] = []
    ordered = sorted(bindings, key=lambda item: (item.order, item.composition_id))
    by_child: dict[str, list[CompositionBinding]] = {}
    by_id = {item.composition_id: item for item in ordered}
    edges: dict[str, set[str]] = {item.composition_id: set() for item in ordered}

    for item in ordered:
        by_child.setdefault(item.child_object_id, []).append(item)

    for item in ordered:
        placement = item.placement
        if placement in {"first", "last"}:
            continue
        if not (placement.startswith("before:") or placement.startswith("after:")):
            findings.append(CompositionPlacementFinding(
                "invalid-composition-anchor",
                f"Invalid placement {placement!r} on {item.composition_id}",
                item.composition_id,
            ))
            continue

        anchor = placement.split(":", 1)[1]
        candidates = by_child.get(anchor, [])
        if not candidates:
            findings.append(CompositionPlacementFinding(
                "invalid-composition-anchor",
                f"Anchor {anchor!r} is missing for {item.composition_id}",
                item.composition_id,
                anchor,
            ))
            continue
        if len(candidates) > 1:
            findings.append(CompositionPlacementFinding(
                "ambiguous-composition-anchor",
                f"Anchor {anchor!r} is ambiguous for {item.composition_id}",
                item.composition_id,
                anchor,
                tuple(candidate.composition_id for candidate in candidates),
            ))
            continue

        anchor_id = candidates[0].composition_id
        if placement.startswith("before:"):
            edges[item.composition_id].add(anchor_id)
        else:
            edges[anchor_id].add(item.composition_id)

    # first/last are global precedence constraints among siblings.
    first_ids = [item.composition_id for item in ordered if item.placement == "first"]
    last_ids = [item.composition_id for item in ordered if item.placement == "last"]
    all_ids = [item.composition_id for item in ordered]
    for first_id in first_ids:
        for other_id in all_ids:
            if other_id != first_id and other_id not in first_ids:
                edges[first_id].add(other_id)
    for last_id in last_ids:
        for other_id in all_ids:
            if other_id != last_id and other_id not in last_ids:
                edges[other_id].add(last_id)

    state: dict[str, int] = {node_id: 0 for node_id in edges}
    stack: list[str] = []
    reported: set[tuple[str, ...]] = set()

    def visit(node_id: str) -> None:
        state[node_id] = 1
        stack.append(node_id)
        for target_id in sorted(edges[node_id]):
            if state[target_id] == 0:
                visit(target_id)
            elif state[target_id] == 1:
                start = stack.index(target_id)
                cycle = tuple(stack[start:] + [target_id])
                # Canonicalize the cycle so deterministic duplicates collapse.
                core = cycle[:-1]
                rotations = [core[index:] + core[:index] for index in range(len(core))]
                canonical_core = min(rotations)
                canonical = canonical_core + (canonical_core[0],)
                if canonical not in reported:
                    reported.add(canonical)
                    findings.append(CompositionPlacementFinding(
                        "composition-placement-cycle",
                        f"Composition placement cycle detected: {' -> '.join(canonical)}",
                        path=canonical,
                    ))
        stack.pop()
        state[node_id] = 2

    for node_id in sorted(edges):
        if state[node_id] == 0:
            visit(node_id)

    return sorted(
        findings,
        key=lambda item: (item.code, item.composition_id, item.anchor, item.path, item.message),
    )
