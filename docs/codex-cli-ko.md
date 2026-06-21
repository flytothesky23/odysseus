# Odysseus와 Codex CLI 사용 방향

이 문서는 한국어 fork에서 Codex 관련 선택지를 구분하기 위한 운영 메모다. 실제 토큰, API 키, OAuth 값은 이 문서나 Git에 남기지 않는다.

## 결론

현재 Odysseus에서 바로 지원되는 Codex 흐름은 두 가지다.

| 목적 | 현재 가능 여부 | 설명 |
|---|---:|---|
| Codex CLI가 Odysseus의 데이터와 도구를 사용 | 가능 | `Settings > Integrations > Codex Agent`에서 scoped token을 만들고 Codex plugin bundle을 설치한다. |
| Odysseus가 ChatGPT/Codex backend를 모델 공급자로 사용 | 가능 | `ChatGPT Subscription` provider를 사용한다. 이 fork는 기존 Codex CLI 로그인도 가져올 수 있다. |
| Odysseus의 Add Models 화면에 Codex CLI path를 넣어 LLM처럼 사용 | 직접 실행 방식은 아님 | Codex CLI는 OpenAI-compatible HTTP model endpoint가 아니다. 대신 Codex CLI의 ChatGPT 로그인 토큰을 provider로 가져온다. |

## 화면별 의미

`Settings > Add Models`의 `Add Local Models`와 `Add API Models`는 모델 엔드포인트를 추가하는 화면이다.

- Local: Ollama, llama.cpp, vLLM처럼 HTTP endpoint를 여는 로컬 모델 서버
- API: OpenAI, Anthropic, DeepSeek, OpenRouter 등 API endpoint
- ChatGPT Subscription: OpenAI 계정 device flow/OAuth 기반 Codex backend provider

따라서 `codex` 실행 파일 경로나 Obsidian Codexian의 `codexCliPath`를 이 화면의 endpoint URL로 넣는 방식은 맞지 않다. 이 fork에서는 `Import Codex CLI login` 버튼으로 기존 Codex CLI 로그인 파일을 읽어 ChatGPT Subscription provider를 만든다.

## Codex CLI가 Odysseus를 쓰는 흐름

원본 기준 문서는 `integrations/codex/README.md`다.

1. Odysseus에 로그인한다.
2. `Settings > Integrations`에서 `Codex Agent`를 추가한다.
3. 필요한 scope만 켠다. 예: todos, memory, documents, cookbook 등.
4. 생성된 setup command를 로컬 터미널에서 실행한다.
5. Codex에서 `odysseus@personal` plugin을 설치한다.
6. 아래 capability 확인 명령으로 연결을 검증한다.

```bash
python3 ~/plugins/odysseus/scripts/odysseus_api.py capabilities
```

이 방식은 “Codex CLI 안에서 Odysseus의 todo, memory, documents, email draft, calendar, cookbook 도구를 사용”하는 구조다.

## Odysseus가 Codex backend를 모델로 쓰는 흐름

Odysseus에는 `ChatGPT Subscription` provider가 있다. 구현 위치는 아래 파일이다.

- `src/chatgpt_subscription.py`
- `routes/chatgpt_subscription_routes.py`
- `static/js/providerDeviceFlow.js`
- `static/js/slashCommands.js`

이 provider는 API key 입력 방식이 아니라 OpenAI 계정 device flow/OAuth로 연결하고, `https://chatgpt.com/backend-api/codex` 모델 목록을 가져온다. Slash command에는 `/setup chatgpt-subscription`이 있고 alias로 `codex`가 등록되어 있다.

이 흐름은 “Codex CLI path”를 실행하는 것이 아니라, Odysseus 서버가 ChatGPT/Codex backend용 bearer token을 갱신해 모델 요청을 보내는 구조다.

## 기존 Codex CLI 로그인 가져오기

한국어 fork에는 API 키 없이 기존 Codex CLI 로그인을 가져오는 버튼을 추가했다.

1. 먼저 로컬 터미널에서 Codex CLI가 로그인되어 있어야 한다. 일반적으로 `codex login` 후 `~/.codex/auth.json`에 ChatGPT 로그인 세션이 생긴다.
2. Odysseus에서 `Settings > Add Models > Add API Models`를 연다.
3. `Import Codex CLI login`을 누른다.
4. Odysseus가 `ChatGPT Subscription - Codex CLI` endpoint를 만들고 기본/유틸리티/리서치/태스크 모델을 설정한다.

등록 후 기본 모델은 긴 작업에 `gpt-5.5`, 가벼운 유틸리티와 백그라운드 태스크에는 `gpt-5.3-codex-spark`를 우선 사용한다. 사용자는 API 키를 붙여넣지 않아도 되지만, Codex CLI의 ChatGPT 로그인 권한과 upstream 사용 제한은 그대로 적용된다.

## 모델별 추론 정도 선택

한국어 fork는 채팅 입력창 모델 선택 옆에 `추론` 드롭다운을 추가했다. 값은 모델별로 브라우저 localStorage에 저장된다.

| UI 값 | 전송 값 | 설명 |
|---|---|---|
| 자동 | 없음 | 기존 동작 유지. 지원하지 않는 모델이나 로컬 엔드포인트에 불필요한 파라미터를 보내지 않는다. |
| 낮음 | `low` | 빠른 응답과 낮은 reasoning token 사용을 우선한다. |
| 보통 | `medium` | 균형형 추론 정도. |
| 높음 | `high` | 더 복잡한 계획/분석 작업에 사용한다. |
| 매우 높음 | `xhigh` | 지원 모델에서만 사용한다. 지원하지 않으면 upstream 오류가 날 수 있다. |

Codex/ChatGPT Subscription provider는 Responses API 스타일 payload를 쓰므로 `reasoning: {"effort": "<값>"}`로 보낸다. 일반 OpenAI 호환 Chat Completions 경로는 로컬/self-hosted 엔드포인트를 제외하고 `reasoning_effort`를 보낸다. 이 분리는 로컬 서버가 모르는 top-level 필드를 거부하는 문제를 줄이기 위한 것이다.

구현 위치:

- `src/chatgpt_subscription.py`: Codex CLI `auth.json` 탐지와 토큰 파서
- `routes/chatgpt_subscription_routes.py`: `/api/chatgpt-subscription/codex-cli/status`, `/api/chatgpt-subscription/codex-cli/import`
- `src/llm_core.py`: Codex Responses payload의 `reasoning.effort`, OpenAI 호환 payload의 `reasoning_effort`
- `src/agent_loop.py`, `routes/chat_routes.py`: Chat/Agent 요청의 effort 전달
- `static/js/admin.js`: 설정 UI 버튼과 상태 표시
- `static/js/modelPicker.js`, `static/js/chat.js`: 모델별 effort 저장과 전송
- `static/js/ko-locale.js`: 한국어 overlay 문자열

검증 명령:

```bash
node --check static/js/modelPicker.js static/js/chat.js static/js/ko-locale.js
./venv/bin/python -m compileall src/llm_core.py src/request_models.py src/agent_loop.py routes/chat_routes.py
ODYSSEUS_E2E_URL=http://127.0.0.1:7860 npm run e2e:ko
```

## Codex CLI path를 직접 쓰고 싶을 때 필요한 구현

Obsidian `flytothesky-ops-forge`의 Codexian 설정은 `codexCliPath`를 로컬 프로필에 저장한다. 이것은 로컬 CLI 실행 경로이므로 Odysseus가 기대하는 HTTP model endpoint와 타입이 다르다.

Odysseus에서 Codex CLI path를 LLM처럼 사용하려면 다음 중 하나가 필요하다.

| 방식 | 장점 | 리스크 |
|---|---|---|
| OpenAI-compatible local adapter | 기존 Add Local Models 화면에 `http://127.0.0.1:<port>/v1`로 붙일 수 있음 | CLI 입출력, 세션, streaming, tool call semantics를 HTTP API로 맞춰야 함 |
| native Codex CLI provider | Odysseus 설정에 `codexCliPath`, model, reasoning을 직접 노출 가능 | backend provider 구현과 UI 설정을 새로 만들어야 함 |
| Codex CLI 로그인 import | API 키 없이 현재 Codex CLI 로그인 재사용 | CLI 실행 경로가 아니라 ChatGPT Subscription provider를 통해 동작 |
| Codex Agent plugin 중심 운영 | 현재 upstream 구조와 맞고 보안 scope가 명확함 | Odysseus chat에서 Codex CLI를 모델로 선택하는 UX는 아님 |

현실적인 첫 단계는 `Codex CLI 로그인 import`와 `Codex Agent plugin 중심 운영`이다. 그 다음 필요성이 분명하면 local adapter 또는 native provider를 별도 브랜치에서 검증한다.

## 보안 기준

- `ODYSSEUS_API_TOKEN`은 scoped token이며 문서, 노트, commit에 기록하지 않는다.
- Codex Agent는 `/api/codex/*` endpoint만 사용한다.
- SSH, Docker, direct Python import, database query로 사용자 데이터에 우회 접근하지 않는다.
- 이메일 전송 같은 부작용 있는 scope는 기본적으로 draft 중심으로 제한한다.
