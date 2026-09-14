"""재료 모으기 — git 기록과 프로젝트 문서를 읽는다.

읽기 전용이다. 이 모듈은 어떤 프로젝트 폴더에도 쓰지 않는다.
GitPython 대신 subprocess 로 git 을 부른다 — 의존을 하나 줄이고,
출력 형식을 우리가 직접 정할 수 있다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import AccessDenied, Project, resolve_within

# 커밋 하나의 시작을 나타내는 표시. 파일 이름에 나올 수 없는 문자를 쓴다.
_REC = "\x1e"
_SEP = "\x1f"

# 한 번에 돌려주는 diff 의 상한. 넘으면 잘라서 알린다.
DIFF_LIMIT = 60_000
DOC_LIMIT = 200_000


class GitError(Exception):
    """git 명령이 실패했다."""


@dataclass
class Commit:
    hash: str
    short: str
    date: str
    subject: str
    files: list[str]

    def as_dict(self) -> dict:
        return {
            "hash": self.short,
            "full_hash": self.hash,
            "date": self.date,
            "subject": self.subject,
            "files": self.files,
        }


def _git(root: Path, *args: str) -> str:
    """프로젝트 폴더에서 git 을 돌린다."""
    try:
        done = subprocess.run(
            # core.quotepath=false 를 주지 않으면 한글 파일명이
            # ë 같은 8진 이스케이프로 나온다.
            ["git", "-C", str(root), "-c", "core.quotepath=false", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:  # git 자체가 없다
        raise GitError("git 을 찾을 수 없다.") from exc

    if done.returncode != 0:
        raise GitError((done.stderr or done.stdout).strip() or "git 명령이 실패했다.")
    return done.stdout


def is_repo(root: Path) -> bool:
    try:
        return _git(root, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except GitError:
        return False


def head(project: Project) -> str | None:
    """현재 HEAD 의 짧은 해시. 초안의 until_commit 기준점이 된다."""
    try:
        return _git(project.path, "rev-parse", "--short", "HEAD").strip()
    except GitError:
        return None


def count_since(project: Project, since: str | None) -> int:
    """since 이후 커밋 수. 마지막 글 이후 얼마나 쌓였는지 세는 데 쓴다."""
    if not is_repo(project.path):
        return 0
    try:
        rev = f"{since}..HEAD" if since else "HEAD"
        out = _git(project.path, "rev-list", "--count", rev)
        return int(out.strip() or 0)
    except (GitError, ValueError):
        # since 가 이 저장소에 없는 커밋일 수 있다. 그때는 세지 않는다.
        return 0


def get_changes(project: Project, since: str | None = None, limit: int = 100) -> dict:
    """커밋 목록과 요약 통계.

    since 는 커밋 해시나 날짜(`2026-09-01`)를 받는다. 비우면 전체에서 limit 만큼.
    """
    project.require_public()
    if not is_repo(project.path):
        raise GitError(
            f"'{project.name}' 는 git 저장소가 아니다: {project.path}\n"
            "감싸는 폴더를 등록하지 않았는지 확인한다."
        )

    fmt = f"{_REC}%H{_SEP}%h{_SEP}%aI{_SEP}%s"
    args = ["log", f"--pretty=format:{fmt}", "--name-only", f"-{limit}"]
    if since:
        # 해시면 범위로, 날짜면 --since 로 해석한다.
        if _looks_like_rev(project, since):
            args.append(f"{since}..HEAD")
        else:
            args.append(f"--since={since}")

    commits = _parse_log(_git(project.path, *args))

    touched: set[str] = set()
    for c in commits:
        touched.update(c.files)

    return {
        "project": project.name,
        "since": since,
        "commits": [c.as_dict() for c in commits],
        "summary": {
            "commit_count": len(commits),
            "file_count": len(touched),
            "first_date": commits[-1].date if commits else None,
            "last_date": commits[0].date if commits else None,
            "head": commits[0].short if commits else None,
        },
    }


def _looks_like_rev(project: Project, value: str) -> bool:
    try:
        _git(project.path, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}")
        return True
    except GitError:
        return False


def _parse_log(out: str) -> list[Commit]:
    commits: list[Commit] = []
    for chunk in out.split(_REC):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, _, rest = chunk.partition("\n")
        parts = header.split(_SEP)
        if len(parts) < 4:
            continue
        files = [line for line in rest.splitlines() if line.strip()]
        commits.append(
            Commit(hash=parts[0], short=parts[1], date=parts[2], subject=parts[3], files=files)
        )
    return commits


def get_diff(
    project: Project,
    commit: str | None = None,
    path: str | None = None,
    limit: int = DIFF_LIMIT,
) -> dict:
    """커밋 하나의 diff, 또는 특정 경로의 변경 이력."""
    project.require_public()
    if not is_repo(project.path):
        raise GitError(f"'{project.name}' 는 git 저장소가 아니다.")

    if commit:
        args = ["show", "--patch", "--stat", commit]
        if path:
            args += ["--", path]
    elif path:
        args = ["log", "--patch", "-10", "--", path]
    else:
        raise GitError("commit 이나 path 중 하나는 필요하다.")

    text = _git(project.path, *args)
    truncated = len(text) > limit
    return {
        "project": project.name,
        "commit": commit,
        "path": path,
        "diff": text[:limit],
        "truncated": truncated,
        "note": "너무 커서 잘랐다. 경로를 좁혀서 다시 요청한다." if truncated else None,
    }


def read_doc(project: Project, relative: str, limit: int = DOC_LIMIT) -> dict:
    """프로젝트 안 문서 원문. 등록된 폴더 밖은 거부한다."""
    project.require_public()
    target = resolve_within(project.path, relative)

    if not target.exists():
        raise AccessDenied(f"없는 파일이다: {relative}")
    if target.is_dir():
        raise AccessDenied(f"파일이 아니라 폴더다: {relative}")

    raw = target.read_bytes()
    if b"\x00" in raw[:4096]:
        raise AccessDenied(f"텍스트 파일이 아니다: {relative}")

    text = raw.decode("utf-8", errors="replace")
    truncated = len(text) > limit
    return {
        "project": project.name,
        "path": relative,
        "content": text[:limit],
        "truncated": truncated,
    }


def list_docs(project: Project, limit: int = 60) -> list[str]:
    """프로젝트 뿌리의 문서들. 글감을 고를 때 뭘 읽을지 보여준다."""
    project.require_public()
    names = []
    for p in sorted(project.path.glob("*.md")):
        names.append(p.name)
    for extra in ("docs", "design"):
        d = project.path / extra
        if d.is_dir():
            names += [f"{extra}/{p.name}" for p in sorted(d.glob("*.md"))]
    return names[:limit]
