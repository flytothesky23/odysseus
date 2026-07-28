# Odysseus와 Codex CLI 사용 방향

이 문서는 한국어 fork에서 Codex 관련 선택지를 구분하기 위한 운영 메모다. 실제 토큰, API 키, OAuth 값, session cookie는 이 문서나 Git에 남기지 않는다.

## 결론

Odysseus에서 Codex를 다루는 방향은 두 가지로 나뉜다.

| 목적 | 설명 |
|---|---|
| Codex CLI가 Odysseus의 데이터와 도구를 사용 | `Settings > Integrations > Codex Agent`에서 scoped token을 만들고 Codex plugin bundle을 설치한다. |
| Odysseus가 ChatGPT/Codex backend를 모델 공급자로 사용 | 한국어 fork 계약은 ChatGPT Subscription provider와 기존 Codex CLI 로그인 가져오기를 보존 대상으로 둔다. |
| Add Models 화면에 Codex CLI path를 넣어 LLM처럼 사용 | Codex CLI는 OpenAI-compatible HTTP model endpoint가 아니다. 직접 경로 입력 대신 provider 또는 local adapter가 필요하다. |

## 화면별 의미

`Settings > Add Models`의 `Add Local Models`와 `Add API Models`는 모델 엔드포인트를 추가하는 화면이다.

- Local: Ollama, llama.cpp, vLLM처럼 HTTP endpoint를 여는 로컬 모델 서버
- API: OpenAI, Anthropic, DeepSeek, OpenRouter 등 API endpoint
- ChatGPT Subscription: OpenAI 계정 device flow/OAuth 기반 Codex backend provider

따라서 `codex` 실행 파일 경로나 Obsidian Codexian의 `codexCliPath`를 endpoint URL로 넣는 방식은 맞지 않다.

## Codex CLI가 Odysseus를 쓰는 흐름

원본 기준 문서는 `integrations/codex/README.md`다.

1. Odysseus에 로그인한다.
2. `Settings > Integrations`에서 `Codex Agent`를 추가한다.
3. 필요한 scope만 켠다. 예: todos, memory, documents, cookbook 등.
4. 생성된 setup command를 로컬 터미널에서 실행한다.
5. Codex에서 `odysseus@personal` plugin을 설치한다.
6. capability 확인 명령으로 연결을 검증한다.

이 방식은 "Codex CLI 안에서 Odysseus의 todo, memory, documents, email draft, calendar, cookbook 도구를 사용"하는 구조다.

## Odysseus가 Codex backend를 모델로 쓰는 흐름

한국어 fork의 안정 기준은 API key 없이 기존 Codex CLI 로그인을 가져오는 운영 방식을 보존 대상으로 둔다. 이 통합 브랜치에서는 upstream의 provider 구조, owner scope, path confinement, SSRF 방어를 우선하고, 필요한 backend 이식은 별도 코드 변경으로 제한 적용한다.

## 모델별 추론 정도 선택

한국어 fork 계약은 채팅 또는 리서치 실행에서 `자동`, `낮음`, `보통`, `높음`, `매우 높음` reasoning effort를 보존 대상으로 둔다.

| UI 값 | 전송 값 | 설명 |
|---|---|---|
| 자동 | 없음 | provider 기본 동작을 유지한다. |
| 낮음 | `low` | 빠른 응답과 낮은 reasoning token 사용을 우선한다. |
| 보통 | `medium` | 균형형 추론 정도. |
| 높음 | `high` | 더 복잡한 계획/분석 작업에 사용한다. |
| 매우 높음 | `xhigh` | 지원 모델에서만 사용한다. |

## 보안 기준

- `ODYSSEUS_API_TOKEN`, API key, OAuth token, session cookie는 문서, 노트, commit에 기록하지 않는다.
- Codex Agent는 `/api/codex/*` endpoint와 scoped permission을 기준으로 사용한다.
- SSH, Docker, direct Python import, database query로 사용자 데이터에 우회 접근하지 않는다.
- 이메일 전송 같은 부작용 있는 scope는 기본적으로 draft 중심으로 제한한다.
