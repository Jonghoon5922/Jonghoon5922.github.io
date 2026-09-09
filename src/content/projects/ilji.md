---
name: 일지 (ilji)
order: 4
summary: 이 블로그를 운영하는 MCP 서버. 프로젝트의 git 기록에서 글을 뽑는다.
stack: [Python, FastMCP, Astro]
status: 개발 중
---

이 블로그가 굴러가는 방식 자체다.

등록한 프로젝트들의 git 기록과 설계 문서를 재료로 Claude가 초안을 쓰고,
마스킹 검사를 통과하고 사람이 승인해야 글이 나간다. 자동 게시는 없다.

도구는 LLM을 호출하지 않는다. 판단은 사람과 Claude가, 읽기·검사·배포는 도구가 한다.
