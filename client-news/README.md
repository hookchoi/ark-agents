# Client News — 주간 큐레이션 에이전트

블록체인 생태계별 주간 뉴스를 자동 수집 → 큐레이션 → **Notion 페이지**로 생성하는 Claude Code 에이전트입니다.

## 사용법

### 프리셋 모드 (등록된 프로젝트)

```bash
cd client-news
/weekly-curation sui
```

`curation-presets.yaml`에 등록된 프리셋으로 자동 실행됩니다.

### 애드혹 모드 (아무 프로젝트나)

```bash
cd client-news
/weekly-curation
```

에이전트가 순서대로 질문합니다:
1. 프로젝트 이름 (예: Aptos, Solana)
2. 소스 붙여넣기 — 자동 감지:
   - `@handle` → 트위터
   - `/rss/` 또는 `/feed/` 포함 URL → RSS 피드
   - 그 외 URL → 웹페이지 직접 수집
3. Notion 상위 페이지 URL
4. 타겟 독자 (기본: 한국 리테일 투자자)

### 입력 예시

```
@AptosLabs @AptosFoundation
https://medium.com/feed/aptoslabs
https://aptosfoundation.org/blog
```

## 사전 설정

### 1. Notion MCP 연결

Claude Code에 Notion MCP 서버를 추가해야 합니다:

```bash
claude mcp add notion \
  --type stdio \
  npx -y @notionhq/notion-mcp-server
```

환경변수에 Notion API 토큰 설정:
- [Notion Integration 생성](https://www.notion.so/my-integrations) → Internal Integration → 토큰 복사
- `.claude.json`에 토큰 추가:
  ```json
  "notion": {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@notionhq/notion-mcp-server"],
    "env": { "NOTION_TOKEN": "your_token_here" }
  }
  ```

### 2. Notion 페이지 연결

큐레이션을 생성할 상위 Notion 페이지에 Integration을 연결합니다:
- Notion 페이지 열기 → 우측 상단 `···` → **연결(Connections)** → Integration 추가

## 출력 예시

Notion 페이지에 아래 구조로 생성됩니다:

```
📊 2026-03-13 주간 큐레이션
├── 기간 · 소스 요약
├── ⭐⭐⭐⭐⭐ 추천 포스팅 1
│   ├── 📰 제목 (bold)
│   ├── 핵심 포인트 (bullet)
│   ├── 💡 투자자 시사점
│   └── 🔗 참고 링크
├── ⭐⭐⭐⭐ 추천 포스팅 2
│   └── ...
├── 📋 선택적 포스팅
└── 🏆 추천 포스팅 순서
```

## 프리셋 추가

`curation-presets.yaml`에 새 프리셋을 추가하면 됩니다:

```yaml
presets:
  aptos:
    name: "Aptos Ecosystem"
    rss_feeds:
      - url: "https://medium.com/feed/aptoslabs"
        label: "Aptos Labs 블로그"
    twitter_handles:
      - Aptos
    audience: "한국 리테일 투자자"
    focus: "투자 관련성 중심 큐레이션"
    days: 7
    notion_parent_page_id: "your-notion-page-id"
    max_recommendations: 5
```

## 파일 구조

```
client-news/
├── .claude/agents/
│   └── weekly-curation.md    # 에이전트 정의
├── curation-presets.yaml      # 프리셋 설정
└── README.md
```
