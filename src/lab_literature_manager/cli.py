"""Command line interface for the research output management MVP."""

from __future__ import annotations

import argparse
from typing import List, Optional

from .constants import DEFAULT_DATA_DIR
from .models import ArticleMetadata, Member, OutputType, Project, ResearchOutput, ReviewStatus, Role
from .repository import ResearchRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litman",
        description="Manage research outputs, members, projects and review workflows for a research group.",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="Path to the local JSON workspace directory. Defaults to data/local.",
    )
    subparsers = parser.add_subparsers(dest="command")

    _build_member_parser(subparsers)
    _build_project_parser(subparsers)
    _build_output_parser(subparsers)

    stats_parser = subparsers.add_parser("stats", help="View aggregate statistics.")
    stats_subparsers = stats_parser.add_subparsers(dest="stats_command")
    stats_subparsers.add_parser("summary", help="Show summary counts for outputs.")

    export_parser = subparsers.add_parser("export", help="Export output data.")
    export_subparsers = export_parser.add_subparsers(dest="export_command")
    export_csv = export_subparsers.add_parser("csv", help="Export outputs to CSV.")
    export_csv.add_argument("--output", required=True, help="Destination CSV path.")
    return parser


def _build_member_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    members_parser = subparsers.add_parser("members", help="Manage member records.")
    members_subparsers = members_parser.add_subparsers(dest="members_command")

    add_parser = members_subparsers.add_parser("add", help="Add a member.")
    add_parser.add_argument("--id", required=True, help="Stable member id.")
    add_parser.add_argument("--name", required=True, help="Member name.")
    add_parser.add_argument(
        "--role",
        choices=[role.value for role in Role],
        default=Role.MEMBER.value,
        help="Member role.",
    )
    add_parser.add_argument("--email", default="", help="Optional email.")
    add_parser.add_argument("--notes", default="", help="Optional note.")

    members_subparsers.add_parser("list", help="List members.")
    show_parser = members_subparsers.add_parser("show", help="Show one member.")
    show_parser.add_argument("member_id", help="Member id to show.")


def _build_project_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    projects_parser = subparsers.add_parser("projects", help="Manage project records.")
    projects_subparsers = projects_parser.add_subparsers(dest="projects_command")

    add_parser = projects_subparsers.add_parser("add", help="Add a project.")
    add_parser.add_argument("--id", required=True, help="Stable project id.")
    add_parser.add_argument("--name", required=True, help="Project name.")
    add_parser.add_argument("--type", required=True, help="Project type, such as funding or collaboration.")
    add_parser.add_argument("--owner", action="append", default=[], help="Owner member id; repeat for multiple owners.")
    add_parser.add_argument("--funding-source", default="", help="Funding source.")
    add_parser.add_argument("--start-year", type=int, help="Project start year.")
    add_parser.add_argument("--end-year", type=int, help="Project end year.")

    projects_subparsers.add_parser("list", help="List projects.")
    show_parser = projects_subparsers.add_parser("show", help="Show one project.")
    show_parser.add_argument("project_id", help="Project id to show.")


def _build_output_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    outputs_parser = subparsers.add_parser("outputs", help="Manage research outputs.")
    outputs_subparsers = outputs_parser.add_subparsers(dest="outputs_command")

    add_parser = outputs_subparsers.add_parser("add", help="Add a research output.")
    add_parser.add_argument("--id", required=True, help="Stable output id.")
    add_parser.add_argument("--title", required=True, help="Output title.")
    add_parser.add_argument(
        "--type",
        choices=[item.value for item in OutputType],
        default=OutputType.ARTICLE.value,
        help="Output type.",
    )
    add_parser.add_argument("--owner", action="append", default=[], help="Owner member id; repeat for multiple owners.")
    add_parser.add_argument(
        "--participant",
        action="append",
        default=[],
        help="Participant member id; repeat for multiple members.",
    )
    add_parser.add_argument("--project", action="append", default=[], help="Related project id; repeat if needed.")
    add_parser.add_argument("--year", type=int, help="Output year.")
    add_parser.add_argument("--keyword", action="append", default=[], help="Keyword; repeat for multiple values.")
    add_parser.add_argument("--summary", default="", help="Short summary.")
    add_parser.add_argument("--notes", default="", help="Additional note.")
    add_parser.add_argument("--actor-id", default="", help="Actor member id for create permission checks.")
    add_parser.add_argument(
        "--actor-role",
        choices=[role.value for role in Role],
        default=Role.MEMBER.value,
        help="Actor role for create permission checks.",
    )
    add_parser.add_argument("--article-type", default="", help="Article subtype when --type article.")
    add_parser.add_argument("--journal", default="", help="Journal name for article outputs.")
    add_parser.add_argument("--doi", default="", help="DOI for article outputs.")
    add_parser.add_argument("--issn", default="", help="ISSN for article outputs.")
    add_parser.add_argument("--pmid", default="", help="PMID for article outputs.")
    add_parser.add_argument("--publication-year", type=int, help="Formal publication year for article outputs.")
    add_parser.add_argument("--volume", default="", help="Volume for article outputs.")
    add_parser.add_argument("--issue", default="", help="Issue for article outputs.")
    add_parser.add_argument("--pages", default="", help="Page range for article outputs.")
    add_parser.add_argument("--impact-factor", default="", help="Impact factor snapshot.")
    add_parser.add_argument("--jcr-quartile", default="", help="JCR quartile.")
    add_parser.add_argument("--cas-quartile", default="", help="CAS quartile.")
    add_parser.add_argument("--submission-status", default="", help="Article submission status.")

    list_parser = outputs_subparsers.add_parser("list", help="List research outputs.")
    list_parser.add_argument("--status", choices=[status.value for status in ReviewStatus], help="Filter by review status.")
    list_parser.add_argument("--type", choices=[item.value for item in OutputType], help="Filter by output type.")
    list_parser.add_argument("--owner", help="Filter by owner member id.")

    show_parser = outputs_subparsers.add_parser("show", help="Show one research output.")
    show_parser.add_argument("output_id", help="Output id to show.")

    submit_parser = outputs_subparsers.add_parser("submit", help="Submit a draft output for review.")
    submit_parser.add_argument("output_id", help="Output id to submit.")
    submit_parser.add_argument("--actor-id", required=True, help="Actor member id.")
    submit_parser.add_argument(
        "--actor-role",
        required=True,
        choices=[role.value for role in Role],
        help="Actor role for permission checks.",
    )

    approve_parser = outputs_subparsers.add_parser("approve", help="Approve a submitted output.")
    approve_parser.add_argument("output_id", help="Output id to approve.")
    approve_parser.add_argument("--actor-id", required=True, help="Actor member id.")
    approve_parser.add_argument(
        "--actor-role",
        required=True,
        choices=[role.value for role in Role],
        help="Actor role for permission checks.",
    )
    approve_parser.add_argument("--comment", default="", help="Optional approval comment.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    repository = ResearchRepository(args.data_dir)

    try:
        if args.command == "members":
            return _handle_members(args, repository, parser)
        if args.command == "projects":
            return _handle_projects(args, repository, parser)
        if args.command == "outputs":
            return _handle_outputs(args, repository, parser)
        if args.command == "stats":
            return _handle_stats(args, repository, parser)
        if args.command == "export":
            return _handle_export(args, repository, parser)
    except (KeyError, PermissionError, ValueError) as exc:
        parser.exit(status=1, message=f"Error: {exc}\n")

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _handle_members(args: argparse.Namespace, repository: ResearchRepository, parser: argparse.ArgumentParser) -> int:
    if args.members_command == "add":
        member = Member(
            member_id=args.id,
            name=args.name,
            role=Role(args.role),
            email=args.email,
            notes=args.notes,
        )
        repository.add_member(member)
        print(f"Added member: {member.member_id}")
        return 0
    if args.members_command == "list":
        members = repository.list_members()
        if not members:
            print("No members found.")
            return 0
        for member in members:
            print(f"{member.member_id}\t{member.role.value}\t{member.name}\t{member.email or '-'}")
        return 0
    if args.members_command == "show":
        member = repository.get_member(args.member_id)
        print(f"Member ID: {member.member_id}")
        print(f"Name: {member.name}")
        print(f"Role: {member.role.value}")
        print(f"Email: {member.email or '-'}")
        print(f"Notes: {member.notes or '-'}")
        return 0
    parser.error("Please choose a members subcommand.")
    return 2


def _handle_projects(args: argparse.Namespace, repository: ResearchRepository, parser: argparse.ArgumentParser) -> int:
    if args.projects_command == "add":
        project = Project(
            project_id=args.id,
            name=args.name,
            project_type=args.type,
            owner_member_ids=args.owner,
            funding_source=args.funding_source,
            start_year=args.start_year,
            end_year=args.end_year,
        )
        repository.add_project(project)
        print(f"Added project: {project.project_id}")
        return 0
    if args.projects_command == "list":
        projects = repository.list_projects()
        if not projects:
            print("No projects found.")
            return 0
        for project in projects:
            owners = ", ".join(project.owner_member_ids) if project.owner_member_ids else "-"
            print(f"{project.project_id}\t{project.project_type}\t{project.name}\t{owners}")
        return 0
    if args.projects_command == "show":
        project = repository.get_project(args.project_id)
        print(f"Project ID: {project.project_id}")
        print(f"Name: {project.name}")
        print(f"Type: {project.project_type}")
        print(f"Owners: {', '.join(project.owner_member_ids) if project.owner_member_ids else '-'}")
        print(f"Funding Source: {project.funding_source or '-'}")
        print(f"Start Year: {project.start_year if project.start_year is not None else '-'}")
        print(f"End Year: {project.end_year if project.end_year is not None else '-'}")
        return 0
    parser.error("Please choose a projects subcommand.")
    return 2


def _handle_outputs(args: argparse.Namespace, repository: ResearchRepository, parser: argparse.ArgumentParser) -> int:
    if args.outputs_command == "add":
        output_type = OutputType(args.type)
        actor_role = Role(args.actor_role)
        if actor_role != Role.MEMBER and not args.actor_id.strip():
            raise ValueError("actor-id is required when actor-role is not member.")
        article = None
        if output_type == OutputType.ARTICLE:
            article_type = args.article_type or "research_article"
            article = ArticleMetadata(
                article_type=article_type,
                journal=args.journal,
                doi=args.doi,
                issn=args.issn,
                pmid=args.pmid,
                publication_year=args.publication_year,
                volume=args.volume,
                issue=args.issue,
                pages=args.pages,
                impact_factor=args.impact_factor,
                jcr_quartile=args.jcr_quartile,
                cas_quartile=args.cas_quartile,
                submission_status=args.submission_status,
            )
        output = ResearchOutput(
            output_id=args.id,
            title=args.title,
            output_type=output_type,
            owner_member_ids=args.owner,
            participant_member_ids=args.participant,
            project_ids=args.project,
            year=args.year,
            keywords=args.keyword,
            summary=args.summary,
            notes=args.notes,
            article=article,
        )
        actor_member_id = args.actor_id or output.owner_member_ids[0]
        repository.add_output(output, actor_role=actor_role, actor_member_id=actor_member_id)
        print(f"Added research output: {output.output_id}")
        return 0
    if args.outputs_command == "list":
        outputs = repository.list_outputs(status=args.status, output_type=args.type, owner_member_id=args.owner)
        if not outputs:
            print("No research outputs found.")
            return 0
        for output in outputs:
            owners = ",".join(output.owner_member_ids)
            print(
                f"{output.output_id}\t{output.output_type.value}\t{output.review_status.value}\t"
                f"{output.year or '-'}\t{owners}\t{output.title}"
            )
        return 0
    if args.outputs_command == "show":
        output = repository.get_output(args.output_id)
        print(f"Output ID: {output.output_id}")
        print(f"Title: {output.title}")
        print(f"Type: {output.output_type.value}")
        print(f"Review Status: {output.review_status.value}")
        print(f"Owners: {', '.join(output.owner_member_ids)}")
        print(f"Participants: {', '.join(output.participant_member_ids) if output.participant_member_ids else '-'}")
        print(f"Projects: {', '.join(output.project_ids) if output.project_ids else '-'}")
        print(f"Year: {output.year if output.year is not None else '-'}")
        print(f"Keywords: {', '.join(output.keywords) if output.keywords else '-'}")
        print(f"Summary: {output.summary or '-'}")
        print(f"Notes: {output.notes or '-'}")
        if output.article:
            print(f"Article Type: {output.article.article_type}")
            print(f"Journal: {output.article.journal or '-'}")
            print(f"DOI: {output.article.doi or '-'}")
            print(f"Submission Status: {output.article.submission_status or '-'}")
        return 0
    if args.outputs_command == "submit":
        updated = repository.submit_output(
            args.output_id,
            actor_role=Role(args.actor_role),
            actor_member_id=args.actor_id,
        )
        print(f"Research output submitted: {updated.output_id} -> {updated.review_status.value}")
        return 0
    if args.outputs_command == "approve":
        updated = repository.approve_output(
            args.output_id,
            actor_role=Role(args.actor_role),
            actor_member_id=args.actor_id,
            comment=args.comment,
        )
        print(f"Research output approved: {updated.output_id} -> {updated.review_status.value}")
        return 0
    parser.error("Please choose an outputs subcommand.")
    return 2


def _handle_stats(args: argparse.Namespace, repository: ResearchRepository, parser: argparse.ArgumentParser) -> int:
    if args.stats_command == "summary":
        summary = repository.build_summary()
        print(f"Total outputs: {summary['total_outputs']}")
        print("By type:")
        for key, value in summary["by_type"].items():
            print(f"  {key}: {value}")
        print("By review status:")
        for key, value in summary["by_review_status"].items():
            print(f"  {key}: {value}")
        if summary["by_year"]:
            print("By year:")
            for key, value in summary["by_year"].items():
                print(f"  {key}: {value}")
        return 0
    parser.error("Please choose a stats subcommand.")
    return 2


def _handle_export(args: argparse.Namespace, repository: ResearchRepository, parser: argparse.ArgumentParser) -> int:
    if args.export_command == "csv":
        output_path = repository.export_outputs_csv(args.output)
        print(f"Exported CSV: {output_path}")
        return 0
    parser.error("Please choose an export subcommand.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
