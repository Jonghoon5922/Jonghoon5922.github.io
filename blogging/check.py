"""마스킹 검사 — 초안이 이 PC 를 떠나기 전에 거치는 관문.

"게시 직전 검사" 가 아니라 "원고가 나가는 모든 출구" 에 둔다.
나중에 미러를 붙여도 구멍이 생기지 않게 하려는 것이다.

회사 정보 유출은 되돌릴 수 없다. 공개 저장소에 한 번 올라가면
지워도 git 히스토리에 남는다. 그래서 애매하면 막는 쪽으로 판단한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config

# 윈도우 절대 경로(C:\... , C:/...)와 유닉스 홈 경로.
# 문자 클래스의 백슬래시는 이스케이프가 꼬이기 쉬워 chr(92) 로 조립한다.
_BS = chr(92) * 2
_TAIL = r"[^\s" + chr(34) + chr(39) + chr(96) + r")\]]+"
_ABS_PATH = re.compile(
    r"(?:[A-Za-z]:[" + _BS + r"/]" + _TAIL + r"|/(?:home|Users)/" + _TAIL + r")"
)

BLOCK = "block"
WARN = "warn"


@dataclass
class Finding:
    line: int
    matched: str
    rule: str
    level: str
    hint: str | None = None

    def as_dict(self) -> dict:
        return {
            "line": self.line,
            "matched": self.matched,
            "rule": self.rule,
            "level": self.level,
            "hint": self.hint,
        }


def _mask(text: str, keep: int = 3) -> str:
    """걸린 문자열을 그대로 되돌려주면 그것부터가 유출이다. 앞부분만 남긴다."""
    text = text.strip()
    if len(text) <= keep:
        return text[:keep] + "…"
    return text[:keep] + "…" + f"({len(text)}자)"


def scan(text: str, config: Config) -> list[Finding]:
    """본문을 훑어 걸리는 것들을 돌려준다. 빈 목록이면 통과."""
    findings: list[Finding] = []
    roots = [str(r).lower().replace("\\", "/") for r in config.roots()]

    for no, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()

        # 1. 금지어 — 고객사명·내부 시스템명 등. 목록은 설정 파일에만 있다.
        for word in config.forbidden.words:
            if word and word.lower() in lowered:
                findings.append(
                    Finding(no, _mask(word), "금지어", BLOCK, "설정의 words 에 등록된 낱말")
                )

        # 2. 패턴 — 키·토큰·이메일·개인키.
        for pattern in config.forbidden.patterns:
            try:
                for m in re.finditer(pattern, line):
                    findings.append(
                        Finding(no, _mask(m.group(0)), f"패턴 {pattern[:24]}", BLOCK)
                    )
            except re.error:
                continue  # 설정의 정규식이 잘못됐다고 검사를 멈추진 않는다

        # 3. 절대 경로.
        if config.forbidden.detect_paths:
            for m in _ABS_PATH.finditer(line):
                found = m.group(0)
                normalized = found.lower().replace("\\", "/")
                registered = any(normalized.startswith(r) for r in roots)
                if registered:
                    findings.append(
                        Finding(
                            no,
                            _mask(found, 8),
                            "로컬 절대 경로(등록됨)",
                            WARN,
                            "등록된 폴더지만 공개 글에 내 PC 경로를 남길 이유는 없다",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            no,
                            _mask(found, 4),
                            "등록되지 않은 절대 경로",
                            BLOCK,
                            "이 경로는 어디에도 등록돼 있지 않다",
                        )
                    )

    return findings


def check_file(path: Path, config: Config) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = scan(text, config)
    blocks = [f for f in findings if f.level == BLOCK]
    warns = [f for f in findings if f.level == WARN]
    return {
        "id": path.stem,
        "ok": not blocks,
        "blocking": len(blocks),
        "warnings": len(warns),
        "findings": [f.as_dict() for f in findings],
        "note": (
            "통과. approve 할 수 있다."
            if not blocks
            else f"{len(blocks)}건이 막고 있다. 본문을 고치고 다시 check 한다."
        ),
    }


def rules_summary(config: Config) -> dict:
    """어떤 규칙이 걸려 있는지. 목록 자체는 노출하지 않는다."""
    return {
        "words": len(config.forbidden.words),
        "patterns": len(config.forbidden.patterns),
        "detect_paths": config.forbidden.detect_paths,
        "warning": (
            "금지어 목록이 비어 있다. 고객사명·내부 시스템명을 채우기 전에는 검사가 절반만 돈다."
            if not config.forbidden.words
            else None
        ),
    }
