"""Regression tests for the research output management MVP."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from lab_literature_manager import (
    ArticleMetadata,
    Member,
    OutputType,
    Permission,
    Project,
    ResearchOutput,
    ResearchRepository,
    ReviewStatus,
    Role,
    SoftwareCopyrightMetadata,
    can_perform,
)
from lab_literature_manager.constants import DEFAULT_DATA_DIR
from lab_literature_manager.models import output_type_label, review_status_label


class ResearchOutputModelTests(unittest.TestCase):
    def test_article_output_normalization(self) -> None:
        output = ResearchOutput(
            output_id=" art-001 ",
            title="  Gut Microbiome Atlas  ",
            output_type=OutputType.ARTICLE,
            owner_member_ids=[" member-a ", "member-a"],
            participant_member_ids=[" member-b ", "", "member-b"],
            project_ids=[" project-1 ", "project-1"],
            keywords=[" Microbiome ", "microbiome", " Atlas "],
            article=ArticleMetadata(
                article_type="review",
                journal="  Nature Reviews Gastroenterology  ",
                doi=" 10.1000/example ",
                submission_status=" writing ",
            ),
        )
        self.assertEqual(output.output_id, "art-001")
        self.assertEqual(output.title, "Gut Microbiome Atlas")
        self.assertEqual(output.owner_member_ids, ["member-a"])
        self.assertEqual(output.participant_member_ids, ["member-b"])
        self.assertEqual(output.project_ids, ["project-1"])
        self.assertEqual(output.keywords, ["atlas", "microbiome"])
        self.assertEqual(output.review_status, ReviewStatus.DRAFT)
        self.assertEqual(output.article.journal, "Nature Reviews Gastroenterology")
        self.assertEqual(output.article.doi, "10.1000/example")
        self.assertEqual(output.article.submission_status, "writing")

    def test_default_data_dir_constant(self) -> None:
        self.assertEqual(DEFAULT_DATA_DIR, "data/local")


class PermissionAndWorkflowTests(unittest.TestCase):
    def test_permission_matrix_and_review_flow(self) -> None:
        output = ResearchOutput(
            output_id="article-1",
            title="Lab Workflow Paper",
            output_type=OutputType.ARTICLE,
            owner_member_ids=["alice"],
            article=ArticleMetadata(article_type="research_article", journal="Journal A"),
        )

        self.assertTrue(can_perform(Role.MEMBER, Permission.CREATE, output=output, actor_member_id="alice"))
        self.assertTrue(can_perform(Role.MEMBER, Permission.EDIT, output=output, actor_member_id="alice"))
        self.assertFalse(can_perform(Role.MEMBER, Permission.REVIEW, output=output, actor_member_id="alice"))
        self.assertTrue(can_perform(Role.PI, Permission.REVIEW, output=output, actor_member_id="pi-1"))
        self.assertTrue(can_perform(Role.ADMIN, Permission.MANAGE_PERMISSIONS))
        self.assertTrue(can_perform(Role.ADMIN, Permission.DELETE, output=output, actor_member_id="admin"))
        self.assertTrue(can_perform(Role.MEMBER, Permission.VIEW, output=output, actor_member_id="alice"))
        self.assertFalse(can_perform(Role.MEMBER, Permission.VIEW, output=output, actor_member_id="bob"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = ResearchRepository(tmp_dir)
            repository.add_member(Member(member_id="alice", name="Alice", role=Role.MEMBER))
            repository.add_member(Member(member_id="pi-1", name="PI", role=Role.PI))
            repository.add_output(output, actor_role=Role.MEMBER, actor_member_id="alice")

            submitted = repository.submit_output("article-1", actor_role=Role.MEMBER, actor_member_id="alice")
            self.assertEqual(submitted.review_status, ReviewStatus.SUBMITTED)

            with self.assertRaises(PermissionError):
                repository.approve_output("article-1", actor_role=Role.MEMBER, actor_member_id="alice")

            approved = repository.approve_output("article-1", actor_role=Role.PI, actor_member_id="pi-1")
            self.assertEqual(approved.review_status, ReviewStatus.APPROVED)
            self.assertEqual(len(repository.list_review_records("article-1")), 2)
            self.assertGreaterEqual(len(repository.list_audit_logs("article-1")), 3)


class RepositoryTests(unittest.TestCase):
    def test_category_labels_and_generated_output_ids_are_chinese_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = ResearchRepository(tmp_dir)
            repository.add_member(Member(member_id="alice", name="Alice", role=Role.MEMBER))
            first_id = repository.generate_output_id(OutputType.ARTICLE, year=2026)
            self.assertEqual(first_id, "LW-2026-001")
            self.assertEqual(output_type_label(OutputType.ARTICLE), "论文")
            self.assertEqual(output_type_label(OutputType.SOFTWARE_COPYRIGHT), "软件著作权")
            self.assertEqual(review_status_label(ReviewStatus.DRAFT), "草稿")

            repository.add_output(
                ResearchOutput(
                    output_id=first_id,
                    title="Cancer Atlas",
                    output_type=OutputType.ARTICLE,
                    owner_member_ids=["alice", "外部合作者"],
                    participant_member_ids=["未建档成员"],
                    year=2026,
                    article=ArticleMetadata(article_type="review"),
                ),
                actor_role=Role.MEMBER,
                actor_member_id="alice",
            )

            self.assertEqual(repository.generate_output_id(OutputType.ARTICLE, year=2026), "LW-2026-002")
            self.assertEqual(repository.generate_output_id(OutputType.PATENT, year=2026), "ZL-2026-001")

    def test_member_output_scope_only_lists_owned_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = ResearchRepository(tmp_dir)
            repository.add_member(Member(member_id="alice", name="Alice", role=Role.MEMBER))
            repository.add_member(Member(member_id="bob", name="Bob", role=Role.MEMBER))
            repository.add_output(
                ResearchOutput(
                    output_id="LW-2026-001",
                    title="Alice Output",
                    output_type=OutputType.ARTICLE,
                    owner_member_ids=["alice"],
                    article=ArticleMetadata(article_type="review"),
                ),
                actor_role=Role.MEMBER,
                actor_member_id="alice",
            )
            repository.add_output(
                ResearchOutput(
                    output_id="ZL-2026-001",
                    title="Bob Output",
                    output_type=OutputType.PATENT,
                    owner_member_ids=["bob"],
                ),
                actor_role=Role.MEMBER,
                actor_member_id="bob",
            )

            alice_outputs = repository.list_outputs_for_actor(Role.MEMBER, "alice")
            admin_outputs = repository.list_outputs_for_actor(Role.ADMIN, "admin")
            self.assertEqual([output.output_id for output in alice_outputs], ["LW-2026-001"])
            self.assertEqual({output.output_id for output in admin_outputs}, {"LW-2026-001", "ZL-2026-001"})

    def test_repository_round_trip_summary_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = ResearchRepository(tmp_dir)
            repository.add_member(Member(member_id="alice", name="Alice", role=Role.MEMBER))
            repository.add_project(
                Project(
                    project_id="proj-1",
                    name="National Key Project",
                    project_type="funding",
                    owner_member_ids=["alice"],
                    funding_source="NSFC",
                )
            )
            repository.add_output(
                ResearchOutput(
                    output_id="article-1",
                    title="Cancer Atlas",
                    output_type=OutputType.ARTICLE,
                    owner_member_ids=["alice"],
                    project_ids=["proj-1"],
                    year=2026,
                    keywords=["oncology"],
                    article=ArticleMetadata(
                        article_type="review",
                        journal="Journal A",
                        submission_status="accepted",
                    ),
                ),
                actor_role=Role.MEMBER,
                actor_member_id="alice",
            )
            repository.add_output(
                ResearchOutput(
                    output_id="patent-1",
                    title="Sample Patent",
                    output_type=OutputType.PATENT,
                    owner_member_ids=["alice"],
                    year=2025,
                ),
                actor_role=Role.MEMBER,
                actor_member_id="alice",
            )

            payload = json.loads((Path(tmp_dir) / "outputs.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual([item["output_id"] for item in payload["items"]], ["article-1", "patent-1"])

            summary = repository.build_summary()
            self.assertEqual(summary["total_outputs"], 2)
            self.assertEqual(summary["by_type"]["article"], 1)
            self.assertEqual(summary["by_type"]["patent"], 1)
            self.assertEqual(summary["by_review_status"]["draft"], 2)
            self.assertEqual(summary["by_year"]["2026"], 1)

            export_path = Path(tmp_dir) / "outputs.csv"
            repository.export_outputs_csv(export_path)
            with export_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["output_id"], "article-1")
            self.assertEqual(rows[0]["article_journal"], "Journal A")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "lab_literature_manager.cli", *args],
            cwd=cwd,
            env={"PYTHONPATH": str(SRC)},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "workspace"

            member_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "members",
                "add",
                "--id",
                "alice",
                "--name",
                "Alice",
                "--role",
                "member",
            )
            self.assertEqual(member_result.returncode, 0, member_result.stderr)
            self.assertIn("Added member: alice", member_result.stdout)

            project_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "projects",
                "add",
                "--id",
                "proj-1",
                "--name",
                "Gut Project",
                "--type",
                "funding",
                "--owner",
                "alice",
            )
            self.assertEqual(project_result.returncode, 0, project_result.stderr)

            add_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "outputs",
                "add",
                "--id",
                "article-1",
                "--title",
                "Gut Project Output",
                "--type",
                "article",
                "--owner",
                "alice",
                "--project",
                "proj-1",
                "--year",
                "2026",
                "--article-type",
                "review",
                "--journal",
                "Gut Journal",
                "--submission-status",
                "writing",
            )
            self.assertEqual(add_result.returncode, 0, add_result.stderr)
            self.assertIn("Added research output: article-1", add_result.stdout)

            submit_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "outputs",
                "submit",
                "article-1",
                "--actor-id",
                "alice",
                "--actor-role",
                "member",
            )
            self.assertEqual(submit_result.returncode, 0, submit_result.stderr)
            self.assertIn("submitted", submit_result.stdout.lower())

            pi_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "members",
                "add",
                "--id",
                "pi-1",
                "--name",
                "Principal Investigator",
                "--role",
                "pi",
            )
            self.assertEqual(pi_result.returncode, 0, pi_result.stderr)

            approve_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "outputs",
                "approve",
                "article-1",
                "--actor-id",
                "pi-1",
                "--actor-role",
                "pi",
            )
            self.assertEqual(approve_result.returncode, 0, approve_result.stderr)
            self.assertIn("approved", approve_result.stdout.lower())

            list_result = self.run_cli("--data-dir", str(data_dir), "outputs", "list", "--status", "approved")
            self.assertEqual(list_result.returncode, 0, list_result.stderr)
            self.assertIn("article-1", list_result.stdout)

            summary_result = self.run_cli("--data-dir", str(data_dir), "stats", "summary")
            self.assertEqual(summary_result.returncode, 0, summary_result.stderr)
            self.assertIn("Total outputs: 1", summary_result.stdout)
            self.assertIn("approved: 1", summary_result.stdout)

            export_path = Path(tmp_dir) / "cli-export.csv"
            export_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "export",
                "csv",
                "--output",
                str(export_path),
            )
            self.assertEqual(export_result.returncode, 0, export_result.stderr)
            self.assertTrue(export_path.exists())

    def test_cli_requires_actor_id_for_admin_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "workspace"
            self.run_cli(
                "--data-dir",
                str(data_dir),
                "members",
                "add",
                "--id",
                "alice",
                "--name",
                "Alice",
                "--role",
                "member",
            )

            add_result = self.run_cli(
                "--data-dir",
                str(data_dir),
                "outputs",
                "add",
                "--id",
                "article-1",
                "--title",
                "Admin Imported Output",
                "--type",
                "article",
                "--owner",
                "alice",
                "--actor-role",
                "admin",
                "--article-type",
                "review",
            )
            self.assertNotEqual(add_result.returncode, 0)
            self.assertIn("actor-id is required", add_result.stderr)

    def test_software_copyright_output_with_metadata(self) -> None:
        """Test software copyright output creation and serialization."""
        output = ResearchOutput(
            output_id="RZ-2026-001",
            title="科研成果管理软件V1.0",
            output_type=OutputType.SOFTWARE_COPYRIGHT,
            owner_member_ids=["dev-001"],
            year=2026,
            software_copyright=SoftwareCopyrightMetadata(
                registration_number="软著登字第1234567号",
                full_software_name="科研成果管理软件V1.0",
                version_number="V1.0",
                development_completion_date="2026-06-01",
                first_publication_date="2026-07-01",
            ),
        )
        self.assertEqual(output.output_id, "RZ-2026-001")
        self.assertEqual(output.output_type, OutputType.SOFTWARE_COPYRIGHT)
        self.assertIsNotNone(output.software_copyright)
        self.assertEqual(output.software_copyright.registration_number, "软著登字第1234567号")
        self.assertEqual(output.software_copyright.version_number, "V1.0")

        # Test serialization
        output_dict = output.to_dict()
        self.assertIn("software_copyright", output_dict)
        self.assertEqual(output_dict["software_copyright"]["registration_number"], "软著登字第1234567号")

        # Test deserialization
        restored = ResearchOutput.from_dict(output_dict)
        self.assertEqual(restored.output_id, "RZ-2026-001")
        self.assertIsNotNone(restored.software_copyright)
        self.assertEqual(restored.software_copyright.registration_number, "软著登字第1234567号")


if __name__ == "__main__":
    unittest.main()
