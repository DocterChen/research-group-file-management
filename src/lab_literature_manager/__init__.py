"""Research output management utilities for research groups."""

from .models import (
    ArticleMetadata,
    AuditLog,
    Member,
    OutputType,
    PatentMetadata,
    Permission,
    Project,
    ResearchOutput,
    ReviewRecord,
    ReviewStatus,
    Role,
    SoftwareCopyrightMetadata,
)
from .permissions import can_perform
from .repository import ResearchRepository
from .web import LocalAuthStore, create_web_server

__all__ = [
    "ArticleMetadata",
    "AuditLog",
    "Member",
    "OutputType",
    "PatentMetadata",
    "Permission",
    "Project",
    "ResearchOutput",
    "ResearchRepository",
    "ReviewRecord",
    "ReviewStatus",
    "Role",
    "SoftwareCopyrightMetadata",
    "LocalAuthStore",
    "create_web_server",
    "can_perform",
]
__version__ = "0.3.0"
