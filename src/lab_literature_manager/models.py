"""Domain models for the research output management MVP."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

CURRENT_YEAR_UPPER_BOUND = 2100


def utc_now_iso() -> str:
    """Return a stable ISO-8601 timestamp in UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_text(value: str) -> str:
    return value.strip()


def _unique_cleaned(values: Iterable[str], *, lower: bool = False, sort_values: bool = False) -> List[str]:
    materialized: List[str] = []
    seen = set()
    for raw in values:
        cleaned = str(raw).strip()
        if not cleaned:
            continue
        normalized = cleaned.lower() if lower else cleaned
        if normalized in seen:
            continue
        seen.add(normalized)
        materialized.append(normalized if lower else cleaned)
    if sort_values:
        return sorted(materialized)
    return materialized


class OutputType(str, Enum):
    ARTICLE = "article"
    PATENT = "patent"
    SOFTWARE_COPYRIGHT = "software_copyright"
    CONFERENCE = "conference"
    PROJECT_MATERIAL = "project_material"
    DATASET_CODE = "dataset_code"


OUTPUT_TYPE_LABELS = {
    OutputType.ARTICLE: "论文",
    OutputType.PATENT: "专利",
    OutputType.SOFTWARE_COPYRIGHT: "软件著作权",
    OutputType.CONFERENCE: "会议成果",
    OutputType.PROJECT_MATERIAL: "项目/基金材料",
    OutputType.DATASET_CODE: "数据与代码",
}

OUTPUT_TYPE_ID_PREFIXES = {
    OutputType.ARTICLE: "LW",
    OutputType.PATENT: "ZL",
    OutputType.SOFTWARE_COPYRIGHT: "RZ",
    OutputType.CONFERENCE: "HY",
    OutputType.PROJECT_MATERIAL: "XM",
    OutputType.DATASET_CODE: "SJ",
}


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RETURNED = "returned"
    APPROVED = "approved"
    ARCHIVED = "archived"


REVIEW_STATUS_LABELS = {
    ReviewStatus.DRAFT: "草稿",
    ReviewStatus.SUBMITTED: "待审核",
    ReviewStatus.RETURNED: "已退回",
    ReviewStatus.APPROVED: "已通过",
    ReviewStatus.ARCHIVED: "已归档",
}


class Role(str, Enum):
    PI = "pi"
    ADMIN = "admin"
    MEMBER = "member"
    READONLY = "readonly"


ROLE_LABELS = {
    Role.PI: "PI",
    Role.ADMIN: "管理员",
    Role.MEMBER: "成员",
    Role.READONLY: "只读",
}


def output_type_label(output_type: OutputType | str) -> str:
    normalized = output_type if isinstance(output_type, OutputType) else OutputType(str(output_type))
    return OUTPUT_TYPE_LABELS[normalized]


def output_type_id_prefix(output_type: OutputType | str) -> str:
    normalized = output_type if isinstance(output_type, OutputType) else OutputType(str(output_type))
    return OUTPUT_TYPE_ID_PREFIXES[normalized]


def review_status_label(status: ReviewStatus | str) -> str:
    normalized = status if isinstance(status, ReviewStatus) else ReviewStatus(str(status))
    return REVIEW_STATUS_LABELS[normalized]


def role_label(role: Role | str) -> str:
    normalized = role if isinstance(role, Role) else Role(str(role))
    return ROLE_LABELS[normalized]


class Permission(str, Enum):
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    ARCHIVE = "archive"
    UPLOAD_ATTACHMENT = "upload_attachment"
    DOWNLOAD_ATTACHMENT = "download_attachment"
    EXPORT = "export"
    REVIEW = "review"
    MANAGE_PERMISSIONS = "manage_permissions"
    VIEW_AUDIT_LOG = "view_audit_log"


@dataclass(frozen=True)
class ArticleMetadata:
    """Article-specific metadata for publication outputs."""

    article_type: str
    journal: str = ""
    doi: str = ""
    issn: str = ""
    pmid: str = ""
    publication_year: Optional[int] = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    impact_factor: str = ""
    jcr_quartile: str = ""
    cas_quartile: str = ""
    submission_status: str = ""
    first_authors: List[str] = field(default_factory=list)
    corresponding_authors: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _clean_text(self.article_type):
            raise ValueError("Article type must not be empty.")
        if self.publication_year is not None and (
            self.publication_year < 0 or self.publication_year > CURRENT_YEAR_UPPER_BOUND
        ):
            raise ValueError(
                f"Article publication year must be between 0 and {CURRENT_YEAR_UPPER_BOUND}."
            )
        object.__setattr__(self, "article_type", _clean_text(self.article_type))
        object.__setattr__(self, "journal", _clean_text(self.journal))
        object.__setattr__(self, "doi", _clean_text(self.doi))
        object.__setattr__(self, "issn", _clean_text(self.issn))
        object.__setattr__(self, "pmid", _clean_text(self.pmid))
        object.__setattr__(self, "volume", _clean_text(self.volume))
        object.__setattr__(self, "issue", _clean_text(self.issue))
        object.__setattr__(self, "pages", _clean_text(self.pages))
        object.__setattr__(self, "impact_factor", _clean_text(self.impact_factor))
        object.__setattr__(self, "jcr_quartile", _clean_text(self.jcr_quartile))
        object.__setattr__(self, "cas_quartile", _clean_text(self.cas_quartile))
        object.__setattr__(self, "submission_status", _clean_text(self.submission_status))
        object.__setattr__(self, "first_authors", _unique_cleaned(self.first_authors))
        object.__setattr__(self, "corresponding_authors", _unique_cleaned(self.corresponding_authors))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_type": self.article_type,
            "journal": self.journal,
            "doi": self.doi,
            "issn": self.issn,
            "pmid": self.pmid,
            "publication_year": self.publication_year,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "impact_factor": self.impact_factor,
            "jcr_quartile": self.jcr_quartile,
            "cas_quartile": self.cas_quartile,
            "submission_status": self.submission_status,
            "first_authors": list(self.first_authors),
            "corresponding_authors": list(self.corresponding_authors),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArticleMetadata":
        return cls(
            article_type=str(data.get("article_type", "")),
            journal=str(data.get("journal", "")),
            doi=str(data.get("doi", "")),
            issn=str(data.get("issn", "")),
            pmid=str(data.get("pmid", "")),
            publication_year=data.get("publication_year"),
            volume=str(data.get("volume", "")),
            issue=str(data.get("issue", "")),
            pages=str(data.get("pages", "")),
            impact_factor=str(data.get("impact_factor", "")),
            jcr_quartile=str(data.get("jcr_quartile", "")),
            cas_quartile=str(data.get("cas_quartile", "")),
            submission_status=str(data.get("submission_status", "")),
            first_authors=list(data.get("first_authors", [])),
            corresponding_authors=list(data.get("corresponding_authors", [])),
        )


@dataclass(frozen=True)
class PatentMetadata:
    """Patent-specific metadata for patent outputs."""

    patent_number: str = ""
    application_number: str = ""
    title: str = ""
    country_code: str = ""
    kind_code: str = ""
    inventors: List[str] = field(default_factory=list)
    assignees: List[str] = field(default_factory=list)
    application_date: str = ""
    publication_date: str = ""
    status: str = ""
    abstract: str = ""
    url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "patent_number", _clean_text(self.patent_number))
        object.__setattr__(self, "application_number", _clean_text(self.application_number))
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "country_code", _clean_text(self.country_code))
        object.__setattr__(self, "kind_code", _clean_text(self.kind_code))
        object.__setattr__(self, "inventors", _unique_cleaned(self.inventors))
        object.__setattr__(self, "assignees", _unique_cleaned(self.assignees))
        object.__setattr__(self, "application_date", _clean_text(self.application_date))
        object.__setattr__(self, "publication_date", _clean_text(self.publication_date))
        object.__setattr__(self, "status", _clean_text(self.status))
        object.__setattr__(self, "abstract", _clean_text(self.abstract))
        object.__setattr__(self, "url", _clean_text(self.url))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patent_number": self.patent_number,
            "application_number": self.application_number,
            "title": self.title,
            "country_code": self.country_code,
            "kind_code": self.kind_code,
            "inventors": list(self.inventors),
            "assignees": list(self.assignees),
            "application_date": self.application_date,
            "publication_date": self.publication_date,
            "status": self.status,
            "abstract": self.abstract,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatentMetadata":
        return cls(
            patent_number=str(data.get("patent_number", "")),
            application_number=str(data.get("application_number", "")),
            title=str(data.get("title", "")),
            country_code=str(data.get("country_code", "")),
            kind_code=str(data.get("kind_code", "")),
            inventors=list(data.get("inventors", [])),
            assignees=list(data.get("assignees", [])),
            application_date=str(data.get("application_date", "")),
            publication_date=str(data.get("publication_date", "")),
            status=str(data.get("status", "")),
            abstract=str(data.get("abstract", "")),
            url=str(data.get("url", "")),
        )


@dataclass(frozen=True)
class SoftwareCopyrightMetadata:
    """Software copyright-specific metadata for software copyright outputs."""

    registration_number: str = ""
    full_software_name: str = ""
    version_number: str = ""
    development_completion_date: str = ""
    first_publication_date: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "registration_number", _clean_text(self.registration_number))
        object.__setattr__(self, "full_software_name", _clean_text(self.full_software_name))
        object.__setattr__(self, "version_number", _clean_text(self.version_number))
        object.__setattr__(self, "development_completion_date", _clean_text(self.development_completion_date))
        object.__setattr__(self, "first_publication_date", _clean_text(self.first_publication_date))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registration_number": self.registration_number,
            "full_software_name": self.full_software_name,
            "version_number": self.version_number,
            "development_completion_date": self.development_completion_date,
            "first_publication_date": self.first_publication_date,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoftwareCopyrightMetadata":
        return cls(
            registration_number=str(data.get("registration_number", "")),
            full_software_name=str(data.get("full_software_name", "")),
            version_number=str(data.get("version_number", "")),
            development_completion_date=str(data.get("development_completion_date", "")),
            first_publication_date=str(data.get("first_publication_date", "")),
        )


@dataclass(frozen=True)
class Member:
    """Research group member."""

    member_id: str
    name: str
    role: Role = Role.MEMBER
    email: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not _clean_text(self.member_id):
            raise ValueError("Member id must not be empty.")
        if not _clean_text(self.name):
            raise ValueError("Member name must not be empty.")
        object.__setattr__(self, "member_id", _clean_text(self.member_id))
        object.__setattr__(self, "name", _clean_text(self.name))
        object.__setattr__(self, "email", _clean_text(self.email))
        object.__setattr__(self, "notes", _clean_text(self.notes))
        if not isinstance(self.role, Role):
            object.__setattr__(self, "role", Role(str(self.role)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "name": self.name,
            "role": self.role.value,
            "email": self.email,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Member":
        return cls(
            member_id=str(data.get("member_id", "")),
            name=str(data.get("name", "")),
            role=Role(str(data.get("role", Role.MEMBER.value))),
            email=str(data.get("email", "")),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class Project:
    """Research project or funding source."""

    project_id: str
    name: str
    project_type: str
    owner_member_ids: List[str] = field(default_factory=list)
    funding_source: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None

    def __post_init__(self) -> None:
        if not _clean_text(self.project_id):
            raise ValueError("Project id must not be empty.")
        if not _clean_text(self.name):
            raise ValueError("Project name must not be empty.")
        if not _clean_text(self.project_type):
            raise ValueError("Project type must not be empty.")
        if self.start_year is not None and (self.start_year < 0 or self.start_year > CURRENT_YEAR_UPPER_BOUND):
            raise ValueError(f"Project start year must be between 0 and {CURRENT_YEAR_UPPER_BOUND}.")
        if self.end_year is not None and (self.end_year < 0 or self.end_year > CURRENT_YEAR_UPPER_BOUND):
            raise ValueError(f"Project end year must be between 0 and {CURRENT_YEAR_UPPER_BOUND}.")
        object.__setattr__(self, "project_id", _clean_text(self.project_id))
        object.__setattr__(self, "name", _clean_text(self.name))
        object.__setattr__(self, "project_type", _clean_text(self.project_type))
        object.__setattr__(self, "owner_member_ids", _unique_cleaned(self.owner_member_ids))
        object.__setattr__(self, "funding_source", _clean_text(self.funding_source))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "project_type": self.project_type,
            "owner_member_ids": list(self.owner_member_ids),
            "funding_source": self.funding_source,
            "start_year": self.start_year,
            "end_year": self.end_year,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        return cls(
            project_id=str(data.get("project_id", "")),
            name=str(data.get("name", "")),
            project_type=str(data.get("project_type", "")),
            owner_member_ids=list(data.get("owner_member_ids", [])),
            funding_source=str(data.get("funding_source", "")),
            start_year=data.get("start_year"),
            end_year=data.get("end_year"),
        )


@dataclass(frozen=True)
class ResearchOutput:
    """Unified research output model."""

    output_id: str
    title: str
    output_type: OutputType
    owner_member_ids: List[str] = field(default_factory=list)
    participant_member_ids: List[str] = field(default_factory=list)
    project_ids: List[str] = field(default_factory=list)
    year: Optional[int] = None
    keywords: List[str] = field(default_factory=list)
    summary: str = ""
    notes: str = ""
    review_status: ReviewStatus = ReviewStatus.DRAFT
    article: Optional[ArticleMetadata] = None
    patent: Optional[PatentMetadata] = None
    software_copyright: Optional[SoftwareCopyrightMetadata] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not _clean_text(self.output_id):
            raise ValueError("Output id must not be empty.")
        if not _clean_text(self.title):
            raise ValueError("Output title must not be empty.")
        if self.year is not None and (self.year < 0 or self.year > CURRENT_YEAR_UPPER_BOUND):
            raise ValueError(f"Output year must be between 0 and {CURRENT_YEAR_UPPER_BOUND}.")
        object.__setattr__(self, "output_id", _clean_text(self.output_id))
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "owner_member_ids", _unique_cleaned(self.owner_member_ids))
        object.__setattr__(self, "participant_member_ids", _unique_cleaned(self.participant_member_ids))
        object.__setattr__(self, "project_ids", _unique_cleaned(self.project_ids))
        object.__setattr__(self, "keywords", _unique_cleaned(self.keywords, lower=True, sort_values=True))
        object.__setattr__(self, "summary", _clean_text(self.summary))
        object.__setattr__(self, "notes", _clean_text(self.notes))
        object.__setattr__(self, "created_at", _clean_text(self.created_at) or utc_now_iso())
        object.__setattr__(self, "updated_at", _clean_text(self.updated_at) or self.created_at)
        if not isinstance(self.output_type, OutputType):
            object.__setattr__(self, "output_type", OutputType(str(self.output_type)))
        if not isinstance(self.review_status, ReviewStatus):
            object.__setattr__(self, "review_status", ReviewStatus(str(self.review_status)))
        if not self.owner_member_ids:
            raise ValueError("At least one owner member id is required.")
        if self.output_type == OutputType.ARTICLE:
            if self.article is None:
                raise ValueError("Article outputs must include article metadata.")
        elif self.article is not None:
            raise ValueError("Only article outputs may include article metadata.")
        if self.output_type == OutputType.PATENT and self.patent is not None:
            object.__setattr__(self, "patent", self.patent)
        elif self.patent is not None and self.output_type != OutputType.PATENT:
            raise ValueError("Only patent outputs may include patent metadata.")
        if self.output_type == OutputType.SOFTWARE_COPYRIGHT and self.software_copyright is not None:
            object.__setattr__(self, "software_copyright", self.software_copyright)
        elif self.software_copyright is not None and self.output_type != OutputType.SOFTWARE_COPYRIGHT:
            raise ValueError("Only software copyright outputs may include software copyright metadata.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_id": self.output_id,
            "title": self.title,
            "output_type": self.output_type.value,
            "owner_member_ids": list(self.owner_member_ids),
            "participant_member_ids": list(self.participant_member_ids),
            "project_ids": list(self.project_ids),
            "year": self.year,
            "keywords": list(self.keywords),
            "summary": self.summary,
            "notes": self.notes,
            "review_status": self.review_status.value,
            "article": self.article.to_dict() if self.article else None,
            "patent": self.patent.to_dict() if self.patent else None,
            "software_copyright": self.software_copyright.to_dict() if self.software_copyright else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchOutput":
        article = data.get("article")
        return cls(
            output_id=str(data.get("output_id", "")),
            title=str(data.get("title", "")),
            output_type=OutputType(str(data.get("output_type", OutputType.ARTICLE.value))),
            owner_member_ids=list(data.get("owner_member_ids", [])),
            participant_member_ids=list(data.get("participant_member_ids", [])),
            project_ids=list(data.get("project_ids", [])),
            year=data.get("year"),
            keywords=list(data.get("keywords", [])),
            summary=str(data.get("summary", "")),
            notes=str(data.get("notes", "")),
            review_status=ReviewStatus(str(data.get("review_status", ReviewStatus.DRAFT.value))),
            article=ArticleMetadata.from_dict(article) if isinstance(article, dict) else None,
            patent=PatentMetadata.from_dict(data["patent"]) if isinstance(data.get("patent"), dict) else None,
            software_copyright=SoftwareCopyrightMetadata.from_dict(data["software_copyright"]) if isinstance(data.get("software_copyright"), dict) else None,
            created_at=str(data.get("created_at", utc_now_iso())),
            updated_at=str(data.get("updated_at", data.get("created_at", utc_now_iso()))),
        )

    def with_review_status(self, review_status: ReviewStatus) -> "ResearchOutput":
        return replace(self, review_status=review_status, updated_at=utc_now_iso())


@dataclass(frozen=True)
class ReviewRecord:
    """Track review-related status transitions."""

    review_id: str
    output_id: str
    actor_member_id: str
    actor_role: Role
    from_status: ReviewStatus
    to_status: ReviewStatus
    comment: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not _clean_text(self.review_id):
            raise ValueError("Review id must not be empty.")
        if not _clean_text(self.output_id):
            raise ValueError("Review output id must not be empty.")
        if not _clean_text(self.actor_member_id):
            raise ValueError("Review actor member id must not be empty.")
        object.__setattr__(self, "review_id", _clean_text(self.review_id))
        object.__setattr__(self, "output_id", _clean_text(self.output_id))
        object.__setattr__(self, "actor_member_id", _clean_text(self.actor_member_id))
        object.__setattr__(self, "comment", _clean_text(self.comment))
        object.__setattr__(self, "created_at", _clean_text(self.created_at) or utc_now_iso())
        if not isinstance(self.actor_role, Role):
            object.__setattr__(self, "actor_role", Role(str(self.actor_role)))
        if not isinstance(self.from_status, ReviewStatus):
            object.__setattr__(self, "from_status", ReviewStatus(str(self.from_status)))
        if not isinstance(self.to_status, ReviewStatus):
            object.__setattr__(self, "to_status", ReviewStatus(str(self.to_status)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "output_id": self.output_id,
            "actor_member_id": self.actor_member_id,
            "actor_role": self.actor_role.value,
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "comment": self.comment,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewRecord":
        return cls(
            review_id=str(data.get("review_id", "")),
            output_id=str(data.get("output_id", "")),
            actor_member_id=str(data.get("actor_member_id", "")),
            actor_role=Role(str(data.get("actor_role", Role.MEMBER.value))),
            from_status=ReviewStatus(str(data.get("from_status", ReviewStatus.DRAFT.value))),
            to_status=ReviewStatus(str(data.get("to_status", ReviewStatus.DRAFT.value))),
            comment=str(data.get("comment", "")),
            created_at=str(data.get("created_at", utc_now_iso())),
        )


@dataclass(frozen=True)
class AuditLog:
    """Lightweight audit trail entry."""

    log_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_member_id: str
    actor_role: Role
    summary: str
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        required_fields = {
            "log id": self.log_id,
            "entity type": self.entity_type,
            "entity id": self.entity_id,
            "action": self.action,
            "actor member id": self.actor_member_id,
            "summary": self.summary,
        }
        for label, value in required_fields.items():
            if not _clean_text(value):
                raise ValueError(f"Audit log {label} must not be empty.")
        object.__setattr__(self, "log_id", _clean_text(self.log_id))
        object.__setattr__(self, "entity_type", _clean_text(self.entity_type))
        object.__setattr__(self, "entity_id", _clean_text(self.entity_id))
        object.__setattr__(self, "action", _clean_text(self.action))
        object.__setattr__(self, "actor_member_id", _clean_text(self.actor_member_id))
        object.__setattr__(self, "summary", _clean_text(self.summary))
        object.__setattr__(self, "created_at", _clean_text(self.created_at) or utc_now_iso())
        if not isinstance(self.actor_role, Role):
            object.__setattr__(self, "actor_role", Role(str(self.actor_role)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "actor_member_id": self.actor_member_id,
            "actor_role": self.actor_role.value,
            "summary": self.summary,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLog":
        return cls(
            log_id=str(data.get("log_id", "")),
            entity_type=str(data.get("entity_type", "")),
            entity_id=str(data.get("entity_id", "")),
            action=str(data.get("action", "")),
            actor_member_id=str(data.get("actor_member_id", "")),
            actor_role=Role(str(data.get("actor_role", Role.MEMBER.value))),
            summary=str(data.get("summary", "")),
            created_at=str(data.get("created_at", utc_now_iso())),
        )
