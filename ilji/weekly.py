"""주간 루틴 — 이번 주에 쓸 만한 재료가 있는 프로젝트를 골라준다.

스케줄 에이전트가 이 결과를 읽고 초안을 쓴다.
변경이 없는 프로젝트는 아예 빼서, 쓸 게 없으면 아무 일도 안 일어나게 한다.
억지로 주 1회를 채우면 글이 아니라 변경 로그가 된다.
"""

from __future__ import annotations

from . import collect, posts
from .config import Config

# 이 정도 미만이면 글 한 편 분량이 안 된다고 보고 넘긴다.
MIN_COMMITS = 3


def gather(config: Config, min_commits: int = MIN_COMMITS, sample: int = 15) -> dict:
    ready: list[dict] = []
    skipped: list[dict] = []

    for project in config.projects:
        if not project.public:
            skipped.append({"project": project.name, "reason": "비공개 프로젝트"})
            continue
        if not collect.is_repo(project.path):
            skipped.append({"project": project.name, "reason": "git 저장소가 아니다"})
            continue

        last = posts.last_published(config, project.name)
        since = last.until_commit if last else None
        n = collect.count_since(project, since)

        if n < min_commits:
            skipped.append(
                {
                    "project": project.name,
                    "reason": f"이후 커밋 {n}건 (기준 {min_commits}건 미만)",
                }
            )
            continue

        changes = collect.get_changes(project, since=since, limit=sample)
        ready.append(
            {
                "project": project.name,
                "since": since,
                "last_post": (
                    {"title": last.title, "date": last.date.isoformat() if last.date else None}
                    if last
                    else None
                ),
                "commits_since": n,
                "head": collect.head(project),
                "recent": [
                    {"hash": c["hash"], "date": c["date"][:10], "subject": c["subject"]}
                    for c in changes["commits"]
                ],
                "files_touched": changes["summary"]["file_count"],
                "docs": collect.list_docs(project),
            }
        )

    ready.sort(key=lambda r: r["commits_since"], reverse=True)
    return {
        "ready": ready,
        "skipped": skipped,
        "note": (
            "쓸 재료가 있는 프로젝트가 없다. 이번 주는 건너뛴다."
            if not ready
            else f"{len(ready)}개 프로젝트에 재료가 있다."
        ),
    }


def render(result: dict) -> str:
    """스케줄 에이전트가 읽을 사람 말 요약."""
    if not result["ready"]:
        lines = ["이번 주 쓸 재료가 없다. 건너뛴다.", ""]
        for s in result["skipped"]:
            lines.append(f"  - {s['project']}: {s['reason']}")
        return "\n".join(lines)

    lines = [f"재료가 있는 프로젝트 {len(result['ready'])}개", ""]
    for r in result["ready"]:
        last = r["last_post"]
        base = f"마지막 글 {last['date']} 이후" if last else "첫 글"
        lines.append(f"## {r['project']} — {base} 커밋 {r['commits_since']}건")
        lines.append(f"기준점 since={r['since'] or '(없음)'} · 현재 HEAD={r['head']}")
        lines.append("")
        for c in r["recent"]:
            lines.append(f"  {c['hash']}  {c['date']}  {c['subject']}")
        lines.append("")
        lines.append(f"읽을 수 있는 문서: {', '.join(r['docs']) or '(없음)'}")
        lines.append("")

    if result["skipped"]:
        lines.append("건너뜀:")
        for s in result["skipped"]:
            lines.append(f"  - {s['project']}: {s['reason']}")
    return "\n".join(lines)
