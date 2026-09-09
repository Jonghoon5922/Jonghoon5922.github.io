# 개발 일지

[jonghoon5922.github.io](https://jonghoon5922.github.io/) — 만드는 것들의 기록.

이 저장소는 블로그이면서, 그 블로그를 운영하는 도구이기도 하다.

```
src/content/posts/   글          ← 산출물
src/content/projects/ 프로젝트 소개
ilji/                일지 MCP 서버 ← 기계
```

## 일지 (ilji)

등록한 프로젝트들의 git 기록과 설계 문서를 재료로 Claude 가 초안을 쓰고,
마스킹 검사를 통과하고 사람이 승인해야 글이 나가는 로컬 MCP 서버.

- **이 도구는 LLM 을 호출하지 않는다.** 글은 사용자의 Claude 가 쓰고, 도구는 재료·검사·게시만 한다.
- **자동 게시는 없다.** 게시는 사용자가 명시적으로 요청할 때만, 검사를 통과한 초안에 대해서만.
- **접근 범위는 등록한 폴더뿐이다.** 비공개로 등록한 프로젝트는 재료 수집 자체를 거부한다.

### 도구

| 묶음 | 도구 |
|---|---|
| 재료 | `list_projects` `get_changes` `get_diff` `list_docs` `read_doc` |
| 원고 | `save_draft` `update_post` |
| 관문 | `check` `approve` |
| 운영 | `publish` `list_posts` `deploy_status` `unpublish` |

### 쓰기

```bash
uv sync
uv run ilji init --blog .     # ~/.ilji/ilji.toml 생성
uv run ilji add <프로젝트 폴더>
uv run ilji status
uv run ilji serve             # MCP (stdio)
```

설정 파일에는 금지어 목록이 들어가므로 저장소가 아니라 `~/.ilji/` 에 둔다.

## 블로그

Astro. `main` 에 push 하면 Actions 가 빌드해 GitHub Pages 로 배포한다.

```bash
npm install
npm run dev
```
