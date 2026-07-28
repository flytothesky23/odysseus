<p align="center">
  <img src="docs/odysseus-wordmark.png" alt="Odysseus" width="280">
</p>

<p align="center">
  채팅, 에이전트, 리서치, 문서, 이메일, 노트, 캘린더, 로컬 모델 워크플로를 한곳에서 다루는 self-hosted AI workspace.
</p>

<p align="center">
  <a href="#빠른-시작">빠른 시작</a> ·
  <a href="docs/setup.md">Setup Guide</a> ·
  <a href="docs/codex-cli-ko.md">Codex CLI 사용 방향</a> ·
  <a href="README.md">English</a>
</p>

---

## 빠른 시작

Docker가 가장 간단한 시작 방법입니다.

```bash
git clone https://github.com/flytothesky23/odysseus.git
cd odysseus
cp .env.example .env
docker compose up -d --build
```

컨테이너가 정상 상태가 되면 `http://localhost:7000`으로 접속합니다. 최초 관리자 비밀번호는 아래 로그에서 확인합니다.

```bash
docker compose logs odysseus
```

native 설치, GPU 설정, Windows/macOS 실행, HTTPS, 환경변수는 원본 [setup guide](docs/setup.md)를 기준으로 확인하세요.

## 무엇을 할 수 있나

- **Chat + Agents** - local/API model, tool, MCP, file, shell, skill, memory를 연결합니다.
- **Cookbook** - 하드웨어에 맞는 모델 추천, 다운로드, serving workflow를 제공합니다.
- **Deep Research** - 여러 단계의 웹 리서치, source reading, report 생성을 지원합니다.
- **Compare** - 모델 응답을 blind side-by-side 방식으로 비교하고 종합합니다.
- **Documents** - AI edit, suggestion, Markdown, HTML, CSV, syntax highlighting을 지원하는 writing-first editor입니다.
- **Email** - IMAP/SMTP inbox, triage, tag, summary, reminder, reply draft를 다룹니다.
- **Notes, Tasks + Calendar** - reminder, todo, scheduled agent task, CalDAV sync를 지원합니다.
- **Extras** - gallery/image editor, theme, upload, web search, preset, session, 2FA 등을 포함합니다.

## 한국어 사용자 메모

| 주제 | 메모 |
|---|---|
| 브랜치 | 원본 최신 개발 기준은 `upstream/dev`입니다. 한국어 통합은 별도 로컬 통합 브랜치에서 검증합니다. |
| macOS Apple Silicon | Docker는 Metal GPU를 직접 쓰지 못합니다. GPU 가속이 필요하면 native 실행 흐름을 확인하세요. |
| 포트 | Docker 기본 UI는 `http://localhost:7000`입니다. macOS launcher는 `http://127.0.0.1:7860`을 사용할 수 있습니다. |
| 보안 | auth를 켠 상태로 사용하고, public internet에 raw port를 직접 노출하지 마세요. |
| 민감정보 | `.env`, API key, OAuth token, session cookie, 개인 문서는 Git에 올리지 마세요. |

## Codex CLI 연동

Odysseus의 Codex 관련 기능은 두 방향을 구분해야 합니다. 자세한 정리는 [docs/codex-cli-ko.md](docs/codex-cli-ko.md)를 확인하세요.

| 목적 | 현재 상태 |
|---|---|
| Codex CLI가 Odysseus의 todo, memory, documents, email draft, calendar, cookbook 도구를 사용 | 원본의 Codex Agent plugin 흐름을 사용합니다. |
| Odysseus가 ChatGPT/Codex backend를 모델로 사용 | 한국어 fork 계약에서는 ChatGPT Subscription provider와 Codex CLI 로그인 가져오기를 보존 대상으로 둡니다. |
| Odysseus의 Add Models 화면에 Codex CLI path를 endpoint처럼 입력 | 직접 실행 방식은 아닙니다. Codex CLI는 HTTP endpoint가 아니므로 별도 provider 또는 adapter가 필요합니다. |

실제 token, API key, OAuth 값, session cookie는 README, issue, PR, Obsidian 노트에 남기지 마세요.

## 한국어 UI smoke

한국어 overlay와 핵심 UI 문구는 아래 명령으로 확인합니다.

```bash
ODYSSEUS_E2E_URL=http://127.0.0.1:7860 npm run e2e:ko
```

## 보안

Odysseus는 강력한 local tool을 포함한 self-hosted workspace입니다. auth를 유지하고, private data를 Git에 넣지 말고, model/service raw port를 공개망에 직접 노출하지 마세요. 자세한 내용은 [setup guide security notes](docs/setup.md#security-notes)를 확인하세요.

## 라이선스

AGPL-3.0-or-later 라이선스입니다. 자세한 내용은 [LICENSE](LICENSE)와 [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)를 확인하세요.

## 원문

이 한국어 문서는 한국어 사용자의 진입 장벽을 낮추기 위한 안내입니다. 최신 세부 내용은 원본 [README.md](README.md)와 [docs/setup.md](docs/setup.md)를 함께 확인하세요.
