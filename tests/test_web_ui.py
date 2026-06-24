"""Tests for the local web UI."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from lab_literature_manager.data_fetcher import ArticleData, DataFetcher
from lab_literature_manager.models import ArticleMetadata, Member, OutputType, Project, ResearchOutput, ReviewStatus, Role
from lab_literature_manager.repository import ResearchRepository
from lab_literature_manager.web import LocalAuthStore, LocalWebRequestHandler, WebApplication


class WebUiTests(TestCase):
    def _build_app(self, tmp_dir: str) -> WebApplication:
        data_dir = Path(tmp_dir) / "data"
        auth_path = Path(tmp_dir) / "auth" / "web_auth.json"
        app = WebApplication(data_dir=data_dir, auth_path=auth_path)
        app.auth_store.create_user("admin", "ChangeMe123", display_name="Administrator", role=Role.ADMIN)
        app.repository.add_member(Member(member_id="alice", name="Alice Zhang", role=Role.MEMBER))
        app.repository.add_member(Member(member_id="pi-1", name="Prof. Li", role=Role.PI))
        app.repository.add_project(
            Project(
                project_id="proj-1",
                name="Gut Cohort",
                project_type="funding",
                owner_member_ids=["pi-1"],
                funding_source="NSFC",
            )
        )
        app.repository.add_output(
            ResearchOutput(
                output_id="article-1",
                title="Gut Atlas",
                output_type=OutputType.ARTICLE,
                owner_member_ids=["alice"],
                project_ids=["proj-1"],
                year=2026,
                keywords=["microbiome", "atlas"],
                article=ArticleMetadata(article_type="review", journal="Journal A", submission_status="writing"),
            ),
            actor_role=Role.MEMBER,
            actor_member_id="alice",
        )
        return app

    def test_login_and_dashboard_pages_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            app.save_settings(app.load_settings().__class__(workspace_name="马老师课题组"))
            login_html = app.render_login_page()
            self.assertIn("马老师课题组", login_html)
            self.assertIn("姓名", login_html)
            self.assertIn("密码", login_html)
            self.assertIn("/register", login_html)
            self.assertNotIn("普通成员", login_html)
            self.assertNotIn("PI / 管理员", login_html)

            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            self.assertIsNotNone(admin)

            dashboard = app.render_dashboard(admin)  # type: ignore[arg-type]
            self.assertIn("成果指挥中心", dashboard)
            self.assertIn("总成果数", dashboard)
            self.assertIn("article-1", dashboard)
            self.assertIn("成员数", dashboard)
            self.assertIn("论文", dashboard)
            self.assertIn("导出Excel", dashboard)

    def test_output_detail_includes_actions_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            output = app.repository.get_output("article-1")

            detail = app.render_output_detail(admin, output)  # type: ignore[arg-type]
            self.assertIn("提交审核", detail)
            self.assertIn("article-1", detail)
            self.assertIn("草稿", detail)

            submit_user = Mock(role=Role.MEMBER, member_id="alice")
            class FakeHandler:
                def __init__(self, app):
                    self.app = app
                    self.send_response = Mock()
                    self.send_header = Mock()
                    self.end_headers = Mock()

            request = FakeHandler(app)
            LocalWebRequestHandler._handle_output_transition(request, submit_user, "article-1", "submit")

            updated = app.repository.get_output("article-1")
            self.assertEqual(updated.review_status.value, "submitted")

    def test_setup_page_is_shown_when_workspace_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = WebApplication(data_dir=Path(tmp_dir) / "data", auth_path=Path(tmp_dir) / "auth" / "web_auth.json")
            setup_html = app.render_setup_page()
            self.assertIn("工作区名称", setup_html)
            app.save_settings(app.load_settings().__class__(workspace_name="马老师课题组"))
            self.assertIn("马老师课题组", app.render_login_page())

    def test_member_pages_only_show_owned_outputs_and_form_supports_manual_people(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            app.repository.add_member(Member(member_id="bob", name="Bob Li", role=Role.MEMBER))
            app.repository.add_output(
                ResearchOutput(
                    output_id="ZL-2026-001",
                    title="Bob Patent",
                    output_type=OutputType.PATENT,
                    owner_member_ids=["bob"],
                    year=2026,
                ),
                actor_role=Role.MEMBER,
                actor_member_id="bob",
            )
            alice = app.auth_store.create_user("alice", "MemberPass123", display_name="Alice Zhang", role=Role.MEMBER)
            bob = app.auth_store.create_user("bob", "MemberPass123", display_name="Bob Li", role=Role.MEMBER)

            alice_outputs = app.render_outputs_page(alice)
            self.assertIn("Gut Atlas", alice_outputs)
            self.assertNotIn("Bob Patent", alice_outputs)
            self.assertNotIn("导出Excel", app.render_dashboard(alice))

            bob_outputs = app.render_outputs_page(bob)
            self.assertIn("Bob Patent", bob_outputs)
            self.assertNotIn("Gut Atlas", bob_outputs)

            output_form = app.render_output_form(alice)
            self.assertIn("论文", output_form)
            self.assertIn("专利", output_form)
            self.assertIn("owner_member_ids_manual", output_form)
            self.assertIn("participant_member_ids_manual", output_form)

    def test_dashboard_approved_metric_uses_chinese_status_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            output = app.repository.get_output("article-1")
            app.repository.update_output(
                ResearchOutput(
                    output_id=output.output_id,
                    title=output.title,
                    output_type=output.output_type,
                    owner_member_ids=output.owner_member_ids,
                    participant_member_ids=output.participant_member_ids,
                    project_ids=output.project_ids,
                    year=output.year,
                    keywords=output.keywords,
                    summary=output.summary,
                    notes=output.notes,
                    review_status=ReviewStatus.APPROVED,
                    article=output.article,
                    patent=output.patent,
                    created_at=output.created_at,
                ),
                actor_role=Role.ADMIN,
                actor_member_id="admin",
            )
            dashboard = app.render_dashboard(admin)  # type: ignore[arg-type]
            self.assertIn("已审核", dashboard)
            self.assertIn("已通过", dashboard)

    def test_import_page_renders_fetch_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            assert admin is not None
            import_html = app.render_import_page(admin)
            self.assertIn("外部数据抓取", import_html)
            self.assertIn("DOI / CrossRef", import_html)
            self.assertIn("10.3390/biom12060824", import_html)
            self.assertIn("PubMed / E-utilities", import_html)

    def test_import_fetch_builds_article_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            assert admin is not None
            with patch("lab_literature_manager.web.fetch_article_metadata") as mocked_fetch:
                mocked_fetch.return_value = ArticleData(
                    title="Mock Article",
                    authors=["Alice Zhang"],
                    journal="Nature",
                    year=2026,
                    doi="10.1038/nature12373",
                    pmid="12345678",
                    abstract="mock abstract",
                )
                original = app._build_output_from_fetch(
                    {"source_type": "doi", "query": "10.1038/nature12373", "owner_member_id": "alice"},
                    admin,
                )
            self.assertEqual(original.output_type, OutputType.ARTICLE)
            self.assertTrue(original.owner_member_ids)

    def test_registration_requires_admin_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            pending = app.auth_store.create_user(
                "Li Ming",
                "MemberPass123",
                display_name="Li Ming",
                role=Role.MEMBER,
                account_status="pending",
            )
            self.assertIsNone(app.auth_store.authenticate("Li Ming", "MemberPass123"))
            self.assertIn("Li Ming", app.render_pending_accounts_page(app.auth_store.get_user("admin")))  # type: ignore[arg-type]

            approved = app.auth_store.approve_user(pending.username, approved_by="admin")
            self.assertEqual(approved.account_status, "active")
            self.assertIsNotNone(app.auth_store.authenticate("Li Ming", "MemberPass123"))

    def test_auth_store_creates_and_persists_users(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_path = Path(tmp_dir) / "auth" / "web_auth.json"
            store = LocalAuthStore(auth_path)
            store.create_user("admin", "ChangeMe123", display_name="Administrator", role=Role.ADMIN)
            self.assertTrue(store.has_users())
            self.assertIsNotNone(store.authenticate("admin", "ChangeMe123"))
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)


class DataFetcherTests(TestCase):
    def test_crossref_doi_parsing_handles_example_payload(self) -> None:
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.session = Mock()
        fetcher.session.get.return_value = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "message": {
                        "DOI": "10.3390/biom12060824",
                        "title": ["Example Biomolecules Article"],
                        "author": [{"given": "Alice", "family": "Zhang"}],
                        "container-title": ["Biomolecules"],
                        "published": {"date-parts": [[2022, 6, 1]]},
                        "ISSN": ["2218-273X"],
                        "volume": "12",
                        "issue": "6",
                        "page": "824",
                        "abstract": "<jats:p>Example abstract.</jats:p>",
                    }
                }
            ),
        )

        article = fetcher.fetch_by_doi("https://doi.org/10.3390/biom12060824", rate_limit=0)

        self.assertIsNotNone(article)
        assert article is not None
        self.assertEqual(article.doi, "10.3390/biom12060824")
        self.assertEqual(article.title, "Example Biomolecules Article")
        self.assertEqual(article.journal, "Biomolecules")
        self.assertEqual(article.year, 2022)
        self.assertEqual(article.authors, ["Alice Zhang"])
        self.assertEqual(article.abstract, "Example abstract.")
