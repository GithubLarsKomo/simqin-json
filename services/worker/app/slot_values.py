"""Scoped slot-value lookup shared by validation and resolution."""

from __future__ import annotations

from typing import Any


def slot_value_keys(object_id: str, revision: int, slot_id: str) -> tuple[str, str, str]:
    """Return lookup keys from most specific to backward-compatible global scope."""
    return (
        f"{object_id}@{revision}:{slot_id}",
        f"{object_id}:{slot_id}",
        slot_id,
    )


def resolve_slot_value(
    supplied: dict[str, Any],
    *,
    object_id: str,
    revision: int,
    slot_id: str,
    default: Any = None,
) -> tuple[Any, str]:
    """Resolve a slot value and report the key that supplied it.

    Supported scopes, in precedence order:
    ``object@revision:slot`` -> ``object:slot`` -> legacy global ``slot``.
    """
    for key in slot_value_keys(object_id, revision, slot_id):
        if key in supplied:
            return supplied[key], key
    return default, ""
