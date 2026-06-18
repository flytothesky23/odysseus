<p align="center">
  <img src="docs/odysseus-wordmark.png" alt="Odysseus" width="280">
</p>

<p align="center">
  채팅, 에이전트, 리서치, 문서, 이메일, 노트, 캘린더, 로컬 모델 워크플로를 한곳에서 다루는 self-hosted AI workspace.
</p>

<p align="center">
  <a href="#빠른-시작">빠른 시작</a> ·
  <a href="docs/setup.md">Setup Guide</a> ·
  <a href="integrations/codex/README.md">Codex 연동</a> ·
  <a href="README.md">English</a>
</p>

<p align="center">
  <img src="docs/odysseus.jpg" alt="Odysseus interface">
</p>

---

## 빠른 시작

> `dev`는 기본 브랜치이며 가장 최신 변경이 먼저 들어옵니다. 더 안정적으로 정리된 브랜치를 원하면 [`main`](https://github.com/pewdiepie-archdaemon/odysseus/tree/main)을 사용하세요.

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
| 브랜치 | 기본 브랜치는 `dev`입니다. 안정성을 우선하면 clone 후 `git checkout main`을 검토하세요. |
| macOS Apple Silicon | Docker는 Metal GPU를 직접 쓰지 못합니다. GPU 가속이 필요하면 native 실행 흐름을 확인하세요. |
| 포트 | Docker 기본 UI는 `http://localhost:7000`입니다. macOS launcher는 `http://127.0.0.1:7860`을 사용할 수 있습니다. |
| 보안 | auth를 켠 상태로 사용하고, public internet에 raw port를 직접 노출하지 마세요. |
| 민감정보 | `.env`, API key, OAuth token, 개인 문서는 Git에 올리지 마세요. |

## Codex CLI 연동

Odysseus는 Codex plugin/skill bundle을 제공합니다. 기준 문서는 [integrations/codex/README.md](integrations/codex/README.md)입니다.

기본 흐름은 다음과 같습니다.

1. Odysseus `Settings > Integrations`에서 Codex Agent를 추가합니다.
2. 생성된 token과 setup command를 로컬 터미널에서만 사용합니다.
3. Codex가 사용할 tool 권한을 Odysseus Settings에서 제한합니다.
4. `codex plugin add odysseus@personal`로 plugin을 설치합니다.
5. `python3 ~/plugins/odysseus/scripts/odysseus_api.py capabilities`로 연결을 확인합니다.

실제 token은 README, issue, PR, Obsidian 노트에 남기지 마세요. Codex 연동은 `/api/codex/*` endpoint를 기준으로 사용해야 하며, SSH, Docker, direct Python import, database query로 사용자 데이터에 우회 접근하면 안 됩니다.

## 기여

원본 프로젝트는 작은 단위의 검증 가능한 PR을 선호합니다. PR 대상 브랜치는 `main`이 아니라 `dev`입니다.

변경 전 확인할 문서:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [ROADMAP.md](ROADMAP.md)
- [SECURITY.md](SECURITY.md)

UI 변경은 실제 앱에서 확인하고 screenshot 또는 짧은 recording을 첨부해야 합니다. 자동화 에이전트로 큰 변경을 만들 때는 PR보다 먼저 issue로 문제와 접근 방식을 설명하는 흐름이 권장됩니다.

## 보안

Odysseus는 강력한 local tool을 포함한 self-hosted workspace입니다. auth를 유지하고, private data를 Git에 넣지 말고, model/service raw port를 공개망에 직접 노출하지 마세요. 자세한 내용은 [setup guide security notes](docs/setup.md#security-notes)를 확인하세요.

## 라이선스

AGPL-3.0-or-later 라이선스입니다. 자세한 내용은 [LICENSE](LICENSE)와 [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)를 확인하세요.

## 원문

이 한국어 문서는 한국어 사용자의 진입 장벽을 낮추기 위한 안내입니다. 최신 세부 내용은 원본 [README.md](README.md)와 [docs/setup.md](docs/setup.md)를 함께 확인하세요.
