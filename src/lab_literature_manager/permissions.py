"""Permission helpers for research output actions."""

from __future__ import annotations

from typing import Optional

from .models import Permission, ResearchOutput, ReviewStatus, Role


def can_perform(
    role: Role,
    permission: Permission,
    *,
    output: Optional[ResearchOutput] = None,
    actor_member_id: str = "",
) -> bool:
    """Return whether a role may perform an action on an output."""
    if not isinstance(role, Role):
        role = Role(str(role))
    if not isinstance(permission, Permission):
        permission = Permission(str(permission))
    normalized_actor = actor_member_id.strip()

    if role in {Role.PI, Role.ADMIN}:
        return True
    if permission == Permission.VIEW:
        return output is None or normalized_actor in output.owner_member_ids
    if permission == Permission.EXPORT:
        return False
    if permission == Permission.REVIEW:
        return False
    if permission == Permission.MANAGE_PERMISSIONS:
        return False
    if permission == Permission.VIEW_AUDIT_LOG:
        return False
    if permission in {Permission.DELETE, Permission.ARCHIVE, Permission.UPLOAD_ATTACHMENT}:
        return False
    if permission == Permission.DOWNLOAD_ATTACHMENT:
        return role != Role.READONLY

    if role == Role.READONLY:
        return False

    if permission == Permission.CREATE:
        return output is not None and normalized_actor in output.owner_member_ids
    if permission == Permission.EDIT:
        return (
            output is not None
            and normalized_actor in output.owner_member_ids
            and output.review_status in {ReviewStatus.DRAFT, ReviewStatus.RETURNED}
        )
    return False


def ensure_permission(
    role: Role,
    permission: Permission,
    *,
    output: Optional[ResearchOutput] = None,
    actor_member_id: str = "",
    action_label: str = "",
) -> None:
    """Raise PermissionError when an action is not allowed."""
    if can_perform(role, permission, output=output, actor_member_id=actor_member_id):
        return
    label = action_label or permission.value
    raise PermissionError(f"{role.value} cannot perform '{label}' for this research output.")
