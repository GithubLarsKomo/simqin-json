"""Scoped-slot adapter for the Phase 6 content resolver.

This module preserves the existing resolver implementation while replacing its
single slot-render hook with the shared scoped lookup rule.  It is intentionally
small so the legacy flat ``slot_values`` contract remains backward-compatible.
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
        value, source_key = resolve_slot_value(
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
        provenance_key = f"{object_id}@{revision}:{slot_id}"
        tree.provenance.slot_values[provenance_key] = value
        if source_key:
            tree.provenance.slot_values[f"{provenance_key}#source"] = source_key

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


# Install the scoped renderer once for all users of the shared resolver module.
_resolver._render_template = _render_template_scoped

resolve_content_tree = _resolver.resolve_content_tree
ResolvedContentTree = _resolver.ResolvedContentTree
ResolutionFinding = _resolver.ResolutionFinding
