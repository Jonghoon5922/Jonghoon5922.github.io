"""마스킹 검사. 여기가 뚫리면 되돌릴 수 없다."""

from pathlib import Path

from blogging.check import BLOCK, WARN, scan
from blogging.config import Blog, Config, Forbidden, Project


def _config(tmp_path: Path, words=None) -> Config:
    return Config(
        blog=Blog(path=tmp_path / "blog"),
        projects=[Project(name="seojae", path=tmp_path / "bookshelf")],
        forbidden=Forbidden(
            words=words or [],
            patterns=[r"sk-[A-Za-z0-9]{16,}", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"],
        ),
        source=tmp_path / "blogging.toml",
    )


def _rules(findings):
    return {(f.rule, f.level) for f in findings}


def test_금지어는_막는다(tmp_path):
    c = _config(tmp_path, words=["넥스트뱅크"])
    found = scan("넥스트뱅크 전환 작업을 했다.", c)
    assert [f.level for f in found] == [BLOCK]
    assert found[0].rule == "금지어"


def test_금지어는_대소문자를_가리지_않는다(tmp_path):
    c = _config(tmp_path, words=["AsIs"])
    assert scan("asis 소스를 봤다", c)


def test_걸린_낱말을_그대로_돌려주지_않는다(tmp_path):
    """검사 결과에 원문이 그대로 실리면 그 결과 자체가 유출 경로가 된다."""
    c = _config(tmp_path, words=["대외비고객사명"])
    found = scan("대외비고객사명 이야기", c)
    assert "대외비고객사명" not in found[0].matched


def test_등록되지_않은_절대경로는_막는다(tmp_path):
    c = _config(tmp_path)
    found = scan(r"설정은 C:\poc\secret\key.txt 에 있다", c)
    assert ("등록되지 않은 절대 경로", BLOCK) in _rules(found)


def test_등록된_폴더_경로는_경고만_한다(tmp_path):
    c = _config(tmp_path)
    found = scan(f"서재는 {(tmp_path / 'bookshelf').as_posix()} 에 있다", c)
    assert ("로컬 절대 경로(등록됨)", WARN) in _rules(found)


def test_키와_이메일은_막는다(tmp_path):
    c = _config(tmp_path)
    found = scan("키는 sk-abcdefghijklmnopqrstuvwxyz 이고 메일은 a@b.com 이다", c)
    assert len([f for f in found if f.level == BLOCK]) == 2


def test_평범한_문장은_통과한다(tmp_path):
    c = _config(tmp_path, words=["넥스트뱅크"])
    assert scan("BM25 로 한국어 검색을 붙였다. 임베딩 서버는 쓰지 않았다.", c) == []
