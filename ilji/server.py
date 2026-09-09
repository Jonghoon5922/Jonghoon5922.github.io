"""MCP 서버 (stdio).

Claude 가 재료를 모을 때 쓰는 읽기 도구들을 노출한다.
이 서버는 LLM 을 호출하지 않는다 — 글은 사용자의 Claude 가 쓰고,
이 도구는 재료를 건네줄 뿐이다.

서버 instructions 에 프로젝트 목록과 "마지막 글 이후 커밋 수" 를 주입한다.
Claude 가 무엇이 밀려 있는지 먼저 알고 시작하게 하려는 것이다.

stdout 은 MCP 프로토콜 채널이다. 이 모듈은 stdout 에 아무것도 출력하지 않는다.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import __version__, collect, posts
from .config import AccessDenied, Config, ConfigError
from .config import load as load_config


def build_instructions(config: Config) -> str:
    """프로젝트 현황을 서버 instructions 로 만든다 (SPEC 4절)."""
    lines: list[str] = []

    rows = []
    for project in config.projects:
        if not project.public:
            rows.append(f"{project.name} (비공개 — 재료 수집 거부)")
            continue
        last = posts.last_published(config, project.name)
        if last:
            since = last.until_commit
            n = collect.count_since(project, since)
            when = last.date.isoformat() if last.date else "날짜 없음"
            rows.append(f"{project.name} (마지막 글 {when}, 이후 커밋 {n}건)")
        else:
            n = collect.count_since(project, None)
            rows.append(f"{project.name} (글 없음, 커밋 {n}건)")

    lines.append("등록된 프로젝트: " + (", ".join(rows) if rows else "(없음)"))
    lines.append("")
    lines.append(
        "글을 쓰기 전 get_changes 로 재료를 모은다. 어떤 문서를 읽을 수 있는지는 "
        "list_docs 로 확인하고, 필요한 것만 read_doc 으로 읽는다."
    )
    lines.append(
        "public = false 인 프로젝트는 재료 수집 자체가 거부된다. 우회하지 않는다."
    )
    lines.append(
        "초안을 저장한 뒤에는 반드시 check 를 실행한다. 걸린 항목이 남아 있으면 "
        "approve 하지 않는다. publish 는 사용자가 직접 요청할 때만 호출한다."
    )
    return "\n".join(lines)


def create_server(config: Config) -> MCPServer:
    server = MCPServer(
        name="ilji",
        title="일지 — 블로그 운영",
        version=__version__,
        instructions=build_instructions(config),
    )

    @server.tool(
        name="list_projects",
        description=(
            "등록된 프로젝트 목록과 각 프로젝트의 마지막 글·이후 커밋 수를 돌려준다. "
            "무엇에 대해 쓸지 고를 때 먼저 호출한다."
        ),
    )
    def list_projects_tool() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for project in config.projects:
            last = posts.last_published(config, project.name)
            row: dict[str, Any] = {
                "name": project.name,
                "public": project.public,
                "is_git": collect.is_repo(project.path),
                "last_post_date": last.date.isoformat() if last and last.date else None,
                "last_post_commit": last.until_commit if last else None,
                "head": collect.head(project),
            }
            row["commits_since"] = (
                collect.count_since(project, last.until_commit if last else None)
                if project.public
                else None
            )
            out.append(row)
        return out

    @server.tool(
        name="get_changes",
        description=(
            "프로젝트의 커밋 목록과 요약 통계를 돌려준다. "
            "since 를 비우면 전체에서 최근 것부터. since 에는 커밋 해시나 날짜(2026-09-01)를 넣는다. "
            "보통 마지막 글의 until_commit 을 넣어 '지난 글 이후' 를 본다."
        ),
    )
    def get_changes_tool(project: str, since: str | None = None, limit: int = 100) -> dict:
        return collect.get_changes(config.project(project), since=since, limit=limit)

    @server.tool(
        name="get_diff",
        description=(
            "커밋 하나의 diff, 또는 특정 경로의 최근 변경 이력을 돌려준다. "
            "commit 이나 path 중 하나는 있어야 한다. 크면 잘라서 돌려준다."
        ),
    )
    def get_diff_tool(
        project: str, commit: str | None = None, path: str | None = None
    ) -> dict:
        return collect.get_diff(config.project(project), commit=commit, path=path)

    @server.tool(
        name="list_docs",
        description="프로젝트에서 읽을 수 있는 문서 목록(README.md, SPEC.md 등).",
    )
    def list_docs_tool(project: str) -> list[str]:
        return collect.list_docs(config.project(project))

    @server.tool(
        name="read_doc",
        description=(
            "프로젝트 안 문서의 원문을 읽는다. 등록된 폴더 밖의 경로는 거부된다."
        ),
    )
    def read_doc_tool(project: str, path: str) -> dict:
        return collect.read_doc(config.project(project), path)

    @server.tool(
        name="list_posts",
        description=(
            "블로그의 글과 초안 목록. status 는 draft 또는 published. "
            "project 로 걸러 볼 수 있다."
        ),
    )
    def list_posts_tool(project: str | None = None, status: str | None = None) -> list[dict]:
        return posts.list_posts(config, project=project, status=status)

    return server


def serve(config: Config | None = None) -> None:
    """stdio MCP 서버를 띄운다."""
    config = config or load_config()
    create_server(config).run("stdio")


__all__ = ["build_instructions", "create_server", "serve", "AccessDenied", "ConfigError"]
