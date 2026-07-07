from __future__ import annotations

import io
import json
import os
from typing import Any
from lxml import etree

from .mapper import MappingProfile, apply_mapping

PARSER_VERSION = "0.1.0"

# Path to canonical JSON schema
_SCHEMA_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "schemas", "canonical-json.schema.json")
)
_CANONICAL_SCHEMA = None


def _load_canonical_schema() -> dict[str, Any] | None:
    global _CANONICAL_SCHEMA
    if _CANONICAL_SCHEMA is not None:
        return _CANONICAL_SCHEMA
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
            _CANONICAL_SCHEMA = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        _CANONICAL_SCHEMA = False  # marker: not available
    return _CANONICAL_SCHEMA if _CANONICAL_SCHEMA else None


def _validate_against_schema(instance: dict[str, Any]) -> list[str]:
    """Validate *instance* against the canonical JSON schema (if available).

    Uses a lightweight recursive structural check instead of pulling in
    ``jsonschema`` as a runtime dependency.
    """
    schema = _load_canonical_schema()
    if schema is None:
        return ["Canonical JSON schema not found; validation skipped."]

    errors: list[str] = []

    def _check_node(node: dict[str, Any], path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path}: expected object, got {type(node).__name__}")
            return
        if "type" not in node:
            errors.append(f"{path}: missing 'type'")
            return
        if node["type"] not in ("element", "text"):
            errors.append(f"{path}: invalid type {node['type']!r}")
            return
        if node["type"] == "element":
            if "name" not in node:
                errors.append(f"{path}: missing 'name' in element")
            if "children" not in node or not isinstance(node["children"], list):
                errors.append(f"{path}: missing or invalid 'children'")
            else:
                for idx, child in enumerate(node["children"]):
                    _check_node(child, f"{path}/children[{idx}]")
        elif node["type"] == "text":
            if "text" not in node or not isinstance(node["text"], str):
                errors.append(f"{path}: missing or invalid 'text' in text node")

    # Top-level document structure
    if "document" not in instance:
        errors.append("root: missing 'document'")
    else:
        doc = instance["document"]
        if "source_filename" not in doc:
            errors.append("document: missing 'source_filename'")
        if "root" in doc:
            _check_node(doc["root"], "document/root")
        else:
            errors.append("document: missing 'root'")

    if "metadata" not in instance:
        errors.append("root: missing 'metadata'")

    return errors


def _node_to_json(node) -> dict[str, Any]:
    # Entity references (e.g. &xxe; when resolve_entities=False) appear as
    # lxml Entity proxy objects — they have a .tag but can't be passed to QName().
    try:
        qname = etree.QName(node)
    except (ValueError, TypeError):
        return {"type": "text", "text": str(node)}
    children: list[dict[str, Any]] = []

    if node.text and node.text.strip():
        children.append({"type": "text", "text": node.text})

    for child in node:
        children.append(_node_to_json(child))
        if child.tail and child.tail.strip():
            children.append({"type": "text", "text": child.tail})

    return {
        "type": "element",
        "name": qname.localname,
        "qualified_name": node.tag,
        "namespace": qname.namespace,
        "attributes": dict(node.attrib),
        "children": children,
    }


def _text_content(node: etree._Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _domain_json(root: etree._Element) -> dict[str, Any]:
    title = None
    sections: list[dict[str, Any]] = []

    for elem in root.iter():
        local = etree.QName(elem).localname.lower()
        if local in {"title", "h1"} and title is None:
            title = _text_content(elem)
        if local in {"section", "sect", "chapter"}:
            heading = None
            for child in elem:
                if etree.QName(child).localname.lower() in {"title", "heading", "head"}:
                    heading = _text_content(child)
                    break
            sections.append({
                "heading": heading,
                "body": _text_content(elem),
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


def _validate_dtd(xml_bytes: bytes, dtd_bytes: bytes | None) -> tuple[bool, list[dict[str, Any]], str | None]:
    if not dtd_bytes:
        return False, [], None
    errors: list[dict[str, Any]] = []
    try:
        parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
        doc = etree.fromstring(xml_bytes, parser=parser)
        dtd = etree.DTD(io.BytesIO(dtd_bytes))
        valid = dtd.validate(doc)
        for err in dtd.error_log:
            errors.append({
                "line": err.line,
                "column": err.column,
                "level": err.level_name,
                "message": err.message,
            })
        return valid, errors, "DTD"
    except Exception as exc:
        return False, [{"line": None, "column": None, "level": "ERROR", "message": str(exc)}], "DTD"


def convert_xml(
    xml_bytes: bytes,
    filename: str,
    dtd_bytes: bytes | None = None,
    mapping_profile: MappingProfile | None = None,
) -> dict[str, Any]:
    """Parse *xml_bytes*, optionally validate against *dtd_bytes*, and produce
    canonical JSON + domain JSON (via *mapping_profile* or hardcoded fallback).
    """
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        remove_blank_text=False,
        recover=False,
    )
    validation_errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        return {
            "ok": False,
            "validation": {
                "valid": False,
                "schema_type": None,
                "errors": [{"line": e.line, "column": e.column, "level": e.level_name, "message": e.message} for e in exc.error_log],
                "warnings": [],
            },
            "canonical_json": None,
            "domain_json": None,
        }

    dtd_validated, dtd_errors, schema_type = _validate_dtd(xml_bytes, dtd_bytes)
    validation_errors.extend(dtd_errors)
    if not dtd_bytes:
        warnings.append({"message": "No DTD supplied; structural validation skipped."})

    canonical = {
        "document": {
            "source_filename": filename,
            "root": _node_to_json(root),
        },
        "metadata": {
            "parser_version": PARSER_VERSION,
            "validated": bool(dtd_bytes and dtd_validated),
            "schema_type": schema_type,
            "errors": validation_errors,
            "warnings": warnings,
        },
    }

    # Schema validation warnings (non-blocking)
    schema_warnings = _validate_against_schema(canonical)
    warnings.extend({"message": sw} for sw in schema_warnings)

    # Domain JSON via mapping profile or hardcoded fallback
    domain = apply_mapping(root, mapping_profile)

    return {
        "ok": len(validation_errors) == 0,
        "validation": {
            "valid": len(validation_errors) == 0,
            "schema_type": schema_type,
            "errors": validation_errors,
            "warnings": warnings,
        },
        "canonical_json": canonical,
        "domain_json": domain,
    }
