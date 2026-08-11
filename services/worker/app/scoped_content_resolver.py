"""Scoped-slot adapter for the Phase 6 content resolver.

This module preserves the existing resolver implementation while replacing its
single slot-render hook with the shared scoped lookup rule. It is intentionally
small so the legacy flat ``slot_values`` contract remains backward-compatible.

The adapter is a compatibility layer only. Provenance remains canonical and
contains resolved slot values under ``object@revision:slot`` keys; lookup-source
metadata is deliberately not persisted into release-relevant provenance.
"""

from __future__ import annotations

import re
from typing import Any

from . import content_resolver as _resolver
from .content_objects import ContentSlot
from .slot_values import resolve_slot_value


def _render_template_scoped(
    template: str,
    slots: list[ContentSlot],
    supplied: dict[str, Any],
    tree: _resolver.ResolvedContentTree,
    object_id: str,
    revision: int,
) -> tuple[str, dict[str, Any]]:
    definitions = {slot.slot_id: slot for slot in slots}
    values: dict[str, Any] = {}
    for slot_id, slot in definitions.items():
        value, _source_key = resolve_slot_value(
            supplied,
            object_id=object_id,
            revision=revision,
            slot_id=slot_id,
            default=slot.default_value,
        )
        if slot.required and (value is None or value == ""):
            tree.findings.append(
                _resolver.ResolutionFinding(
                    "unresolved-required-slot",
                    "FATAL",
                    f"Required slot {slot_id} has no value",
                    object_id,
                    revision,
                    details={"slot_id": slot_id},
                )
            )
        values[slot_id] = value
        tree.provenance.slot_values[f"{object_id}@{revision}:{slot_id}"] = value

    def replace(match: re.Match[str]) -> str:
        slot_id = match.group(1)
        if slot_id not in definitions:
            tree.findings.append(
                _resolver.ResolutionFinding(
                    "unknown-slot-placeholder",
                    "WARNING",
                    f"Unknown slot placeholder {slot_id} in {object_id}@{revision}",
                    object_id,
                    revision,
                )
            )
            return match.group(0)
        value = values.get(slot_id)
        return "" if value is None else str(value)

    return _resolver._PLACEHOLDER.sub(replace, template), values


# Install the scoped renderer for all users of the shared resolver module.
# Python's module cache makes ordinary imports idempotent; assigning the same
# deterministic function again during an explicit module reload is harmless.
_resolver._render_template = _render_template_scoped

resolve_content_tree = _resolver.resolve_content_tree
ResolvedContentTree = _resolver.ResolvedContentTree
ResolutionFinding = _resolver.ResolutionFinding
