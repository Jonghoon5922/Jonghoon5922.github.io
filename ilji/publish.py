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


def _gh(*args: str) -> tuple[int, str, str]:
    try:
        done = subprocess.run(
            ["gh", *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except FileNotFoundError:
        return 127, "", "gh 명령이 없다."
    return done.returncode, done.stdout, done.stderr


def open_pr(
    config: Config,
    draft_id: str,
    title: str | None = None,
    body: str | None = None,
) -> dict:
    """초안을 PR 로 올린다. merge 는 사람이 한다.

    로컬 작업 트리는 건드리지 않는다 — 브랜치를 GitHub 쪽에서 만들고 파일도 거기에 올린다.
    도구 코드를 고치던 중에 브랜치가 갈아엎히면 안 되기 때문이다.
    초안은 로컬 drafts/ 에 그대로 둔다. merge 후 pull 하면 posts/ 로 들어온다.
    """
    import base64
    import urllib.parse

    from .drafts import _find

    path, status = _find(config, draft_id)
    if status != "draft":
        return {"opened": False, "note": f"초안이 아니다: {draft_id}"}

    # 나가는 출구다. 여기서도 검사한다.
    result = check.check_file(path, config)
    if not result["ok"]:
        return {"opened": False, "check": result, "note": "검사에 걸려 PR 을 열지 않았다."}

    slug = _repo_slug(config)
    if not slug:
        return {"opened": False, "note": "GitHub 원격이 아니다."}

    branch = f"post/{draft_id}"
    rc, out, err = _gh("api", f"repos/{slug}/git/ref/heads/main", "-q", ".object.sha")
    if rc != 0:
        return {"opened": False, "note": f"main 을 찾지 못했다: {err.strip()}"}
    base_sha = out.strip()

    rc, _, err = _gh(
        "api", "-X", "POST", f"repos/{slug}/git/refs",
        "-f", f"ref=refs/heads/{branch}", "-f", f"sha={base_sha}",
    )
    if rc != 0 and "already exists" not in err:
        return {"opened": False, "note": f"브랜치를 만들지 못했다: {err.strip()}"}

    target = f"{config.blog.posts_dir}/{path.name}"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    rc, _, err = _gh(
        "api", "-X", "PUT",
        f"repos/{slug}/contents/{urllib.parse.quote(target)}",
        "-f", f"message=post: {draft_id}",
        "-f", f"content={encoded}",
        "-f", f"branch={branch}",
    )
    if rc != 0:
        return {"opened": False, "note": f"파일을 올리지 못했다: {err.strip()}"}

    pr_body = body or (
        f"`{draft_id}` 초안.\n\n"
        f"마스킹 검사 통과 (경고 {result['warnings']}건).\n"
        "merge 하면 Actions 가 빌드해 사이트에 반영된다."
    )
    rc, out, err = _gh(
        "pr", "create", "--repo", slug, "--head", branch, "--base", "main",
        "--title", title or f"post: {draft_id}", "--body", pr_body,
    )
    if rc != 0:
        return {"opened": False, "branch": branch, "note": f"PR 생성 실패: {err.strip()}"}

    return {
        "opened": True,
        "branch": branch,
        "url": out.strip().splitlines()[-1] if out.strip() else None,
        "check": result,
        "note": "PR 을 열었다. merge 는 사람이 한다. merge 되면 사이트에 반영된다.",
    }
