"""CLI — 설정과 프로젝트 등록, 그리고 MCP 서버 실행.

설정 실물(`~/.ilji/ilji.toml`)에는 금지어 목록이 들어간다.
그래서 이 파일은 블로그 저장소 안에 절대 만들지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, collect, config as cfg, posts, weekly as weekly_mod

app = typer.Typer(
    add_completion=False,
    help="일지 — 프로젝트의 git 기록에서 블로그 글을 뽑는 도구",
    no_args_is_help=True,
)

# stdout 은 MCP 채널이 될 수 있다. 사람에게 하는 말은 전부 stderr 로 보낸다.
err = Console(stderr=True)


def _toml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render(config_blog: Path, projects: list[cfg.Project], forbidden: cfg.Forbidden) -> str:
    lines = [
        "# 일지 설정. 이 파일은 공개 저장소에 두지 않는다 — 금지어 목록이 들어 있다.",
        "",
        "[blog]",
        f"path = {_toml_str(config_blog.as_posix())}",
        'posts_dir = "src/content/posts"',
        'drafts_dir = "drafts"',
        "",
    ]
    for p in projects:
        lines += [
            "[[projects]]",
            f"name = {_toml_str(p.name)}",
            f"path = {_toml_str(p.path.as_posix())}",
            f"public = {'true' if p.public else 'false'}",
        ]
        if p.repo:
            lines.append(f"repo = {_toml_str(p.repo)}")
        lines.append("")

    lines += [
        "[forbidden]",
        "# 고객사명·내부 시스템명 등. 한 번 공개되면 되돌릴 수 없다.",
        "words = [" + ", ".join(_toml_str(w) for w in forbidden.words) + "]",
        "# 정규식. 키·이메일 패턴 같은 것.",
        "patterns = [" + ", ".join(_toml_str(p) for p in forbidden.patterns) + "]",
        "# 등록되지 않은 절대 경로가 본문에 나오면 걸러낸다.",
        f"detect_paths = {'true' if forbidden.detect_paths else 'false'}",
        "",
    ]
    return "\n".join(lines)


DEFAULT_PATTERNS = [
    r"sk-[A-Za-z0-9]{16,}",
    r"AKIA[0-9A-Z]{16}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]


@app.command()
def init(
    blog: Path = typer.Option(Path.cwd(), "--blog", help="블로그 저장소 경로"),
) -> None:
    """`~/.ilji/ilji.toml` 골격을 만든다."""
    path = cfg.config_path()
    if path.exists():
        err.print(f"[yellow]이미 있다:[/yellow] {path}")
        raise typer.Exit(0)

    path.parent.mkdir(parents=True, exist_ok=True)
    forbidden = cfg.Forbidden(words=[], patterns=list(DEFAULT_PATTERNS))
    path.write_text(_render(blog.resolve(), [], forbidden), encoding="utf-8")
    err.print(f"[green]설정을 만들었다:[/green] {path}")
    err.print("금지어(words) 는 직접 채운다. 이 파일은 공개 저장소에 두지 않는다.")


@app.command()
def add(
    path: Path = typer.Argument(..., help="프로젝트 폴더"),
    name: str = typer.Option(None, "--name", help="글에서 쓸 이름 (기본: 폴더 이름)"),
    private: bool = typer.Option(False, "--private", help="재료 수집을 거부한다"),
) -> None:
    """프로젝트를 등록한다."""
    config = cfg.load()
    target = path.expanduser().resolve()

    if not target.is_dir():
        err.print(f"[red]폴더가 아니다:[/red] {target}")
        raise typer.Exit(1)

    # 감싸는 폴더를 잘못 등록하면 그 옆의 키 파일까지 읽을 수 있게 된다.
    # git 저장소가 아니면 한 칸 아래를 살펴보고 알려준다.
    if not collect.is_repo(target):
        nested = [d for d in target.iterdir() if d.is_dir() and collect.is_repo(d)]
        err.print(f"[yellow]git 저장소가 아니다:[/yellow] {target}")
        if nested:
            err.print("아래 폴더가 저장소다. 이쪽을 등록하는 게 맞다:")
            for d in nested:
                err.print(f"  {d}")
            raise typer.Exit(1)

    label = name or target.name
    if any(p.name == label for p in config.projects):
        err.print(f"[red]이미 등록된 이름이다:[/red] {label}")
        raise typer.Exit(1)

    repo = None
    try:
        repo = collect._git(target, "remote", "get-url", "origin").strip() or None
    except collect.GitError:
        pass

    config.projects.append(
        cfg.Project(name=label, path=target, public=not private, repo=repo)
    )
    cfg.config_path().write_text(
        _render(config.blog.path, config.projects, config.forbidden), encoding="utf-8"
    )
    flag = " (비공개)" if private else ""
    err.print(f"[green]등록했다:[/green] {label}{flag} → {target}")


@app.command()
def status() -> None:
    """프로젝트별 마지막 글 이후 커밋 수와 초안 수."""
    config = cfg.load()

    table = Table(title="일지 현황", title_style="")
    table.add_column("프로젝트")
    table.add_column("공개")
    table.add_column("마지막 글")
    table.add_column("이후 커밋", justify="right")
    table.add_column("HEAD")

    for project in config.projects:
        last = posts.last_published(config, project.name)
        if not project.public:
            table.add_row(project.name, "✗", "-", "-", "-")
            continue
        n = collect.count_since(project, last.until_commit if last else None)
        table.add_row(
            project.name,
            "○",
            last.date.isoformat() if last and last.date else "없음",
            str(n),
            collect.head(project) or "-",
        )

    err.print(table)
    drafts = posts.list_posts(config, status="draft")
    published = posts.list_posts(config, status="published")
    err.print(f"게시글 {len(published)}편 · 초안 {len(drafts)}편")


@app.command()
def serve() -> None:
    """MCP(stdio) 서버를 띄운다. Claude 가 이 명령을 실행한다."""
    from .server import serve as run_server

    config = cfg.load()
    err.print(f"[dim]일지 MCP 서버 시작 (stdio) — 프로젝트 {len(config.projects)}개[/dim]")
    run_server(config)


@app.command()
def version() -> None:
    """버전."""
    err.print(f"ilji {__version__}")


@app.command()
def weekly(
    as_json: bool = typer.Option(False, "--json", help="기계가 읽을 형태로"),
    min_commits: int = typer.Option(
        weekly_mod.MIN_COMMITS, "--min-commits", help="이 미만이면 건너뛴다"
    ),
) -> None:
    """이번 주 쓸 재료가 있는 프로젝트를 추린다.

    결과는 stdout 으로 낸다 — 스케줄 에이전트가 이걸 읽고 초안을 쓴다.
    재료가 없으면 아무 프로젝트도 나오지 않는다. 억지로 주 1회를 채우지 않는다.
    """
    import json as _json

    result = weekly_mod.gather(cfg.load(), min_commits=min_commits)
    print(_json.dumps(result, ensure_ascii=False, indent=2) if as_json else weekly_mod.render(result))


if __name__ == "__main__":
    app()
