"""Pure evaluator for ApplicabilityRule — no eval, no side effects."""

from __future__ import annotations

from typing import Any

from .content_objects import ApplicabilityRule, OPERATORS


def evaluate_rule(rule: ApplicabilityRule, params: dict[str, Any]) -> bool:
    """Evaluate an ApplicabilityRule against the given parameter values.

    Args:
        rule: The rule to evaluate.
        params: A flat dict of parameter_id -> value.

    Returns:
        True if the rule matches, False otherwise.

    Raises:
        ValueError: If the rule structure is invalid.
    """
    op = rule.operator

    if op in ("and", "or"):
        if not rule.children:
            raise ValueError(f"Operator {op!r} requires at least one child rule")
        results = [evaluate_rule(c, params) for c in rule.children]
        if op == "and":
            return all(results)
        return any(results)

    # Leaf operators
    if op == "exists":
        return rule.parameter in params and params[rule.parameter] not in ("", None)

    if op == "in":
        value = params.get(rule.parameter, "")
        allowed = [v.strip() for v in rule.value.split(",")] if rule.value else []
        return value in allowed

    if op == "not_in":
        value = params.get(rule.parameter, "")
        allowed = [v.strip() for v in rule.value.split(",")] if rule.value else []
        return value not in allowed

    if op == "equals":
        return str(params.get(rule.parameter, "")) == rule.value

    if op == "not_equals":
        return str(params.get(rule.parameter, "")) != rule.value

    raise ValueError(f"Unknown operator {op!r}")


def validate_rule(rule: ApplicabilityRule, available_params: set[str]) -> list[str]:
    """Validate a rule structure. Returns validation errors."""
    errors: list[str] = []

    if rule.operator not in OPERATORS:
        errors.append(f"Invalid operator {rule.operator!r}")
        return errors

    if rule.operator in ("and", "or"):
        if not rule.children:
            errors.append(f"Operator {rule.operator!r} requires at least one child")
        for i, child in enumerate(rule.children):
            child_errors = validate_rule(child, available_params)
            for ce in child_errors:
                errors.append(f"children[{i}]: {ce}")
        return errors

    # Leaf operators
    if rule.operator in ("equals", "not_equals", "in", "not_in", "exists"):
        if rule.parameter and rule.parameter not in available_params:
            errors.append(f"Parameter {rule.parameter!r} not found in available parameters")
    else:
        errors.append(f"Operator {rule.operator!r} requires a parameter reference")

    if rule.operator in ("equals", "not_equals") and rule.children:
        errors.append(f"Operator {rule.operator!r} does not support child rules")

    return errors