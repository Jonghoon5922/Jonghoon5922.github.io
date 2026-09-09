---
name: 토큰빌 (tokenbill)
order: 2
summary: AI 코딩 도구가 쓴 토큰을 모아 집계하고 보여주는 사용량 뷰어.
repo: https://github.com/Jonghoon5922/tokenbill
stack: [Python, SQLite, Container]
status: 개발 중
---

여러 AI 코딩 도구에 흩어진 대화와 토큰 사용량을 한자리에 모은다.
Cursor는 로컬 SQLite(`state.vscdb`)에서 대화와 토큰을 직접 읽어온다.

뷰어에서 AI(소스)·프로젝트·기간으로 걸러 보고, 검색에도 같은 필터가 걸린다.
