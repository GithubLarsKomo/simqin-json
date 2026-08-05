"""Minimal server-side role policy for privileged Phase 6 actions."""

from __future__ import annotations

from dataclasses import dataclass


ROLES = {"author", "reviewer", "approver"}
ROLE_PERMISSIONS = {
    "author": frozenset(),
    "reviewer": frozenset({"review"}),
    "approver": frozenset({"review", "release"}),
}


@dataclass(frozen=True)
class Phase6Principal:
    user_id: str
    role: str

    @classmethod
    def from_trusted_headers(cls, user_id: str | None, role: str | None) -> "Phase6Principal":
        normalized_user = (user_id or "").strip()
        normalized_role = (role or "").strip().lower()
        if not normalized_user:
            raise ValueError("Trusted user identity is required")
        if normalized_role not in ROLES:
            raise ValueError("Trusted role must be one of: author, reviewer, approver")
        return cls(normalized_user, normalized_role)

    def require(self, permission: str) -> None:
        if permission not in ROLE_PERMISSIONS[self.role]:
            raise PermissionError(
                f"Role {self.role!r} is not permitted to perform {permission!r} actions"
            )
