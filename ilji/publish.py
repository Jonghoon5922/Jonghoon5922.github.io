"""게시 — 블로그 저장소에 커밋하고 push 한다.

이 저장소에는 글과 도구 코드가 같이 산다. 그래서 절대로 `git add -A` 를 쓰지 않는다.
작업 중이던 도구 코드가 글과 함께 딸려 나가면 안 된다.
스테이징 범위는 posts 폴더 하나로 못 박는다.

그리고 push 는 되돌릴 수 없는 출구다. 여기서도 마스킹 검사를 한 번 더 한다.
approve 에서 이미 걸렀더라도, 그 뒤에 본문이 바뀌었을 수 있다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import check
from .collect import GitError, _git
from .config import Config


def _staged_posts(config: Config) -> list[str]:
    out = _git(config.blog.path, "diff", "--cached", "--name-only")
    return [line.strip() for line in out.splitlines() if line.strip()]


def publish(config: Config, message: str | None = None, push: bool = True) -> dict:
    """posts 폴더의 변경만 커밋하고 push 한다.

    사용자가 명시적으로 요청했을 때만 불려야 한다.
    """
    root = config.blog.path
    posts_rel = config.blog.posts_dir

    # 스테이징 범위를 posts 폴더로 한정한다. 삭제도 함께 잡히도록 -A 를 이 경로에만 건다.
    _git(root, "add", "-A", "--", posts_rel)

    staged = _staged_posts(config)
    if not staged:
        return {"published": False, "note": "게시할 변경이 없다.", "files": []}

    # 나가는 출구에서 한 번 더 검사한다.
    blocked: list[dict] = []
    for rel in staged:
        path = root / rel
        if not path.exists() or path.suffix != ".md":
            continue
        result = check.check_file(path, config)
        if not result["ok"]:
            blocked.append(result)

    if blocked:
        _git(root, "reset", "--quiet", "HEAD", "--", posts_rel)
        return {
            "published": False,
            "note": "검사에 걸려 게시하지 않았다. 스테이징도 되돌렸다.",
            "blocked": blocked,
        }

    subject = message or f"post: {len(staged)}건 게시"
    try:
        _git(root, "commit", "-m", subject, "--", posts_rel)
    except GitError as exc:
        return {"published": False, "note": f"커밋 실패: {exc}", "files": staged}

    head = _git(root, "rev-parse", "--short", "HEAD").strip()
    result = {
        "published": True,
        "commit": head,
        "files": staged,
        "pushed": False,
        "note": "커밋했다.",
    }

    if push:
        try:
            _git(root, "push", "origin", "HEAD")
            result["pushed"] = True
            result["note"] = "push 했다. Actions 가 빌드하면 사이트에 반영된다. deploy_status 로 확인한다."
        except GitError as exc:
            result["note"] = f"커밋은 됐지만 push 가 실패했다: {exc}"

    return result


def _repo_slug(config: Config) -> str | None:
    try:
        url = _git(config.blog.path, "remote", "get-url", "origin").strip()
    except GitError:
        return None
    url = url.removesuffix(".git")
    if "github.com" not in url:
        return None
    tail = url.split("github.com", 1)[1].lstrip(":/")
    return tail or None


def deploy_status(config: Config, limit: int = 3) -> dict:
    """Actions 빌드 상태. 이걸 못 보면 게시했다고 착각하게 된다."""
    slug = _repo_slug(config)
    if not slug:
        return {"available": False, "note": "GitHub 원격이 아니라 배포 상태를 알 수 없다."}

    try:
        done = subprocess.run(
            [
                "gh", "run", "list", "--repo", slug, "--limit", str(limit),
                "--json", "displayTitle,status,conclusion,createdAt,url",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    except FileNotFoundError:
        return {"available": False, "note": "gh 명령이 없어 배포 상태를 알 수 없다."}

    if done.returncode != 0:
        return {"available": False, "note": (done.stderr or "gh 실행 실패").strip()}

    try:
        runs = json.loads(done.stdout or "[]")
    except json.JSONDecodeError:
        return {"available": False, "note": "gh 응답을 읽지 못했다."}

    latest = runs[0] if runs else None
    return {
        "available": True,
        "repo": slug,
        "site": f"https://{slug.split('/')[0].lower()}.github.io/",
        "latest": latest,
        "runs": runs,
        "note": (
            "빌드 성공. 사이트에 반영됐다."
            if latest and latest.get("conclusion") == "success"
            else "아직 도는 중이거나 실패했다. runs 를 확인한다."
        ),
    }


def blog_state(config: Config) -> dict:
    """블로그 저장소의 현재 상태. push 안 된 게 있는지 등."""
    root: Path = config.blog.path
    try:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        dirty = bool(_git(root, "status", "--porcelain", "--", config.blog.posts_dir).strip())
        ahead = _git(root, "rev-list", "--count", "@{u}..HEAD").strip()
    except GitError as exc:
        return {"ok": False, "note": str(exc)}
    return {
        "ok": True,
        "branch": branch,
        "posts_dir_dirty": dirty,
        "unpushed_commits": int(ahead or 0),
    }
