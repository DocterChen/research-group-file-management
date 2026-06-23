"""Tests for the local web UI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

from lab_literature_manager.models import ArticleMetadata, Member, OutputType, Project, ResearchOutput, Role
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
            login_html = app.render_login_page()
            self.assertIn("Local Research Manager", login_html)
            self.assertIn("Sign in", login_html)

            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            self.assertIsNotNone(admin)

            dashboard = app.render_dashboard(admin)  # type: ignore[arg-type]
            self.assertIn("Research Command Center", dashboard)
            self.assertIn("Total outputs", dashboard)
            self.assertIn("article-1", dashboard)
            self.assertIn("Members", dashboard)

    def test_output_detail_includes_actions_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            app = self._build_app(tmp_dir)
            admin = app.auth_store.authenticate("admin", "ChangeMe123")
            output = app.repository.get_output("article-1")

            detail = app.render_output_detail(admin, output)  # type: ignore[arg-type]
            self.assertIn("Submit for review", detail)
            self.assertIn("article-1", detail)
            self.assertIn("Draft", detail)

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
            self.assertIn("Create workspace access", setup_html)

    def test_auth_store_creates_and_persists_users(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_path = Path(tmp_dir) / "auth" / "web_auth.json"
            store = LocalAuthStore(auth_path)
            store.create_user("admin", "ChangeMe123", display_name="Administrator", role=Role.ADMIN)
            self.assertTrue(store.has_users())
            self.assertIsNotNone(store.authenticate("admin", "ChangeMe123"))
            payload = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
