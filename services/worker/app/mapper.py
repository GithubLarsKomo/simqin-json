"""Mapping engine — loads, validates, and applies YAML mapping profiles.

Supports XPath-based extraction rules defined in SIMQIN mapping profiles
(e.g. ``shared/mappings/simqin-default.yaml``).
"""

from __future__ import annotations

import os
from typing import Any

import yaml
from lxml import etree

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MappingValidationError(ValueError):
    """Raised when a user-supplied mapping YAML is structurally invalid."""


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class MappingRule:
    """A single mapping rule with precompiled XPath."""

    __slots__ = ("match", "target", "type", "_xpath")

    def __init__(self, match: str, target: str, type: str = "text") -> None:
        self.match = match
        self.target = target
        self.type = type
        # Precompile — raises etree.XPathSyntaxError on bad syntax
        self._xpath = etree.XPath(match)


class MappingProfile:
    """Deserialised mapping profile with precompiled XPath expressions."""

    def __init__(
        self,
        name: str,
        version: str,
        rules: list[MappingRule],
        warnings: list[str] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.rules = rules
        self.warnings = warnings or []

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    VALID_TYPES = {"text", "attribute", "object", "table"}

    @classmethod
    def _validate_raw(cls, raw: Any) -> list[str]:
        """Validate the raw parsed YAML structure.

        Returns a list of error messages.  Empty list means valid.
        """
        errors: list[str] = []

        if not isinstance(raw, dict):
            errors.append("Root value must be a YAML mapping (object).")
            return errors

        rules_raw = raw.get("rules")
        if rules_raw is None:
            errors.append("Missing required key 'rules'.")
            return errors

        if not isinstance(rules_raw, list):
            errors.append("'rules' must be a list.")
            return errors

        if not rules_raw:
            errors.append("'rules' list is empty — no mapping will be applied.")
            return errors

        for i, entry in enumerate(rules_raw):
            prefix = f"rules[{i}]"
            if not isinstance(entry, dict):
                errors.append(f"{prefix}: must be a mapping (object).")
                continue

            if "match" not in entry:
                errors.append(f"{prefix}: missing required key 'match'.")
            elif not isinstance(entry["match"], str) or not entry["match"].strip():
                errors.append(f"{prefix}: 'match' must be a non-empty string.")

            if "target" not in entry:
                errors.append(f"{prefix}: missing required key 'target'.")
            elif not isinstance(entry["target"], str) or not entry["target"].strip():
                errors.append(f"{prefix}: 'target' must be a non-empty string.")

            rule_type = entry.get("type", "text")
            if rule_type not in cls.VALID_TYPES:
                valid = ", ".join(sorted(cls.VALID_TYPES))
                errors.append(
                    f"{prefix}: invalid type {rule_type!r} — must be one of {valid}."
                )

            # Validate XPath syntax — hard error if invalid
            if "match" in entry and isinstance(entry["match"], str) and entry["match"].strip():
                try:
                    etree.XPath(entry["match"])
                except etree.XPathSyntaxError as exc:
                    errors.append(
                        f"{prefix}: invalid XPath expression {entry['match']!r} — {exc}"
                    )

        return errors

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str) -> "MappingProfile":
        """Load and parse a YAML mapping profile from *path*.

        Raises ``MappingValidationError`` for structural issues
        or invalid YAML syntax.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise MappingValidationError(f"Invalid YAML syntax in {path}: {exc}")
        if raw is None:
            raise MappingValidationError(f"Empty YAML file: {path}")
        return cls._build(raw)

    @classmethod
    def from_bytes(cls, data: bytes) -> "MappingProfile":
        """Load a YAML mapping profile from *data* bytes.

        Raises ``MappingValidationError`` for structural issues
        or invalid YAML syntax.
        """
        try:
            raw = yaml.safe_load(data)
        except yaml.YAMLError as exc:
            raise MappingValidationError(f"Invalid YAML syntax: {exc}")
        if raw is None:
            raise MappingValidationError("Empty YAML data")
        return cls._build(raw)

    @classmethod
    def _build(cls, raw: Any) -> "MappingProfile":
        """Common build step — validate, then construct."""
        errors = cls._validate_raw(raw)
        if errors:
            raise MappingValidationError("\n".join(errors))

        name: str = raw.get("profile", "unknown")
        version: str = raw.get("version", "0.0.0")
        rules_raw = raw["rules"]

        rules: list[MappingRule] = []

        for i, entry in enumerate(rules_raw):
            match_str = entry["match"]
            target_str = entry["target"]
            type_str = entry.get("type", "text")
            # XPath already validated in _validate_raw — this should not fail
            rule = MappingRule(match=match_str, target=target_str, type=type_str)
            rules.append(rule)

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


def _build_object(elem: etree._Element) -> dict[str, Any]:
    """Build an object-type mapping result from *elem*."""
    obj: dict[str, Any] = {"id": elem.get("id")}
    title_val = None
    for child in elem:
        try:
            local = etree.QName(child).localname.lower()
        except (ValueError, TypeError):
            continue
        if local in ("title", "heading", "head"):
            title_val = _extract_text(child)
            break
    obj["heading"] = title_val
    obj["body"] = _extract_text(elem)

    # Attach tables and figures scoped to this element
    tables = _extract_tables(elem)
    if tables:
        obj["tables"] = tables
    figures = _extract_figures(elem)
    if figures:
        obj["figures"] = figures

    return obj


def _extract_tables(parent: etree._Element) -> list[dict[str, Any]]:
    """Extract tables from *parent* using DITA and HTML conventions."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for elem in parent.iter():
        try:
            local = etree.QName(elem).localname.lower()
        except (ValueError, TypeError):
            continue
        if local not in ("table", "simpletable"):
            continue
        key = str(id(elem))
        if key in seen:
            continue
        seen.add(key)
        results.append(_table_to_dict(elem))
    return results


def _extract_figures(parent: etree._Element) -> list[dict[str, Any]]:
    """Extract <fig> elements from *parent*."""
    figs: list[dict[str, Any]] = []
    for elem in parent.iter():
        try:
            local = etree.QName(elem).localname.lower()
        except (ValueError, TypeError):
            continue
        if local != "fig":
            continue
        fig: dict[str, Any] = {}
        for child in elem:
            try:
                cl = etree.QName(child).localname.lower()
            except (ValueError, TypeError):
                continue
            if cl == "title" and "title" not in fig:
                fig["title"] = _extract_text(child)
            if cl == "image":
                fig["image"] = _resolve_href(child)
        figs.append(fig)
    return figs


def _table_to_dict(table_elem: etree._Element) -> dict[str, Any]:
    """Convert a table/simpletable element to a dictionary."""
    rows: list[list[str]] = []

    # DITA <tgroup>/<thead>/<tbody>/<row>/<entry>
    for row in table_elem.iterfind(".//row"):
        cells = [
            " ".join(cell.itertext()).strip()
            for cell in row.iterfind(".//entry")
        ]
        if cells:
            rows.append(cells)

    # DITA <simpletable>/<strow>/<stentry>
    if not rows:
        for strow in table_elem.iterfind(".//strow"):
            cells = [
                " ".join(cell.itertext()).strip()
                for cell in strow.iterfind(".//stentry")
            ]
            if cells:
                rows.append(cells)

    # HTML <tr>/<td> / <th>
    if not rows:
        for tr in table_elem.iterfind(".//tr"):
            cells = []
            for cell in tr.iterfind(".//td"):
                cells.append(" ".join(cell.itertext()).strip())
            for cell in tr.iterfind(".//th"):
                cells.append(" ".join(cell.itertext()).strip())
            if cells:
                rows.append(cells)

    result: dict[str, Any] = {"rows": rows}

    for caption in table_elem.iterfind(".//caption"):
        result["caption"] = " ".join(caption.itertext()).strip()
        break
    if "caption" not in result:
        for title in table_elem.iterfind(".//title"):
            result["caption"] = " ".join(title.itertext()).strip()
            break

    return result


def _resolve_href(elem: etree._Element) -> str:
    """Return the first non-empty href-like attribute."""
    for attr in ("href", "src", "fileref", "data"):
        val = elem.get(attr) or elem.get(attr, "")
        if val:
            return val
    # xlink:href via namespace
    for ns, val in elem.attrib.items():
        if ns.endswith("href") or ns.endswith("}href"):
            return val
    return ""


# ---------------------------------------------------------------------------
# Main apply function
# ---------------------------------------------------------------------------


def apply_mapping(
    root: etree._Element,
    profile: MappingProfile | None,
) -> dict[str, Any]:
    """Apply a mapping *profile* to *root* and return a domain-JSON dict.

    When *profile* is ``None`` the hardcoded default logic is used (keeps
    backward compatibility).
    """
    if profile is None:
        return _domain_json_hardcoded(root)

    result: dict[str, Any] = {}
    list_targets: dict[str, list[Any]] = {}
    mapping_warnings: list[str] = list(profile.warnings)

    for rule in profile.rules:
        target = rule.target
        try:
            matches = rule._xpath(root)
        except Exception:
            mapping_warnings.append(
                f"XPath evaluation failed for {rule.match!r} (rule target={target!r})."
            )
            continue

        if not matches:
            mapping_warnings.append(
                f"XPath {rule.match!r} (target={target!r}) matched 0 nodes."
            )
            continue

        # Array target (suffix [])
        if target.endswith("[]"):
            key = target[:-2]
            if key not in list_targets:
                list_targets[key] = []
            for m in matches:
                if rule.type == "object":
                    if isinstance(m, etree._Element):
                        list_targets[key].append(_build_object(m))
                elif rule.type == "table":
                    if isinstance(m, etree._Element):
                        list_targets[key].append(_table_to_dict(m))
                else:  # text
                    list_targets[key].append(
                        _extract_text(m) if isinstance(m, etree._Element) else str(m)
                    )
        else:
            # Scalar target — take first match only
            if target in result:
                continue
            for m in matches[:1]:
                if rule.type == "text":
                    result[target] = (
                        _extract_text(m) if isinstance(m, etree._Element) else str(m)
                    )
                elif rule.type == "attribute":
                    result[target] = str(m)
                break

    # Merge list targets into result
    result.update(list_targets)

    # Append mapping metadata
    result["_mapping"] = {
        "profile": profile.name,
        "version": profile.version,
        "rule_count": len(profile.rules),
        "warnings": mapping_warnings,
    }

    return result


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
            section_body = _extract_text(elem)
            section_tables = _extract_tables(elem)
            section_figures = _extract_figures(elem)
            entry: dict[str, Any] = {
                "heading": heading,
                "body": section_body,
            }
            if section_tables:
                entry["tables"] = section_tables
            if section_figures:
                entry["figures"] = section_figures
            sections.append(entry)

    return {
        "title": title,
        "sections": sections,
        "metadata": {
            "root_element": etree.QName(root).localname,
        },
    }