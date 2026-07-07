"""Mapping engine — loads YAML mapping profiles and applies them to XML trees.

Supports XPath-based extraction rules defined in SIMQIN mapping profiles
(e.g. ``shared/mappings/simqin-default.yaml``).
"""

from __future__ import annotations

import os
from typing import Any

import yaml
from lxml import etree


class MappingRule:
    """A single mapping rule extracted from a YAML profile."""

    __slots__ = ("match", "target", "type")

    def __init__(self, match: str, target: str, type: str = "text") -> None:
        self.match = match
        self.target = target
        self.type = type


class MappingProfile:
    """Deserialised mapping profile with compiled XPath expressions."""

    def __init__(self, name: str, version: str, rules: list[MappingRule]) -> None:
        self.name = name
        self.version = version
        self.rules = rules

    @classmethod
    def from_yaml(cls, path: str) -> "MappingProfile":
        """Load and parse a YAML mapping profile from *path*."""
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        name: str = raw.get("profile", "unknown")
        version: str = raw.get("version", "0.0.0")
        rules: list[MappingRule] = []
        for entry in raw.get("rules", []):
            rules.append(MappingRule(
                match=entry["match"],
                target=entry["target"],
                type=entry.get("type", "text"),
            ))
        return cls(name=name, version=version, rules=rules)

    @classmethod
    def from_bytes(cls, data: bytes) -> "MappingProfile":
        """Load a YAML mapping profile from *data* bytes."""
        raw = yaml.safe_load(data)
        name: str = raw.get("profile", "unknown")
        version: str = raw.get("version", "0.0.0")
        rules: list[MappingRule] = []
        for entry in raw.get("rules", []):
            rules.append(MappingRule(
                match=entry["match"],
                target=entry["target"],
                type=entry.get("type", "text"),
            ))
        return cls(name=name, version=version, rules=rules)

    @staticmethod
    def default_profile_path() -> str:
        """Return the canonical path to the shipped default mapping profile."""
        here = os.path.dirname(__file__)  # services/worker/app/
        return os.path.normpath(
            os.path.join(here, "..", "..", "..", "shared", "mappings", "simqin-default.yaml")
        )


def _extract_text(elem: etree._Element) -> str:
    """Return the joined, whitespace-normalised text content of *elem*."""
    return " ".join("".join(elem.itertext()).split())


def _build_object(elem: etree._Element, rule: MappingRule) -> dict[str, Any] | None:
    """Build an object-type mapping result from *elem*."""
    obj: dict[str, Any] = {}
    obj["id"] = elem.get("id")
    # Recurse into child elements and try to extract text from first title/heading child
    title_val = None
    for child in elem:
        local = etree.QName(child).localname.lower()
        if local in ("title", "heading", "head"):
            title_val = _extract_text(child)
            break
    obj["heading"] = title_val
    obj["body"] = _extract_text(elem)
    return obj


def apply_mapping(root: etree._Element, profile: MappingProfile | None) -> dict[str, Any]:
    """Apply a mapping *profile* to *root* and return a domain-JSON dict.

    When *profile* is ``None`` the hardcoded default logic is used (keeps
    backward compatibility).
    """
    if profile is None:
        return _domain_json_hardcoded(root)

    result: dict[str, Any] = {}
    list_targets: dict[str, list[Any]] = {}

    for rule in profile.rules:
        try:
            xpath_expr = etree.XPath(rule.match)
            matches = xpath_expr(root)
        except etree.XPathSyntaxError:
            continue

        target = rule.target

        # Array target (suffix [])
        if target.endswith("[]"):
            key = target[:-2]
            if key not in list_targets:
                list_targets[key] = []
            for m in matches:
                if rule.type == "object":
                    obj = _build_object(m, rule)
                    if obj is not None:
                        list_targets[key].append(obj)
                elif rule.type == "table":
                    list_targets[key].append(_build_table(m))
                else:  # text
                    list_targets[key].append(_extract_text(m))
        else:
            # Scalar target — take first match only
            if target in result:
                continue
            for m in matches[:1]:
                if rule.type == "text":
                    result[target] = _extract_text(m) if isinstance(m, etree._Element) else str(m)
                elif rule.type == "attribute":
                    result[target] = str(m)
                break

    # Merge list targets into result
    result.update(list_targets)
    return result


def _build_table(table_elem: etree._Element) -> dict[str, Any]:
    """Extract a simple table representation from *table_elem*."""
    rows: list[list[str]] = []
    for row in table_elem.iterfind(".//row"):
        cells = [" ".join(cell.itertext()).strip() for cell in row.iterfind(".//entry")]
        rows.append(cells)
    return {"rows": rows}


# ---------------------------------------------------------------------------
# Hardcoded fallback (original _domain_json logic)
# ---------------------------------------------------------------------------

def _domain_json_hardcoded(root: etree._Element) -> dict[str, Any]:
    """Original hardcoded domain-JSON extraction (kept for backward compat)."""
    title = None
    sections: list[dict[str, Any]] = []

    for elem in root.iter():
        try:
            local = etree.QName(elem).localname.lower()
        except (ValueError, TypeError):
            continue  # skip non-element nodes (e.g. entity references)
        if local in {"title", "h1"} and title is None:
            title = _extract_text(elem)
        if local in {"section", "sect", "chapter"}:
            heading = None
            for child in elem:
                try:
                    child_local = etree.QName(child).localname.lower()
                except (ValueError, TypeError):
                    continue
                if child_local in {"title", "heading", "head"}:
                    heading = _extract_text(child)
                    break
            sections.append({
                "heading": heading,
                "body": _extract_text(elem),
                "tables": [],
                "figures": [],
            })

    return {
        "title": title,
        "sections": sections,
        "metadata": {
            "root_element": etree.QName(root).localname,
        },
    }