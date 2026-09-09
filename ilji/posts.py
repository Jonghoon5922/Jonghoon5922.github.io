"""글과 초안 읽기.

상태를 담는 DB 는 없다. 파일이 어느 폴더에 있느냐가 곧 상태다.
    drafts/  → 초안
    posts/   → 게시됨
그리고 각 글 프론트매터의 project·until_commit 이
"지난 글 이후 무엇이 바뀌었나" 를 계산하는 유일한 근거다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from .config import Config


@dataclass
class Post:
    id: str
    title: str
    date: date | None
    project: str | None
    tags: list[str]
    until_commit: str | None
    status: str  # "draft" | "published"
    path: Path

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date.isoformat() if self.date else None,
            "project": self.project,
            "tags": self.tags,
            "until_commit": self.until_commit,
            "status": self.status,
        }


def split_frontmatter(text: str) -> tuple[dict, str]:
    """`---` 로 감싼 앞머리를 떼어낸다. 없으면 빈 앞머리로 본다."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].lstrip("\n")


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _read(path: Path, status: str) -> Post | None:
    try:
        meta, _ = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return Post(
        id=path.stem,
        title=str(meta.get("title") or path.stem),
        date=_as_date(meta.get("date")),
        project=meta.get("project"),
        tags=[str(t) for t in tags],
        until_commit=meta.get("until_commit"),
        status=status,
        path=path,
    )


def all_posts(config: Config) -> list[Post]:
    """게시글과 초안 전부. 최신 글이 앞에 온다."""
    found: list[Post] = []
    for folder, status in ((config.blog.posts, "published"), (config.blog.drafts, "draft")):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("**/*.md")):
            post = _read(path, status)
            if post:
                found.append(post)
    found.sort(key=lambda p: (p.date or date.min), reverse=True)
    return found


def list_posts(config: Config, project: str | None = None, status: str | None = None) -> list[dict]:
    posts = all_posts(config)
    if project:
        posts = [p for p in posts if p.project == project]
    if status:
        posts = [p for p in posts if p.status == status]
    return [p.as_dict() for p in posts]


def last_published(config: Config, project: str) -> Post | None:
    """그 프로젝트로 마지막에 게시된 글. 다음 초안의 시작점이 여기서 나온다."""
    for post in all_posts(config):
        if post.status == "published" and post.project == project:
            return post
    return None
