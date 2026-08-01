"""Strict type-aware validation for Phase 6 content slots."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .content_objects import ContentSlot, SLOT_TYPES


class SlotValidationFinding:
    def __init__(self, code: str, message: str, slot_id: str = "") -> None:
        self.code = code
        self.message = message
        self.slot_id = slot_id

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "slot_id": self.slot_id}


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def validate_slot_definition(slot: ContentSlot) -> list[SlotValidationFinding]:
    findings: list[SlotValidationFinding] = []
    if not slot.slot_id:
        findings.append(SlotValidationFinding("missing-slot-id", "slot_id is required"))
    if slot.type not in SLOT_TYPES:
        findings.append(SlotValidationFinding("invalid-slot-type", f"Unsupported slot type {slot.type!r}", slot.slot_id))
    if slot.allowed_units and slot.type not in {"quantity", "unit", "temperature", "duration"}:
        findings.append(SlotValidationFinding("invalid-slot-units", "allowed_units is not valid for this slot type", slot.slot_id))
    if slot.allowed_values and len(set(map(str, slot.allowed_values))) != len(slot.allowed_values):
        findings.append(SlotValidationFinding("duplicate-slot-value", "allowed_values contains duplicates", slot.slot_id))
    return findings


def validate_slot_value(slot: ContentSlot, value: Any) -> list[SlotValidationFinding]:
    findings = validate_slot_definition(slot)
    if value in (None, ""):
        if slot.required:
            findings.append(SlotValidationFinding("unresolved-required-slot", "Required slot has no value", slot.slot_id))
        return findings

    if slot.allowed_values and value not in slot.allowed_values:
        findings.append(SlotValidationFinding("invalid-slot-value", f"Value {value!r} is not allowed", slot.slot_id))

    numeric_types = {"number", "percentage", "temperature", "duration"}
    if slot.type in numeric_types and _decimal(value) is None:
        findings.append(SlotValidationFinding("invalid-slot-value", "A numeric value is required", slot.slot_id))

    if slot.type == "percentage":
        number = _decimal(value)
        if number is not None and not (Decimal("0") <= number <= Decimal("100")):
            findings.append(SlotValidationFinding("invalid-slot-value", "Percentage must be between 0 and 100", slot.slot_id))

    if slot.type == "quantity":
        if not isinstance(value, dict):
            findings.append(SlotValidationFinding("invalid-slot-value", "Quantity must be an object with value and unit", slot.slot_id))
        else:
            number = _decimal(value.get("value"))
            unit = value.get("unit")
            if number is None:
                findings.append(SlotValidationFinding("invalid-slot-value", "Quantity value must be numeric", slot.slot_id))
            if not isinstance(unit, str) or not unit:
                findings.append(SlotValidationFinding("invalid-slot-value", "Quantity unit is required", slot.slot_id))
            elif slot.allowed_units and unit not in slot.allowed_units:
                findings.append(SlotValidationFinding("invalid-slot-unit", f"Unit {unit!r} is not allowed", slot.slot_id))

    if slot.type == "range":
        if not isinstance(value, dict):
            findings.append(SlotValidationFinding("invalid-slot-value", "Range must be an object with lower and upper", slot.slot_id))
        else:
            lower = _decimal(value.get("lower"))
            upper = _decimal(value.get("upper"))
            if lower is None or upper is None:
                findings.append(SlotValidationFinding("invalid-slot-value", "Range boundaries must be numeric", slot.slot_id))
            elif lower > upper:
                findings.append(SlotValidationFinding("invalid-slot-range", "Range lower boundary exceeds upper boundary", slot.slot_id))

    return findings
