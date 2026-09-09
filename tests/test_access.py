"""접근 범위 방어. 여기가 뚫리면 되돌릴 수 없으므로 테스트로 못 박는다."""

from pathlib import Path

import pytest

from ilji.config import AccessDenied, Project, resolve_within


def test_안쪽_경로는_통과한다(tmp_path: Path):
    (tmp_path / "SPEC.md").write_text("x", encoding="utf-8")
    assert resolve_within(tmp_path, "SPEC.md") == (tmp_path / "SPEC.md").resolve()


def test_상위로_빠져나가는_경로는_거부된다(tmp_path: Path):
    with pytest.raises(AccessDenied):
        resolve_within(tmp_path, "../바깥.md")


def test_절대경로로_탈출하는_것도_거부된다(tmp_path: Path):
    with pytest.raises(AccessDenied):
        resolve_within(tmp_path, "C:/Windows/System32/drivers/etc/hosts")


def test_비공개_프로젝트는_재료수집을_거부한다(tmp_path: Path):
    project = Project(name="poc", path=tmp_path, public=False)
    with pytest.raises(AccessDenied):
        project.require_public()


def test_공개_프로젝트는_통과한다(tmp_path: Path):
    Project(name="seojae", path=tmp_path, public=True).require_public()
