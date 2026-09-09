---
name: 서재 (seojae)
order: 1
summary: 폴더에 문서를 꽂아두면 Claude가 찾아 읽는 로컬 RAG MCP 서버.
repo: https://github.com/Jonghoon5922/seojae
stack: [Python, FastMCP, BM25]
status: 운영 중
---

문서를 책장(collection)에 꽂아두면, Claude가 질문에 맞는 책장을 골라 검색한다.
BM25 기반 한국어 형태소 검색이라 임베딩 서버도, 외부 API도 필요 없다.
아직 분류하지 않은 문서는 인박스에 모였다가 정리 요청을 받으면 알맞은 책장으로 간다.

검색이 빗나갔을 때 그냥 빈손으로 돌아오지 않고, 색인에 없는 단어와 그 책장이 실제로
쓰는 어휘를 힌트로 돌려준다. 다시 검색하도록 유도하는 장치다.
