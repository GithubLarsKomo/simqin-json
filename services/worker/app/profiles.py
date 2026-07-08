"""Authoring profiles — structure-governed rules per document type.

Each profile defines:
- allowed root fields
- allowed child blocks per parent block
- required fields
- allowed attributes per block type
- export rules
- validation rules
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Profile data
# ---------------------------------------------------------------------------

# Block types used in the authoring model
BLOCK_TYPES = {
    "section",
    "paragraph",
    "table",
    "image",
    "link",
    "topicref",
    "asset",
    "reference",
}

# Allowed attributes per block type
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "section": {"heading", "id", "paragraphs", "tables", "images", "links"},
    "paragraph": {"text", "id"},
    "table": {"caption", "id", "rows"},
    "image": {"src", "alt", "id"},
    "link": {"href", "text", "id"},
    "topicref": {"href", "navtitle", "id", "keys", "children"},
    "asset": {"type", "href", "alt"},
    "reference": {"type", "href", "text"},
}

# Required fields per block type
REQUIRED_FIELDS: dict[str, set[str]] = {
    "section": {"heading"},
    "paragraph": set(),
    "table": set(),
    "image": set(),
    "link": set(),
    "topicref": set(),
    "asset": set(),
    "reference": set(),
}


def _build_profile(
    profile_id: str,
    name: str,
    description: str,
    root_fields: list[str],
    allowed_children: dict[str, list[str]],
    export_extension: str,
) -> dict[str, Any]:
    """Build a profile dict."""
    return {
        "id": profile_id,
        "name": name,
        "description": description,
        "root_fields": root_fields,
        "allowed_children": allowed_children,
        "allowed_attributes": {
            bt: sorted(attrs)
            for bt, attrs in ALLOWED_ATTRIBUTES.items()
            if bt in allowed_children or bt in root_fields or any(
                bt in children for children in allowed_children.values()
            )
        },
        "required_fields": {
            bt: sorted(fields)
            for bt, fields in REQUIRED_FIELDS.items()
            if bt in allowed_children or bt in root_fields or any(
                bt in children for children in allowed_children.values()
            )
        },
        "export_extension": export_extension,
    }


# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict[str, Any]] = {
    "dita-topic": _build_profile(
        profile_id="dita-topic",
        name="DITA Topic",
        description="Standardkonforme DITA Topic-Datei mit Titel, Abschnitten, Absätzen, Tabellen, Bildern und Verweisen.",
        root_fields=["template", "title", "id", "sections", "topicrefs", "assets", "references"],
        allowed_children={
            "doc": ["section", "asset", "reference"],
            "section": ["paragraph", "table", "image", "link"],
            "paragraph": [],
            "table": [],
            "image": [],
            "link": [],
            "asset": [],
            "reference": [],
        },
        export_extension=".dita",
    ),
    "sop": _build_profile(
        profile_id="sop",
        name="SOP-Dokument",
        description="Ein SOP-ähnliches Dokument (Standard Operating Procedure) mit strukturierten Abschnitten.",
        root_fields=["template", "title", "id", "sections", "topicrefs", "assets", "references"],
        allowed_children={
            "doc": ["section", "asset", "reference"],
            "section": ["paragraph", "table", "image", "link"],
            "paragraph": [],
            "table": [],
            "image": [],
            "link": [],
            "asset": [],
            "reference": [],
        },
        export_extension=".xml",
    ),
    "dita-map": _build_profile(
        profile_id="dita-map",
        name="DITA Map",
        description="Eine DITA Map mit verschachtelbaren TopicRefs.",
        root_fields=["template", "title", "id", "sections", "topicrefs", "assets", "references"],
        allowed_children={
            "doc": ["topicref"],
            "topicref": ["topicref"],
        },
        export_extension=".ditamap",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_profiles() -> list[dict[str, Any]]:
    """Return all available profiles as summary dicts."""
    return [
        {
            "id": pid,
            "name": info["name"],
            "description": info["description"],
        }
        for pid, info in PROFILES.items()
    ]


def get_profile(profile_id: str) -> dict[str, Any]:
    """Return the full profile for *profile_id*.

    Raises ``ValueError`` if unknown.
    """
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown profile: {profile_id}")
    return dict(PROFILES[profile_id])


def get_allowed_actions(
    profile_id: str,
    node_path: str = "",
    block_type: str = "",
) -> dict[str, Any]:
    """Return allowed actions for a given block type in a profile.

    If *block_type* is provided, it is used directly to look up
    ``allowed_children``.  If only *node_path* is given (backward
    compat), the block type is inferred from the last path segment.

    Args:
        profile_id:  The profile identifier.
        node_path:   Dot-separated path like "sections.0" (legacy).
        block_type:  Semantic block type like "section", "paragraph",
                     "topicref", "doc".

    Returns a dict with:
    - allowed_add: list of block types that can be added as children
    - allowed_attributes: list of editable attribute names
    - required_fields: list of required field names
    - can_delete: bool
    - can_move_up: bool
    - can_move_down: bool
    """
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown profile: {profile_id}")

    profile = PROFILES[profile_id]
    allowed_children = profile["allowed_children"]

    # Determine the parent block type (for allowed_add) and current
    # block type (for attributes / can_delete).
    parent_type = block_type if block_type else (
        node_path.split(".")[-1] if node_path else "doc"
    )
    current_type = block_type if block_type else (
        node_path.split(".")[-1] if node_path else "doc"
    )

    allowed_add = list(allowed_children.get(parent_type, []))
    allowed_attrs = list(ALLOWED_ATTRIBUTES.get(current_type, set()))
    required = list(REQUIRED_FIELDS.get(current_type, set()))

    can_delete = current_type not in ("doc",)
    can_move_up = can_delete
    can_move_down = can_delete

    return {
        "allowed_add": allowed_add,
        "allowed_attributes": allowed_attrs,
        "required_fields": required,
        "can_delete": can_delete,
        "can_move_up": can_move_up,
        "can_move_down": can_move_down,
    }


def validate_with_profile(doc: dict[str, Any], profile_id: str | None = None) -> list[str]:
    """Validate an authoring document dict against its profile.

    Returns a list of error strings (empty = valid).
    Each error includes a node path for UI display.
    """
    pid = profile_id or doc.get("template", "dita-topic")
    if pid not in PROFILES:
        return [f"Unknown profile: {pid}"]

    profile = PROFILES[pid]
    errors: list[str] = []

    # Validate root fields
    allowed_root = set(profile["root_fields"])
    for key in doc:
        if key not in allowed_root:
            errors.append(f"doc: Unerlaubtes Feld '{key}'")

    # Validate required root fields
    for field in ("title", "id"):
        if field in allowed_root:
            val = doc.get(field, "")
            if not isinstance(val, str) or not val.strip():
                errors.append(f"doc: Feld '{field}' ist erforderlich")

    # Validate sections
    allowed_children = profile["allowed_children"]
    for i, sec in enumerate(doc.get("sections", [])):
        path = f"doc.sections[{i}]"
        _validate_block(sec, "section", path, allowed_children, errors)
        for j, p in enumerate(sec.get("paragraphs", [])):
            _validate_block(p, "paragraph", f"{path}.paragraphs[{j}]", allowed_children, errors)
        for j, t in enumerate(sec.get("tables", [])):
            _validate_block(t, "table", f"{path}.tables[{j}]", allowed_children, errors)
        for j, img in enumerate(sec.get("images", [])):
            _validate_block(img, "image", f"{path}.images[{j}]", allowed_children, errors)
        for j, lnk in enumerate(sec.get("links", [])):
            _validate_block(lnk, "link", f"{path}.links[{j}]", allowed_children, errors)

    # Validate topicrefs (recursive)
    _validate_topicrefs(doc.get("topicrefs", []), "doc.topicrefs", allowed_children, errors)

    # Validate assets
    for i, a in enumerate(doc.get("assets", [])):
        _validate_block(a, "asset", f"doc.assets[{i}]", allowed_children, errors)

    # Validate references
    for i, r in enumerate(doc.get("references", [])):
        _validate_block(r, "reference", f"doc.references[{i}]", allowed_children, errors)

    return errors


def _validate_block(
    block: dict[str, Any],
    block_type: str,
    path: str,
    allowed_children: dict[str, list[str]],
    errors: list[str],
) -> None:
    """Validate a single block's fields."""
    allowed_attrs = ALLOWED_ATTRIBUTES.get(block_type, set())
    required = REQUIRED_FIELDS.get(block_type, set())

    for key in block:
        if key not in allowed_attrs:
            errors.append(f"{path}: Unerlaubtes Attribut '{key}' für {block_type}")

    for field in required:
        val = block.get(field, "")
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{path}: Erforderliches Feld '{field}' fehlt")


def _validate_topicrefs(
    refs: list[dict[str, Any]],
    path: str,
    allowed_children: dict[str, list[str]],
    errors: list[str],
) -> None:
    """Recursively validate topicrefs."""
    for i, tr in enumerate(refs):
        tp = f"{path}[{i}]"
        _validate_block(tr, "topicref", tp, allowed_children, errors)
        children = tr.get("children", [])
        if children:
            _validate_topicrefs(children, f"{tp}.children", allowed_children, errors)
