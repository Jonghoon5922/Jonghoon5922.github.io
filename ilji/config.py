"""설정과 접근 범위.

이 도구가 읽을 수 있는 곳은 ilji.toml 에 등록된 프로젝트 폴더와 블로그 저장소뿐이다.
그 밖의 경로 요청은 전부 거부한다 — 등록하지 않은 폴더가 실수로 글감이 되는 일이 없어야 한다.

설정 실물은 ~/.ilji/ilji.toml 에만 둔다. 금지어 목록이 들어 있어서
공개 저장소에 절대 들어가면 안 된다.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIRNAME = ".ilji"
CONFIG_FILENAME = "ilji.toml"


class ConfigError(Exception):
    """설정이 없거나 잘못됐다."""


class AccessDenied(Exception):
    """등록되지 않은 경로, 또는 비공개 프로젝트에 대한 접근."""


@dataclass
class Project:
    name: str
    path: Path
    public: bool = True
    repo: str | None = None

    def require_public(self) -> None:
        """비공개 프로젝트는 재료 수집 자체를 거부한다.

        PoC 작업 폴더가 실수로 글감이 되지 않게 하는 마지막 방어선이다.
        """
        if not self.public:
            raise AccessDenied(
                f"'{self.name}' 은 public = false 로 등록돼 있다. 재료 수집을 거부한다."
            )


@dataclass
class Blog:
    path: Path
    posts_dir: str = "src/content/posts"
    drafts_dir: str = "drafts"

    @property
    def posts(self) -> Path:
        return self.path / self.posts_dir

    @property
    def drafts(self) -> Path:
        return self.path / self.drafts_dir


@dataclass
class Forbidden:
    """마스킹 검사 규칙. 실물 목록은 설정 파일에만 있다."""

    words: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    # 등록된 프로젝트 밖의 절대 경로가 본문에 나오면 걸러낸다.
    detect_paths: bool = True


@dataclass
class Config:
    blog: Blog
    projects: list[Project]
    forbidden: Forbidden
    source: Path

    def project(self, name: str) -> Project:
        for p in self.projects:
            if p.name == name:
                return p
        known = ", ".join(p.name for p in self.projects) or "(없음)"
        raise AccessDenied(f"'{name}' 은 등록되지 않은 프로젝트다. 등록된 것: {known}")

    def roots(self) -> list[Path]:
        """읽기가 허용된 뿌리 전부."""
        return [p.path for p in self.projects] + [self.blog.path]


def config_dir() -> Path:
    """설정 폴더. ILJI_HOME 으로 덮어쓸 수 있다 (테스트용)."""
    override = os.environ.get("ILJI_HOME")
    if override:
        return Path(override)
    return Path.home() / CONFIG_DIRNAME


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise ConfigError(f"설정이 없다: {path}\n`ilji init` 으로 만든다.")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    blog_raw = raw.get("blog") or {}
    if not blog_raw.get("path"):
        raise ConfigError("[blog] path 가 필요하다.")
    blog = Blog(
        path=Path(blog_raw["path"]).expanduser().resolve(),
        posts_dir=blog_raw.get("posts_dir", "src/content/posts"),
        drafts_dir=blog_raw.get("drafts_dir", "drafts"),
    )

    projects: list[Project] = []
    for item in raw.get("projects", []):
        if not item.get("name") or not item.get("path"):
            raise ConfigError(f"[[projects]] 에 name·path 가 필요하다: {item!r}")
        projects.append(
            Project(
                name=item["name"],
                path=Path(item["path"]).expanduser().resolve(),
                public=bool(item.get("public", True)),
                repo=item.get("repo"),
            )
        )

    f_raw = raw.get("forbidden") or {}
    forbidden = Forbidden(
        words=list(f_raw.get("words", [])),
        patterns=list(f_raw.get("patterns", [])),
        detect_paths=bool(f_raw.get("detect_paths", True)),
    )

    return Config(blog=blog, projects=projects, forbidden=forbidden, source=path)


def resolve_within(root: Path, relative: str) -> Path:
    """root 안의 경로로만 풀어준다.

    `..` 이나 심볼릭 링크로 밖으로 빠져나가는 경로는 resolve() 후 비교해서 막는다.
    문자열 검사로는 못 막는 우회가 있어서 실제 경로로 확인한다.
    """
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise AccessDenied(f"등록된 폴더 밖이다: {relative}")
    return candidate
