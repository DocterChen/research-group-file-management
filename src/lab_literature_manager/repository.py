"""JSON-backed repository for research outputs and related entities."""

from __future__ import annotations

import csv
import json
from collections import Counter
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, TypeVar, Union

from .constants import DATA_FILE_NAMES, SCHEMA_VERSION
from .models import (
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
from .permissions import ensure_permission

T = TypeVar("T")

ALLOWED_REVIEW_TRANSITIONS = {
    ReviewStatus.DRAFT: {ReviewStatus.SUBMITTED},
    ReviewStatus.RETURNED: {ReviewStatus.SUBMITTED},
    ReviewStatus.SUBMITTED: {ReviewStatus.APPROVED, ReviewStatus.RETURNED},
    ReviewStatus.APPROVED: {ReviewStatus.ARCHIVED},
    ReviewStatus.ARCHIVED: set(),
}


class ResearchRepository:
    """Store research outputs, members and projects in JSON files."""

    def __init__(self, data_dir: Union[Path, str]) -> None:
        self.data_dir = Path(data_dir)

    def list_members(self) -> List[Member]:
        return self._load_entities("members", Member.from_dict, sort_key=lambda item: item.member_id.lower())

    def get_member(self, member_id: str) -> Member:
        normalized_id = member_id.strip()
        for member in self.list_members():
            if member.member_id == normalized_id:
                return member
        raise KeyError(f"Member not found: {member_id}")

    def add_member(self, member: Member) -> None:
        members = self.list_members()
        if any(existing.member_id == member.member_id for existing in members):
            raise ValueError(f"Member already exists: {member.member_id}")
        members.append(member)
        self._save_entities("members", members, sort_key=lambda item: item.member_id.lower())

    def update_member(self, member: Member) -> None:
        members = self.list_members()
        if not any(existing.member_id == member.member_id for existing in members):
            raise KeyError(f"Member not found: {member.member_id}")
        updated_members = [member if existing.member_id == member.member_id else existing for existing in members]
        self._save_entities("members", updated_members, sort_key=lambda item: item.member_id.lower())

    def delete_member(self, member_id: str) -> None:
        normalized_id = member_id.strip()
        members = self.list_members()
        if not any(existing.member_id == normalized_id for existing in members):
            raise KeyError(f"Member not found: {member_id}")
        # Check if member is referenced in outputs
        outputs = self.list_outputs()
        referenced_in = [
            output.output_id
            for output in outputs
            if normalized_id in output.owner_member_ids or normalized_id in output.participant_member_ids
        ]
        if referenced_in:
            raise ValueError(
                f"Cannot delete member {member_id}: referenced in outputs {', '.join(referenced_in[:5])}"
                + (f" and {len(referenced_in) - 5} more" if len(referenced_in) > 5 else "")
            )
        # Check if member is referenced in projects
        projects = self.list_projects()
        referenced_projects = [
            project.project_id for project in projects if normalized_id in project.owner_member_ids
        ]
        if referenced_projects:
            raise ValueError(
                f"Cannot delete member {member_id}: referenced in projects {', '.join(referenced_projects[:5])}"
                + (f" and {len(referenced_projects) - 5} more" if len(referenced_projects) > 5 else "")
            )
        updated_members = [existing for existing in members if existing.member_id != normalized_id]
        self._save_entities("members", updated_members, sort_key=lambda item: item.member_id.lower())

    def list_projects(self) -> List[Project]:
        return self._load_entities("projects", Project.from_dict, sort_key=lambda item: item.project_id.lower())

    def get_project(self, project_id: str) -> Project:
        normalized_id = project_id.strip()
        for project in self.list_projects():
            if project.project_id == normalized_id:
                return project
        raise KeyError(f"Project not found: {project_id}")

    def add_project(self, project: Project) -> None:
        projects = self.list_projects()
        if any(existing.project_id == project.project_id for existing in projects):
            raise ValueError(f"Project already exists: {project.project_id}")
        self._validate_member_ids(project.owner_member_ids, label="project owners")
        projects.append(project)
        self._save_entities("projects", projects, sort_key=lambda item: item.project_id.lower())

    def update_project(self, project: Project) -> None:
        projects = self.list_projects()
        if not any(existing.project_id == project.project_id for existing in projects):
            raise KeyError(f"Project not found: {project.project_id}")
        self._validate_member_ids(project.owner_member_ids, label="project owners")
        updated_projects = [project if existing.project_id == project.project_id else existing for existing in projects]
        self._save_entities("projects", updated_projects, sort_key=lambda item: item.project_id.lower())

    def delete_project(self, project_id: str) -> None:
        normalized_id = project_id.strip()
        projects = self.list_projects()
        if not any(existing.project_id == normalized_id for existing in projects):
            raise KeyError(f"Project not found: {project_id}")
        # Check if project is referenced in outputs
        outputs = self.list_outputs()
        referenced_in = [output.output_id for output in outputs if normalized_id in output.project_ids]
        if referenced_in:
            raise ValueError(
                f"Cannot delete project {project_id}: referenced in outputs {', '.join(referenced_in[:5])}"
                + (f" and {len(referenced_in) - 5} more" if len(referenced_in) > 5 else "")
            )
        updated_projects = [existing for existing in projects if existing.project_id != normalized_id]
        self._save_entities("projects", updated_projects, sort_key=lambda item: item.project_id.lower())

    def list_outputs(
        self,
        *,
        status: Optional[Union[ReviewStatus, str]] = None,
        output_type: Optional[Union[OutputType, str]] = None,
        owner_member_id: Optional[str] = None,
    ) -> List[ResearchOutput]:
        outputs = self._load_entities("outputs", ResearchOutput.from_dict, sort_key=lambda item: item.output_id.lower())
        if status:
            expected_status = status if isinstance(status, ReviewStatus) else ReviewStatus(str(status))
            outputs = [item for item in outputs if item.review_status == expected_status]
        if output_type:
            expected_type = output_type if isinstance(output_type, OutputType) else OutputType(str(output_type))
            outputs = [item for item in outputs if item.output_type == expected_type]
        if owner_member_id:
            normalized_owner = owner_member_id.strip()
            outputs = [item for item in outputs if normalized_owner in item.owner_member_ids]
        return outputs

    def get_output(self, output_id: str) -> ResearchOutput:
        normalized_id = output_id.strip()
        for output in self.list_outputs():
            if output.output_id == normalized_id:
                return output
        raise KeyError(f"Research output not found: {output_id}")

    def add_output(self, output: ResearchOutput, *, actor_role: Role, actor_member_id: str) -> None:
        ensure_permission(
            actor_role,
            Permission.CREATE,
            output=output,
            actor_member_id=actor_member_id,
            action_label="create output",
        )
        outputs = self.list_outputs()
        if any(existing.output_id == output.output_id for existing in outputs):
            raise ValueError(f"Research output already exists: {output.output_id}")
        self._validate_member_ids(output.owner_member_ids, label="output owners")
        self._validate_member_ids(output.participant_member_ids, label="output participants")
        self._validate_project_ids(output.project_ids)
        outputs.append(output)
        self._save_entities("outputs", outputs, sort_key=lambda item: item.output_id.lower())
        self._append_audit_log(
            entity_type="output",
            entity_id=output.output_id,
            action="create",
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            summary=f"Created research output '{output.title}'.",
        )

    def update_output(self, output: ResearchOutput, *, actor_role: Role, actor_member_id: str) -> None:
        ensure_permission(
            actor_role,
            Permission.EDIT,
            output=output,
            actor_member_id=actor_member_id,
            action_label="update output",
        )
        outputs = self.list_outputs()
        if not any(existing.output_id == output.output_id for existing in outputs):
            raise KeyError(f"Research output not found: {output.output_id}")
        self._validate_member_ids(output.owner_member_ids, label="output owners")
        self._validate_member_ids(output.participant_member_ids, label="output participants")
        self._validate_project_ids(output.project_ids)
        updated_outputs = [output if existing.output_id == output.output_id else existing for existing in outputs]
        self._save_entities("outputs", updated_outputs, sort_key=lambda item: item.output_id.lower())
        self._append_audit_log(
            entity_type="output",
            entity_id=output.output_id,
            action="update",
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            summary=f"Updated research output '{output.title}'.",
        )

    def delete_output(self, output_id: str, *, actor_role: Role, actor_member_id: str) -> None:
        normalized_id = output_id.strip()
        output = self.get_output(normalized_id)
        ensure_permission(
            actor_role,
            Permission.DELETE,
            output=output,
            actor_member_id=actor_member_id,
            action_label="delete output",
        )
        outputs = self.list_outputs()
        updated_outputs = [existing for existing in outputs if existing.output_id != normalized_id]
        self._save_entities("outputs", updated_outputs, sort_key=lambda item: item.output_id.lower())
        self._append_audit_log(
            entity_type="output",
            entity_id=output_id,
            action="delete",
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            summary=f"Deleted research output '{output.title}'.",
        )

    def submit_output(self, output_id: str, *, actor_role: Role, actor_member_id: str) -> ResearchOutput:
        output = self.get_output(output_id)
        ensure_permission(
            actor_role,
            Permission.EDIT,
            output=output,
            actor_member_id=actor_member_id,
            action_label="submit output",
        )
        updated = self._transition_output(
            output,
            ReviewStatus.SUBMITTED,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            comment="Submitted for review.",
        )
        return updated

    def approve_output(
        self,
        output_id: str,
        *,
        actor_role: Role,
        actor_member_id: str,
        comment: str = "",
    ) -> ResearchOutput:
        output = self.get_output(output_id)
        ensure_permission(
            actor_role,
            Permission.REVIEW,
            output=output,
            actor_member_id=actor_member_id,
            action_label="approve output",
        )
        updated = self._transition_output(
            output,
            ReviewStatus.APPROVED,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            comment=comment or "Approved.",
        )
        return updated

    def list_review_records(self, output_id: Optional[str] = None) -> List[ReviewRecord]:
        records = self._load_entities("reviews", ReviewRecord.from_dict, sort_key=lambda item: item.created_at)
        if output_id:
            normalized_id = output_id.strip()
            records = [item for item in records if item.output_id == normalized_id]
        return records

    def list_audit_logs(self, entity_id: Optional[str] = None) -> List[AuditLog]:
        records = self._load_entities("audit_logs", AuditLog.from_dict, sort_key=lambda item: item.created_at)
        if entity_id:
            normalized_id = entity_id.strip()
            records = [item for item in records if item.entity_id == normalized_id]
        return records

    def build_summary(self) -> Dict[str, Dict[str, int]]:
        outputs = self.list_outputs()
        by_type = Counter(item.output_type.value for item in outputs)
        by_status = Counter(item.review_status.value for item in outputs)
        by_year = Counter(str(item.year) for item in outputs if item.year is not None)
        return {
            "total_outputs": len(outputs),
            "by_type": dict(sorted(by_type.items())),
            "by_review_status": dict(sorted(by_status.items())),
            "by_year": dict(sorted(by_year.items())),
        }

    def export_outputs_csv(self, output_path: Union[Path, str]) -> Path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "output_id",
            "title",
            "output_type",
            "review_status",
            "year",
            "owner_member_ids",
            "participant_member_ids",
            "project_ids",
            "keywords",
            "article_type",
            "article_journal",
            "article_doi",
            "article_submission_status",
            "created_at",
            "updated_at",
        ]
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for output in self.list_outputs():
                writer.writerow(
                    {
                        "output_id": output.output_id,
                        "title": output.title,
                        "output_type": output.output_type.value,
                        "review_status": output.review_status.value,
                        "year": output.year if output.year is not None else "",
                        "owner_member_ids": ";".join(output.owner_member_ids),
                        "participant_member_ids": ";".join(output.participant_member_ids),
                        "project_ids": ";".join(output.project_ids),
                        "keywords": ";".join(output.keywords),
                        "article_type": output.article.article_type if output.article else "",
                        "article_journal": output.article.journal if output.article else "",
                        "article_doi": output.article.doi if output.article else "",
                        "article_submission_status": output.article.submission_status if output.article else "",
                        "created_at": output.created_at,
                        "updated_at": output.updated_at,
                    }
                )
        return target

    def _transition_output(
        self,
        output: ResearchOutput,
        next_status: ReviewStatus,
        *,
        actor_member_id: str,
        actor_role: Role,
        comment: str,
    ) -> ResearchOutput:
        if next_status not in ALLOWED_REVIEW_TRANSITIONS[output.review_status]:
            raise ValueError(f"Cannot change output from {output.review_status.value} to {next_status.value}.")
        updated = output.with_review_status(next_status)
        outputs = [updated if item.output_id == output.output_id else item for item in self.list_outputs()]
        self._save_entities("outputs", outputs, sort_key=lambda item: item.output_id.lower())
        review_records = self.list_review_records()
        review_records.append(
            ReviewRecord(
                review_id=f"{output.output_id}-{len(review_records) + 1}",
                output_id=output.output_id,
                actor_member_id=actor_member_id,
                actor_role=actor_role,
                from_status=output.review_status,
                to_status=next_status,
                comment=comment,
            )
        )
        self._save_entities("reviews", review_records, sort_key=lambda item: item.created_at)
        self._append_audit_log(
            entity_type="output",
            entity_id=output.output_id,
            action=f"status:{next_status.value}",
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            summary=f"Changed review status from {output.review_status.value} to {next_status.value}.",
        )
        return updated

    def _append_audit_log(
        self,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_member_id: str,
        actor_role: Role,
        summary: str,
    ) -> None:
        logs = self.list_audit_logs()
        logs.append(
            AuditLog(
                log_id=f"{entity_type}-{entity_id}-{len(logs) + 1}",
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_member_id=actor_member_id.strip(),
                actor_role=actor_role,
                summary=summary,
            )
        )
        self._save_entities("audit_logs", logs, sort_key=lambda item: item.created_at)

    def _validate_member_ids(self, member_ids: Sequence[str], *, label: str) -> None:
        known_member_ids = {member.member_id for member in self.list_members()}
        missing = sorted(member_id for member_id in member_ids if member_id not in known_member_ids)
        if missing:
            raise ValueError(f"Unknown {label}: {', '.join(missing)}")

    def _validate_project_ids(self, project_ids: Sequence[str]) -> None:
        known_project_ids = {project.project_id for project in self.list_projects()}
        missing = sorted(project_id for project_id in project_ids if project_id not in known_project_ids)
        if missing:
            raise ValueError(f"Unknown projects: {', '.join(missing)}")

    def _collection_path(self, collection_name: str) -> Path:
        try:
            filename = DATA_FILE_NAMES[collection_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported collection: {collection_name}") from exc
        return self.data_dir / filename

    def _load_entities(
        self,
        collection_name: str,
        factory: Callable[[Dict[str, object]], T],
        *,
        sort_key: Callable[[T], object],
    ) -> List[T]:
        path = self._collection_path(collection_name)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except JSONDecodeError as exc:
            raise ValueError(f"Data file is not valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Data file must contain a JSON object: {path}")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version in {path}: {payload.get('schema_version')}")
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError(f"Data file items must be a JSON list: {path}")
        return sorted([factory(item) for item in items], key=sort_key)

    def _save_entities(
        self,
        collection_name: str,
        items: Iterable[T],
        *,
        sort_key: Callable[[T], object],
    ) -> None:
        path = self._collection_path(collection_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        materialized = sorted(list(items), key=sort_key)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "items": [item.to_dict() for item in materialized],
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
