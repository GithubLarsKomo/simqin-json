"""Configuration parameter catalog for IFU families."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


PARAM_TYPES = {"string", "boolean", "integer", "decimal", "enum", "string-list"}


class ConfigurationParameter:
    """A configuration parameter that may be referenced by rules."""

    def __init__(
        self,
        parameter_id: str = "",
        label: str = "",
        description: str = "",
        type: str = "string",
        default_value: str = "",
        allowed_values: list[str] | None = None,
        status: str = "draft",
        revision: int = 1,
        scope: str = "global",
        allowed_roles: list[str] | None = None,
    ) -> None:
        self.parameter_id = parameter_id or _new_id()
        self.label = label
        self.description = description
        self.type = type
        self.default_value = default_value
        self.allowed_values = allowed_values or []
        self.status = status
        self.revision = revision
        self.scope = scope
        self.allowed_roles = allowed_roles or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "label": self.label,
            "description": self.description,
            "type": self.type,
            "default_value": self.default_value,
            "allowed_values": self.allowed_values,
            "status": self.status,
            "revision": self.revision,
            "scope": self.scope,
            "allowed_roles": self.allowed_roles,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConfigurationParameter":
        return cls(
            parameter_id=d.get("parameter_id", ""),
            label=d.get("label", ""),
            description=d.get("description", ""),
            type=d.get("type", "string"),
            default_value=d.get("default_value", ""),
            allowed_values=d.get("allowed_values", []),
            status=d.get("status", "draft"),
            revision=d.get("revision", 1),
            scope=d.get("scope", "global"),
            allowed_roles=d.get("allowed_roles", []),
        )


class ConfigurationValue:
    """A pinned configuration value for an IFU working version."""

    def __init__(
        self,
        parameter_id: str = "",
        parameter_revision: int = 1,
        value: str = "",
        source: str = "manual",
        set_by: str = "",
        set_at: str = "",
    ) -> None:
        self.parameter_id = parameter_id
        self.parameter_revision = parameter_revision
        self.value = value
        self.source = source
        self.set_by = set_by
        self.set_at = set_at or _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "parameter_revision": self.parameter_revision,
            "value": self.value,
            "source": self.source,
            "set_by": self.set_by,
            "set_at": self.set_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConfigurationValue":
        return cls(
            parameter_id=d.get("parameter_id", ""),
            parameter_revision=d.get("parameter_revision", 1),
            value=d.get("value", ""),
            source=d.get("source", "manual"),
            set_by=d.get("set_by", ""),
            set_at=d.get("set_at", ""),
        )


class ConfigurationCatalog:
    """In-memory catalog of configuration parameters."""

    def __init__(self) -> None:
        self._params: dict[str, ConfigurationParameter] = {}

    def add(self, param: ConfigurationParameter) -> None:
        self._params[param.parameter_id] = param

    def get(self, param_id: str) -> ConfigurationParameter | None:
        return self._params.get(param_id)

    def validate_value(self, param_id: str, value: str) -> list[str]:
        errors: list[str] = []
        param = self._params.get(param_id)
        if not param:
            errors.append(f"Parameter {param_id} not found")
            return errors
        if param.type == "boolean" and value.lower() not in ("true", "false", "1", "0"):
            errors.append(f"Invalid boolean value: {value}")
        elif param.type == "integer":
            try:
                int(value)
            except ValueError:
                errors.append(f"Invalid integer value: {value}")
        elif param.type == "decimal":
            try:
                float(value)
            except ValueError:
                errors.append(f"Invalid decimal value: {value}")
        elif param.type == "enum" and param.allowed_values and value not in param.allowed_values:
            errors.append(f"Value {value!r} not in allowed values: {param.allowed_values}")
        return errors