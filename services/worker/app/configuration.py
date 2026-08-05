"""Revision-aware configuration parameter catalog for IFU families."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


PARAM_TYPES = {"string", "boolean", "integer", "decimal", "enum", "string-list"}
PARAM_STATUSES = {"draft", "approved", "deprecated", "archived"}
_INTEGER_STRING = re.compile(r"^[+-]?\d+$")


class ConfigurationParameter:
    """One immutable-in-practice revision of a configuration parameter."""

    def __init__(
        self,
        parameter_id: str = "",
        label: str = "",
        description: str = "",
        type: str = "string",
        default_value: Any = "",
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
        self.allowed_values = list(allowed_values or [])
        self.status = status
        self.revision = revision
        self.scope = scope
        self.allowed_roles = list(allowed_roles or [])

    def key(self) -> tuple[str, int]:
        return self.parameter_id, self.revision

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "label": self.label,
            "description": self.description,
            "type": self.type,
            "default_value": self.default_value,
            "allowed_values": list(self.allowed_values),
            "status": self.status,
            "revision": self.revision,
            "scope": self.scope,
            "allowed_roles": list(self.allowed_roles),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConfigurationParameter":
        return cls(**{key: d.get(key, default) for key, default in {
            "parameter_id": "", "label": "", "description": "", "type": "string",
            "default_value": "", "allowed_values": [], "status": "draft", "revision": 1,
            "scope": "global", "allowed_roles": [],
        }.items()})


class ConfigurationValue:
    """A value pinned to an exact parameter revision."""

    def __init__(self, parameter_id: str = "", parameter_revision: int = 1,
                 value: Any = "", source: str = "manual", set_by: str = "",
                 set_at: str = "") -> None:
        self.parameter_id = parameter_id
        self.parameter_revision = parameter_revision
        self.value = value
        self.source = source
        self.set_by = set_by
        self.set_at = set_at or _now()

    def to_dict(self) -> dict[str, Any]:
        return dict(parameter_id=self.parameter_id, parameter_revision=self.parameter_revision,
                    value=self.value, source=self.source, set_by=self.set_by, set_at=self.set_at)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConfigurationValue":
        return cls(parameter_id=d.get("parameter_id", ""), parameter_revision=d.get("parameter_revision", 1),
                   value=d.get("value", ""), source=d.get("source", "manual"),
                   set_by=d.get("set_by", ""), set_at=d.get("set_at", ""))


class ConfigurationCatalog:
    """In-memory revision store keyed by ``(parameter_id, revision)``."""

    def __init__(self) -> None:
        self._params: dict[tuple[str, int], ConfigurationParameter] = {}

    def add_parameter_revision(self, param: ConfigurationParameter) -> None:
        errors = self.validate_parameter(param)
        if errors:
            raise ValueError("; ".join(errors))
        if param.key() in self._params:
            raise ValueError(f"Duplicate parameter revision {param.parameter_id}@{param.revision}")
        self._params[param.key()] = ConfigurationParameter.from_dict(param.to_dict())

    def add(self, param: ConfigurationParameter) -> None:
        self.add_parameter_revision(param)

    def get_revision(self, parameter_id: str, revision: int) -> ConfigurationParameter | None:
        value = self._params.get((parameter_id, revision))
        return ConfigurationParameter.from_dict(value.to_dict()) if value else None

    def get(self, parameter_id: str) -> ConfigurationParameter | None:
        revisions = [p for (pid, _), p in self._params.items() if pid == parameter_id]
        if not revisions:
            return None
        value = max(revisions, key=lambda p: p.revision)
        return ConfigurationParameter.from_dict(value.to_dict())

    def get_latest_approved(self, parameter_id: str) -> ConfigurationParameter | None:
        revisions = [p for (pid, _), p in self._params.items()
                     if pid == parameter_id and p.status == "approved"]
        if not revisions:
            return None
        value = max(revisions, key=lambda p: p.revision)
        return ConfigurationParameter.from_dict(value.to_dict())

    def validate_parameter(self, param: ConfigurationParameter) -> list[str]:
        errors: list[str] = []
        if not param.parameter_id:
            errors.append("parameter_id is required")
        if param.revision < 1:
            errors.append("revision must be positive")
        if param.type not in PARAM_TYPES:
            errors.append(f"Invalid parameter type: {param.type}")
        if param.status not in PARAM_STATUSES:
            errors.append(f"Invalid parameter status: {param.status}")
        if param.type == "enum" and not param.allowed_values:
            errors.append("enum requires allowed_values")
        if not errors:
            errors.extend(self._validate_typed_value(param, param.default_value, allow_empty=True))
        return errors

    def _validate_typed_value(self, param: ConfigurationParameter, value: Any,
                              allow_empty: bool = False) -> list[str]:
        if allow_empty and value in (None, "", []):
            return []
        errors: list[str] = []
        if param.type == "string" and not isinstance(value, str):
            errors.append("value must be a string")
        elif param.type == "boolean" and not isinstance(value, bool):
            errors.append("value must be a boolean")
        elif param.type == "integer":
            is_integer = (
                isinstance(value, int) and not isinstance(value, bool)
            ) or (
                isinstance(value, str) and bool(_INTEGER_STRING.fullmatch(value.strip()))
            )
            if not is_integer:
                errors.append("value must be an integer")
        elif param.type == "decimal":
            try:
                Decimal(str(value))
            except (InvalidOperation, ValueError):
                errors.append("value must be decimal-compatible")
        elif param.type == "enum" and value not in param.allowed_values:
            errors.append(f"value {value!r} is not allowed")
        elif param.type == "string-list" and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            errors.append("value must be a list of strings")
        return errors

    def validate_configuration_value(self, value: ConfigurationValue,
                                     role: str | None = None,
                                     require_approved: bool = False) -> list[str]:
        param = self._params.get((value.parameter_id, value.parameter_revision))
        if not param:
            return [f"Parameter revision {value.parameter_id}@{value.parameter_revision} not found"]
        errors: list[str] = []
        if require_approved and param.status != "approved":
            errors.append(f"Parameter revision {value.parameter_id}@{value.parameter_revision} is not approved")
        if role and param.allowed_roles and role not in param.allowed_roles:
            errors.append(f"Role {role!r} is not allowed for {value.parameter_id}")
        errors.extend(self._validate_typed_value(param, value.value))
        return errors

    def validate_value(self, param_id: str, value: Any) -> list[str]:
        param = self.get(param_id)
        if not param:
            return [f"Parameter {param_id} not found"]
        return self._validate_typed_value(param, value)

    def snapshot(self, values: list[ConfigurationValue], require_approved: bool = True) -> tuple[dict[str, Any], list[str]]:
        errors: list[str] = []
        rows: list[dict[str, Any]] = []
        for value in sorted(values, key=lambda item: (item.parameter_id, item.parameter_revision)):
            errors.extend(self.validate_configuration_value(value, require_approved=require_approved))
            rows.append(value.to_dict())
        payload = {"parameters": rows}
        return json.loads(json.dumps(payload, sort_keys=True)), errors
