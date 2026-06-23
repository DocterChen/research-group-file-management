"""Research output management utilities for research groups."""

from .models import (
    ArticleMetadata,
    AuditLog,
    Member,
    OutputType,
    Permission,
    Project,
    ResearchOutput,
    ReviewRecord,
    ReviewStatus,
    Role,
)
from .permissions import can_perform
from .repository import ResearchRepository

__all__ = [
    "ArticleMetadata",
    "AuditLog",
    "Member",
    "OutputType",
    "Permission",
    "Project",
    "ResearchOutput",
    "ResearchRepository",
    "ReviewRecord",
    "ReviewStatus",
    "Role",
    "can_perform",
]
__version__ = "0.2.0"
