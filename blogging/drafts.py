"""원고 — 초안 저장, 승인, 수정, 내리기.

상태 전이는 파일 이동이다.
    save_draft  →  drafts/
    approve     →  drafts/ → posts/   (check 통과가 필수)
    unpublish   →  posts/ → drafts/
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import check, collect
from .config import AccessDenied, Config
from .posts import split_frontmatter

_SLUG_STRIP = re.compile(r"[^0-9A-Za-z가-힣\s-]")
_SLUG_SPACE = re.compile(r"\s+")


def make_slug(title: str) -> str:
    text = _SLUG_STRIP.sub("", title).strip()
    text = _SLUG_SPACE.sub("-", text)
    return text[:60].strip("-") or "글"


def _frontmatter(meta: dict) -> str:
    """프론트매터를 정해진 순서로 쓴다. 순서가 흔들리면 diff 가 지저분해진다."""
    lines = ["---"]
    for key in ("title", "date", "project", "tags", "until_commit", "summary"):
        if key not in meta or meta[key] in (None, ""):
            continue
        value = meta[key]
        if key == "tags":
            lines.append(f"tags: [{', '.join(str(t) for t in value)}]")
        elif isinstance(value, str) and (":" in value or value.startswith(("[", "#"))):
            escaped = value.replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def save_draft(
    config: Config,
    title: str,
    body: str,
    project: str,
    tags: list[str] | None = None,
    until_commit: str | None = None,
    summary: str | None = None,
    slug: str | None = None,
) -> dict:
    """초안을 drafts/ 에 만든다. 게시되지 않으며, 저장소에도 올라가지 않는다."""
    proj = config.project(project)
    proj.require_public()

    # 기준점을 안 주면 지금 HEAD 로 박는다. 다음 글이 여기서부터 이어진다.
    until_commit = until_commit or collect.head(proj)

    today = date.today()
    name = f"{today.isoformat()}-{slug or make_slug(title)}"
    config.blog.drafts.mkdir(parents=True, exist_ok=True)
    path = config.blog.drafts / f"{name}.md"
    if path.exists():
        raise AccessDenied(f"같은 이름의 초안이 이미 있다: {name}")

    meta = {
        "title": title,
        "date": today.isoformat(),
        "project": project,
        "tags": tags or [],
        "until_commit": until_commit,
        "summary": summary,
    }
    path.write_text(_frontmatter(meta) + "\n\n" + body.strip() + "\n", encoding="utf-8")

    result = check.check_file(path, config)
    return {
        "id": name,
        "status": "draft",
        "until_commit": until_commit,
        "check": result,
        "note": (
            "저장했다. 검사도 통과했으니 approve 할 수 있다."
            if result["ok"]
            else "저장했지만 검사에 걸렸다. 본문을 고치고 다시 check 한다."
        ),
    }


def _find(config: Config, post_id: str) -> tuple[Path, str]:
    for folder, status in ((config.blog.drafts, "draft"), (config.blog.posts, "published")):
        candidate = folder / f"{post_id}.md"
        if candidate.exists():
            return candidate, status
    raise AccessDenied(f"없는 글이다: {post_id}")


def approve(config: Config, draft_id: str) -> dict:
    """검사를 통과한 초안만 posts/ 로 옮긴다."""
    path, status = _find(config, draft_id)
    if status != "draft":
        raise AccessDenied(f"이미 게시된 글이다: {draft_id}")

    result = check.check_file(path, config)
    if not result["ok"]:
        return {
            "approved": False,
            "id": draft_id,
            "check": result,
            "note": "검사에 걸린 항목이 남아 있어 승인하지 않았다.",
        }

    config.blog.posts.mkdir(parents=True, exist_ok=True)
    target = config.blog.posts / path.name
    if target.exists():
        raise AccessDenied(f"같은 이름의 글이 이미 있다: {draft_id}")
    path.replace(target)

    return {
        "approved": True,
        "id": draft_id,
        "status": "published",
        "check": result,
        "note": "승인했다. 아직 사이트에는 없다 — publish 는 사용자가 요청할 때만 한다.",
    }


def update_post(
    config: Config,
    post_id: str,
    body: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """이미 있는 글이나 초안을 고친다. 고친 뒤 곧바로 검사한다."""
    path, status = _find(config, post_id)
    meta, current = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))

    if title is not None:
        meta["title"] = title
    if summary is not None:
        meta["summary"] = summary
    if tags is not None:
        meta["tags"] = tags
    if isinstance(meta.get("date"), (date,)):
        meta["date"] = meta["date"].isoformat()

    path.write_text(
        _frontmatter(meta) + "\n\n" + (body if body is not None else current).strip() + "\n",
        encoding="utf-8",
    )
    return {"id": post_id, "status": status, "check": check.check_file(path, config)}


def unpublish(config: Config, post_id: str) -> dict:
    """글을 초안으로 되돌린다. 사이트에서 내리려면 그 뒤 publish 가 필요하다."""
    path, status = _find(config, post_id)
    if status != "published":
        raise AccessDenied(f"게시된 글이 아니다: {post_id}")

    config.blog.drafts.mkdir(parents=True, exist_ok=True)
    path.replace(config.blog.drafts / path.name)
    return {
        "id": post_id,
        "status": "draft",
        "note": "초안으로 되돌렸다. 사이트에서 내리려면 publish 를 해야 반영된다.",
    }
