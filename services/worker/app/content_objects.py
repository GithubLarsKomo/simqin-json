"""Content Object domain model for IFU families.

Core entities: ContentObject, ContentObjectRevision, ContentBinding, ContentSlot,
CompositionBinding, ApplicabilityRule, ContentMergeRecord, SuggestedTemplateCandidate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums / constants
# ---------------------------------------------------------------------------

CONTENT_OBJECT_TYPES = {"template", "section", "paragraph", "table", "image", "warning", "note", "conditional"}
SECTION_TYPES = {"intended-use", "summary", "procedure", "warnings", "storage", "materials", "limitations"}
BINDING_MODES = {"derived", "free", "proposed"}
CONTENT_STATUSES = {"draft", "approved", "deprecated", "archived"}
SLOT_TYPES = {"term", "phrase", "sentence-fragment", "sentence", "number", "quantity", "unit", "range", "percentage", "temperature", "duration", "sample-type", "analyte", "product-name", "regulatory-market", "conditional-fragment"}
OPERATORS = {"equals", "not_equals", "in", "not_in", "exists", "and", "or"}
VARIANT_GROUP_MODES = {"zero_or_more", "zero_or_one", "exactly_one"}
MAX_INHERITANCE_DEPTH = 20
ALLOWED_SOURCE_LANGUAGES = {"de-DE", "en-US"}

MIGRATION_STATUSES = {"draft", "pending_approval", "approved", "rejected", "changes_requested"}
TRANSLATION_STATUSES = {"generated", "reviewed", "approved", "rejected", "superseded"}
MULTIPLICITY_MODES = {"single", "multiple"}
SEGMENT_TYPES = {"sentence", "heading", "list-item", "table-cell", "caption", "label"}
MIGRATION_TYPES = {"split", "merge", "resegment"}


# ---------------------------------------------------------------------------
# ContentSlot
# ---------------------------------------------------------------------------


class ContentSlot:
    """A typed slot within a ContentObject."""

    def __init__(
        self,
        slot_id: str = "",
        type: str = "term",
        required: bool = False,
        default_value: str = "",
        allowed_values: list[str] | None = None,
        allowed_units: list[str] | None = None,
    ) -> None:
        self.slot_id = slot_id or _new_id()
        self.type = type
        self.required = required
        self.default_value = default_value
        self.allowed_values = allowed_values or []
        self.allowed_units = allowed_units or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "type": self.type,
            "required": self.required,
            "default_value": self.default_value,
            "allowed_values": self.allowed_values,
            "allowed_units": self.allowed_units,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentSlot":
        return cls(
            slot_id=d.get("slot_id", ""),
            type=d.get("type", "term"),
            required=d.get("required", False),
            default_value=d.get("default_value", ""),
            allowed_values=d.get("allowed_values", []),
            allowed_units=d.get("allowed_units", []),
        )


# ---------------------------------------------------------------------------
# ApplicabilityRule
# ---------------------------------------------------------------------------


class ApplicabilityRule:
    """Declarative visibility / applicability rule."""

    def __init__(
        self,
        rule_id: str = "",
        operator: str = "equals",
        parameter: str = "",
        value: str = "",
        children: list[ApplicabilityRule] | None = None,
    ) -> None:
        self.rule_id = rule_id or _new_id()
        self.operator = operator
        self.parameter = parameter
        self.value = value
        self.children = children or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "operator": self.operator,
            "parameter": self.parameter,
            "value": self.value,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ApplicabilityRule":
        return cls(
            rule_id=d.get("rule_id", ""),
            operator=d.get("operator", "equals"),
            parameter=d.get("parameter", ""),
            value=d.get("value", ""),
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )


# ---------------------------------------------------------------------------
# CompositionBinding
# ---------------------------------------------------------------------------


class CompositionBinding:
    """Binds a child ContentObject into a parent."""

    def __init__(
        self,
        composition_id: str = "",
        child_object_id: str = "",
        pinned_revision: int = 1,
        placement: str = "last",
        order: int = 0,
        visibility_rule_id: str = "",
        allow_multiple_override: bool = False,
    ) -> None:
        self.composition_id = composition_id or _new_id()
        self.child_object_id = child_object_id
        self.pinned_revision = pinned_revision
        self.placement = placement
        self.order = order
        self.visibility_rule_id = visibility_rule_id
        self.allow_multiple_override = allow_multiple_override

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "child_object_id": self.child_object_id,
            "pinned_revision": self.pinned_revision,
            "placement": self.placement,
            "order": self.order,
            "visibility_rule_id": self.visibility_rule_id,
            "allow_multiple_override": self.allow_multiple_override,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CompositionBinding":
        return cls(
            composition_id=d.get("composition_id", ""),
            child_object_id=d.get("child_object_id", ""),
            pinned_revision=d.get("pinned_revision", 1),
            placement=d.get("placement", "last"),
            order=d.get("order", 0),
            visibility_rule_id=d.get("visibility_rule_id", ""),
            allow_multiple_override=d.get("allow_multiple_override", False),
        )


# ---------------------------------------------------------------------------
# ContentObjectRevision
# ---------------------------------------------------------------------------


class ContentObjectRevision:
    """A specific revision of a ContentObject."""

    def __init__(
        self,
        object_id: str = "",
        revision: int = 1,
        canonical_content: str = "",
        sentence_segments: list[dict[str, Any]] | None = None,
        slots: list[ContentSlot] | None = None,
        visibility_rule: ApplicabilityRule | None = None,
        composed_objects: list[CompositionBinding] | None = None,
        created_at: str = "",
        created_by: str = "",
        approval_status: str = "draft",
    ) -> None:
        self.object_id = object_id
        self.revision = revision
        self.canonical_content = canonical_content
        self.sentence_segments = sentence_segments or []
        self.slots = slots or []
        self.visibility_rule = visibility_rule
        self.composed_objects = composed_objects or []
        self.created_at = created_at or _now()
        self.created_by = created_by
        self.approval_status = approval_status

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "revision": self.revision,
            "canonical_content": self.canonical_content,
            "sentence_segments": self.sentence_segments,
            "slots": [s.to_dict() for s in self.slots],
            "visibility_rule": self.visibility_rule.to_dict() if self.visibility_rule else None,
            "composed_objects": [c.to_dict() for c in self.composed_objects],
            "created_at": self.created_at,
            "created_by": self.created_by,
            "approval_status": self.approval_status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentObjectRevision":
        return cls(
            object_id=d.get("object_id", ""),
            revision=d.get("revision", 1),
            canonical_content=d.get("canonical_content", ""),
            sentence_segments=d.get("sentence_segments", []),
            slots=[ContentSlot.from_dict(s) for s in d.get("slots", [])],
            visibility_rule=ApplicabilityRule.from_dict(d["visibility_rule"]) if d.get("visibility_rule") else None,
            composed_objects=[CompositionBinding.from_dict(c) for c in d.get("composed_objects", [])],
            created_at=d.get("created_at", ""),
            created_by=d.get("created_by", ""),
            approval_status=d.get("approval_status", "draft"),
        )


# ---------------------------------------------------------------------------
# ContentBinding
# ---------------------------------------------------------------------------


class ContentBinding:
    """Describes how a ContentObject binds to its base."""

    def __init__(
        self,
        base_template_id: str = "",
        mode: str = "derived",
        detached_from_revision: int = 0,
        last_compared_revision: int = 0,
        sync_policy: str = "suggest",
        reason: str = "",
    ) -> None:
        self.base_template_id = base_template_id
        self.mode = mode
        self.detached_from_revision = detached_from_revision
        self.last_compared_revision = last_compared_revision
        self.sync_policy = sync_policy
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_template_id": self.base_template_id,
            "mode": self.mode,
            "detached_from_revision": self.detached_from_revision,
            "last_compared_revision": self.last_compared_revision,
            "sync_policy": self.sync_policy,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentBinding":
        return cls(
            base_template_id=d.get("base_template_id", ""),
            mode=d.get("mode", "derived"),
            detached_from_revision=d.get("detached_from_revision", 0),
            last_compared_revision=d.get("last_compared_revision", 0),
            sync_policy=d.get("sync_policy", "suggest"),
            reason=d.get("reason", ""),
        )


# ---------------------------------------------------------------------------
# MultiplicityRule
# ---------------------------------------------------------------------------


class MultiplicityRule:
    """Governs whether a ContentObject may appear multiple times."""

    def __init__(
        self,
        object_id: str = "",
        mode: str = "single",
        max_occurrences: int = 1,
        reason: str = "",
        revision: int = 1,
        status: str = "draft",
    ) -> None:
        self.object_id = object_id
        self.mode = mode
        self.max_occurrences = max_occurrences
        self.reason = reason
        self.revision = revision
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "mode": self.mode,
            "max_occurrences": self.max_occurrences,
            "reason": self.reason,
            "revision": self.revision,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MultiplicityRule":
        return cls(
            object_id=d.get("object_id", ""),
            mode=d.get("mode", "single"),
            max_occurrences=d.get("max_occurrences", 1),
            reason=d.get("reason", ""),
            revision=d.get("revision", 1),
            status=d.get("status", "draft"),
        )


# ---------------------------------------------------------------------------
# ContentObjectAlias
# ---------------------------------------------------------------------------


class ContentObjectAlias:
    """An alias for a ContentObject (used after merges)."""

    def __init__(self, old_id: str = "", canonical_id: str = "", created_at: str = "") -> None:
        self.old_id = old_id
        self.canonical_id = canonical_id
        self.created_at = created_at or _now()

    def to_dict(self) -> dict[str, Any]:
        return {"old_id": self.old_id, "canonical_id": self.canonical_id, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentObjectAlias":
        return cls(old_id=d.get("old_id", ""), canonical_id=d.get("canonical_id", ""), created_at=d.get("created_at", ""))


# ---------------------------------------------------------------------------
# ContentObject
# ---------------------------------------------------------------------------


class ContentObject:
    """A reusable content object within an IFU family."""

    def __init__(
        self,
        id: str = "",
        type: str = "template",
        section_type: str = "",
        origin_product_id: str = "",
        canonical_language: str = "de-DE",
        status: str = "draft",
        current_revision: int = 1,
        base_template_id: str | None = None,
        created_at: str = "",
        created_by: str = "",
        metadata: dict[str, Any] | None = None,
        revisions: list[ContentObjectRevision] | None = None,
        binding: ContentBinding | None = None,
        aliases: list[ContentObjectAlias] | None = None,
    ) -> None:
        self.id = id or _new_id()
        self.type = type
        self.section_type = section_type
        self.origin_product_id = origin_product_id
        self.canonical_language = canonical_language
        self.status = status
        self.current_revision = current_revision
        self.base_template_id = base_template_id
        self.created_at = created_at or _now()
        self.created_by = created_by
        self.metadata = metadata or {}
        self.revisions = revisions or []
        self.binding = binding
        self.aliases = aliases or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "section_type": self.section_type,
            "origin_product_id": self.origin_product_id,
            "canonical_language": self.canonical_language,
            "status": self.status,
            "current_revision": self.current_revision,
            "base_template_id": self.base_template_id,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "metadata": self.metadata,
            "revisions": [r.to_dict() for r in self.revisions],
            "binding": self.binding.to_dict() if self.binding else None,
            "aliases": [a.to_dict() for a in self.aliases],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentObject":
        return cls(
            id=d.get("id", ""),
            type=d.get("type", "template"),
            section_type=d.get("section_type", ""),
            origin_product_id=d.get("origin_product_id", ""),
            canonical_language=d.get("canonical_language", "de-DE"),
            status=d.get("status", "draft"),
            current_revision=d.get("current_revision", 1),
            base_template_id=d.get("base_template_id"),
            created_at=d.get("created_at", ""),
            created_by=d.get("created_by", ""),
            metadata=d.get("metadata", {}),
            revisions=[ContentObjectRevision.from_dict(r) for r in d.get("revisions", [])],
            binding=ContentBinding.from_dict(d["binding"]) if d.get("binding") else None,
            aliases=[ContentObjectAlias.from_dict(a) for a in d.get("aliases", [])],
        )

    def latest_revision(self) -> ContentObjectRevision | None:
        if not self.revisions:
            return None
        return max(self.revisions, key=lambda r: r.revision)

    def get_revision(self, rev: int) -> ContentObjectRevision | None:
        for r in self.revisions:
            if r.revision == rev:
                return r
        return None


# ---------------------------------------------------------------------------
# SuggestedTemplateCandidate
# ---------------------------------------------------------------------------


class SuggestedTemplateCandidate:
    """An automatically detected candidate for reusable content."""

    def __init__(
        self,
        candidate_id: str = "",
        section_type: str = "",
        segment_type: str = "",
        source_references: list[str] | None = None,
        languages: list[str] | None = None,
        similarity: float = 0.0,
        aligned_tokens: list[tuple[str, str]] | None = None,
        suggested_template: str = "",
        suggested_slots: list[ContentSlot] | None = None,
        status: str = "proposed",
        created_at: str = "",
    ) -> None:
        self.candidate_id = candidate_id or _new_id()
        self.section_type = section_type
        self.segment_type = segment_type
        self.source_references = source_references or []
        self.languages = languages or []
        self.similarity = similarity
        self.aligned_tokens = aligned_tokens or []
        self.suggested_template = suggested_template
        self.suggested_slots = suggested_slots or []
        self.status = status
        self.created_at = created_at or _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "section_type": self.section_type,
            "segment_type": self.segment_type,
            "source_references": self.source_references,
            "languages": self.languages,
            "similarity": self.similarity,
            "aligned_tokens": self.aligned_tokens,
            "suggested_template": self.suggested_template,
            "suggested_slots": [s.to_dict() for s in self.suggested_slots],
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SuggestedTemplateCandidate":
        return cls(
            candidate_id=d.get("candidate_id", ""),
            section_type=d.get("section_type", ""),
            segment_type=d.get("segment_type", ""),
            source_references=d.get("source_references", []),
            languages=d.get("languages", []),
            similarity=d.get("similarity", 0.0),
            aligned_tokens=[tuple(t) for t in d.get("aligned_tokens", [])],
            suggested_template=d.get("suggested_template", ""),
            suggested_slots=[ContentSlot.from_dict(s) for s in d.get("suggested_slots", [])],
            status=d.get("status", "proposed"),
            created_at=d.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# ContentMergeRecord
# ---------------------------------------------------------------------------


class ContentMergeRecord:
    """Auditable merge of multiple ContentObjects into one."""

    def __init__(
        self,
        merge_id: str = "",
        source_ids: list[str] | None = None,
        target_id: str = "",
        reason: str = "",
        created_by: str = "",
        approved_by: str = "",
        status: str = "draft",
        created_at: str = "",
    ) -> None:
        self.merge_id = merge_id or _new_id()
        self.source_ids = source_ids or []
        self.target_id = target_id
        self.reason = reason
        self.created_by = created_by
        self.approved_by = approved_by
        self.status = status
        self.created_at = created_at or _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "merge_id": self.merge_id,
            "source_ids": self.source_ids,
            "target_id": self.target_id,
            "reason": self.reason,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentMergeRecord":
        return cls(
            merge_id=d.get("merge_id", ""),
            source_ids=d.get("source_ids", []),
            target_id=d.get("target_id", ""),
            reason=d.get("reason", ""),
            created_by=d.get("created_by", ""),
            approved_by=d.get("approved_by", ""),
            status=d.get("status", "draft"),
            created_at=d.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# VariantGroup
# ---------------------------------------------------------------------------


class VariantGroup:
    """A group of alternative blocks with a selection mode."""

    def __init__(
        self,
        group_id: str = "",
        mode: str = "exactly_one",
        rule: ApplicabilityRule | None = None,
        members: list[str] | None = None,
    ) -> None:
        self.group_id = group_id or _new_id()
        self.mode = mode
        self.rule = rule
        self.members = members or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "mode": self.mode,
            "rule": self.rule.to_dict() if self.rule else None,
            "members": self.members,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VariantGroup":
        return cls(
            group_id=d.get("group_id", ""),
            mode=d.get("mode", "exactly_one"),
            rule=ApplicabilityRule.from_dict(d["rule"]) if d.get("rule") else None,
            members=d.get("members", []),
        )


# ---------------------------------------------------------------------------
# IFU product and release model
# ---------------------------------------------------------------------------


class IFUProduct:
    """An IFU product with its language-specific working versions and releases."""

    def __init__(
        self,
        product_id: str = "",
        name: str = "",
        primary_language: str = "de-DE",
        content_object_ids: list[str] | None = None,
        working_versions: list[IFUWorkingVersion] | None = None,
        language_releases: list[IFULanguageRelease] | None = None,
    ) -> None:
        self.product_id = product_id or _new_id()
        self.name = name
        self.primary_language = primary_language
        self.content_object_ids = content_object_ids or []
        self.working_versions = working_versions or []
        self.language_releases = language_releases or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_id": self.product_id,
            "name": self.name,
            "primary_language": self.primary_language,
            "content_object_ids": self.content_object_ids,
            "working_versions": [v.to_dict() for v in self.working_versions],
            "language_releases": [r.to_dict() for r in self.language_releases],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IFUProduct":
        return cls(
            product_id=d.get("product_id", ""),
            name=d.get("name", ""),
            primary_language=d.get("primary_language", "de-DE"),
            content_object_ids=d.get("content_object_ids", []),
            working_versions=[IFUWorkingVersion.from_dict(v) for v in d.get("working_versions", [])],
            language_releases=[IFULanguageRelease.from_dict(r) for r in d.get("language_releases", [])],
        )


class IFUWorkingVersion:
    """A working version of an IFU for a specific language."""

    def __init__(
        self,
        version_id: str = "",
        product_id: str = "",
        language: str = "de-DE",
        version: int = 1,
        status: str = "draft",
        config_values: dict[str, Any] | None = None,
        created_at: str = "",
    ) -> None:
        self.version_id = version_id or _new_id()
        self.product_id = product_id
        self.language = language
        self.version = version
        self.status = status
        self.config_values = config_values or {}
        self.created_at = created_at or _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "product_id": self.product_id,
            "language": self.language,
            "version": self.version,
            "status": self.status,
            "config_values": self.config_values,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IFUWorkingVersion":
        return cls(
            version_id=d.get("version_id", ""),
            product_id=d.get("product_id", ""),
            language=d.get("language", "de-DE"),
            version=d.get("version", 1),
            status=d.get("status", "draft"),
            config_values=d.get("config_values", {}),
            created_at=d.get("created_at", ""),
        )


class IFULanguageRelease:
    """An immutable language-specific IFU release."""

    def __init__(
        self,
        release_id: str = "",
        product_id: str = "",
        language: str = "de-DE",
        version: int = 1,
        pinned_revisions: dict[str, int] | None = None,
        release_checksum: str = "",
        created_at: str = "",
        created_by: str = "",
    ) -> None:
        self.release_id = release_id or _new_id()
        self.product_id = product_id
        self.language = language
        self.version = version
        self.pinned_revisions = pinned_revisions or {}
        self.release_checksum = release_checksum
        self.created_at = created_at or _now()
        self.created_by = created_by

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "product_id": self.product_id,
            "language": self.language,
            "version": self.version,
            "pinned_revisions": self.pinned_revisions,
            "release_checksum": self.release_checksum,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IFULanguageRelease":
        return cls(
            release_id=d.get("release_id", ""),
            product_id=d.get("product_id", ""),
            language=d.get("language", "de-DE"),
            version=d.get("version", 1),
            pinned_revisions=d.get("pinned_revisions", {}),
            release_checksum=d.get("release_checksum", ""),
            created_at=d.get("created_at", ""),
            created_by=d.get("created_by", ""),
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_inheritance_chain(
    obj: ContentObject,
    objects: dict[str, ContentObject],
    depth: int = 0,
    visited: set[str] | None = None,
) -> list[str]:
    """Validate single inheritance chain. Returns error messages."""
    errors: list[str] = []
    if visited is None:
        visited = {obj.id}
    if depth > MAX_INHERITANCE_DEPTH:
        errors.append(f"Inheritance depth exceeds {MAX_INHERITANCE_DEPTH} for {obj.id}")
        return errors
    if not obj.base_template_id:
        return errors
    if obj.base_template_id == obj.id:
        errors.append(f"Self-referencing base_template_id on {obj.id}")
        return errors
    if obj.base_template_id in visited:
        errors.append(f"Inheritance cycle detected involving {obj.id} -> {obj.base_template_id}")
        return errors
    base = objects.get(obj.base_template_id)
    if not base:
        errors.append(f"Base object {obj.base_template_id} not found for {obj.id}")
        return errors
    visited.add(obj.base_template_id)
    errors.extend(validate_inheritance_chain(base, objects, depth + 1, visited))
    return errors


def validate_composition_chain(
    obj: ContentObject,
    objects: dict[str, ContentObject],
    visited: set[str] | None = None,
) -> list[str]:
    """Validate recursive composition for cycles. Returns error messages."""
    errors: list[str] = []
    if visited is None:
        visited = {obj.id}
    rev = obj.latest_revision()
    if not rev:
        return errors
    for comp in rev.composed_objects:
        child = objects.get(comp.child_object_id)
        if not child:
            errors.append(f"Composed child {comp.child_object_id} not found")
            continue
        if child.id in visited:
            errors.append(f"Composition cycle detected: {child.id} appears twice in composition chain")
            continue
        visited.add(child.id)
        errors.extend(validate_composition_chain(child, objects, visited))
    return errors