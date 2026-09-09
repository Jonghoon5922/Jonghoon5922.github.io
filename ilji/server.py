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

from . import (
    __version__,
    check as masking,
    collect,
    drafts,
    posts,
    publish as publishing,
    weekly as weekly_mod,
)
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

    # ── 원고 ─────────────────────────────────────────────────────────

    @server.tool(
        name="save_draft",
        description=(
            "초안을 drafts/ 에 저장한다. 저장 직후 자동으로 마스킹 검사를 돌려 결과를 함께 돌려준다. "
            "until_commit 을 비우면 그 프로젝트의 현재 HEAD 로 박는다 — 다음 글이 여기서 이어진다. "
            "초안은 저장소에 올라가지 않는다."
        ),
    )
    def save_draft_tool(
        title: str,
        body: str,
        project: str,
        tags: list[str] | None = None,
        until_commit: str | None = None,
        summary: str | None = None,
    ) -> dict:
        return drafts.save_draft(
            config, title=title, body=body, project=project,
            tags=tags, until_commit=until_commit, summary=summary,
        )

    @server.tool(
        name="update_post",
        description="이미 있는 글이나 초안의 본문·제목·요약·태그를 고친다. 고친 뒤 곧바로 검사한다.",
    )
    def update_post_tool(
        post_id: str,
        body: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        return drafts.update_post(
            config, post_id=post_id, body=body, title=title, summary=summary, tags=tags
        )

    # ── 관문 ─────────────────────────────────────────────────────────

    @server.tool(
        name="check",
        description=(
            "초안이나 글의 마스킹 검사. 금지어·키·이메일·등록되지 않은 절대 경로를 찾는다. "
            "level 이 block 인 항목이 하나라도 있으면 approve 할 수 없다. "
            "걸린 원문은 그대로 돌려주지 않는다 — 결과 자체가 유출 경로가 되면 안 되기 때문이다."
        ),
    )
    def check_tool(draft_id: str) -> dict:
        path, _ = drafts._find(config, draft_id)
        return masking.check_file(path, config)

    @server.tool(
        name="check_rules",
        description="어떤 검사 규칙이 걸려 있는지. 금지어 목록 자체는 노출하지 않는다.",
    )
    def check_rules_tool() -> dict:
        return masking.rules_summary(config)

    @server.tool(
        name="approve",
        description=(
            "검사를 통과한 초안을 posts/ 로 옮긴다. 걸린 항목이 남아 있으면 옮기지 않는다. "
            "승인해도 아직 사이트에는 없다 — 반영하려면 publish 가 따로 필요하다."
        ),
    )
    def approve_tool(draft_id: str) -> dict:
        return drafts.approve(config, draft_id)

    # ── 운영 ─────────────────────────────────────────────────────────

    @server.tool(
        name="publish",
        description=(
            "posts 폴더의 변경만 커밋하고 push 한다. push 직전에 검사를 한 번 더 돌린다. "
            "**사용자가 명시적으로 요청했을 때만 호출한다.** 스스로 판단해서 부르지 않는다."
        ),
    )
    def publish_tool(message: str | None = None) -> dict:
        return publishing.publish(config, message=message)

    @server.tool(
        name="deploy_status",
        description="Actions 빌드·배포 상태와 사이트 주소. push 후 실제로 반영됐는지 확인한다.",
    )
    def deploy_status_tool() -> dict:
        return publishing.deploy_status(config)

    @server.tool(
        name="blog_state",
        description="블로그 저장소 상태 — 브랜치, posts 폴더에 커밋 안 된 변경, push 안 된 커밋 수.",
    )
    def blog_state_tool() -> dict:
        return publishing.blog_state(config)

    @server.tool(
        name="unpublish",
        description=(
            "게시된 글을 초안으로 되돌린다. 사이트에서 실제로 내리려면 그 뒤 publish 가 필요하다."
        ),
    )
    def unpublish_tool(post_id: str) -> dict:
        return drafts.unpublish(config, post_id)

    @server.tool(
        name="weekly",
        description=(
            "재료가 쌓인 프로젝트만 추려서 돌려준다. 커밋이 기준(기본 3건) 미만인 프로젝트는 뺀다. "
            "'뭐 밀렸어?' 나 주간 초안 작성의 출발점으로 쓴다."
        ),
    )
    def weekly_tool(min_commits: int = weekly_mod.MIN_COMMITS) -> dict:
        return weekly_mod.gather(config, min_commits=min_commits)

    @server.tool(
        name="open_pr",
        description=(
            "검사를 통과한 초안을 PR 로 올린다. merge 는 사람이 한다 — 자동 게시가 아니다. "
            "로컬 작업 트리는 건드리지 않는다. publish 와 달리 바로 사이트에 나가지 않으므로, "
            "사람이 읽어보고 결정하게 하고 싶을 때 쓴다."
        ),
    )
    def open_pr_tool(draft_id: str, title: str | None = None, body: str | None = None) -> dict:
        return publishing.open_pr(config, draft_id, title=title, body=body)

    @server.tool(
        name="merge_pr",
        description=(
            "PR 을 squash 머지하고 로컬 저장소를 맞춘다. 머지되면 Actions 가 빌드해 사이트에 반영된다. "
            "로컬을 안 맞추면 '지난 글 이후' 계산이 어긋나므로 머지 후 fast-forward 까지 함께 한다."
        ),
    )
    def merge_pr_tool(pr: int, delete_branch: bool = True) -> dict:
        return publishing.merge_pr(config, pr, delete_branch=delete_branch)

    return server


def serve(config: Config | None = None) -> None:
    """stdio MCP 서버를 띄운다."""
    config = config or load_config()
    create_server(config).run("stdio")


__all__ = ["build_instructions", "create_server", "serve", "AccessDenied", "ConfigError"]
