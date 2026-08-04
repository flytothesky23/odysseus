# Korean Semantic Bridge + Context-Preserving Agentic Web Search + v0.1.13-ko Release Plan

## 단일 최종 목표

Odysseus 일반 채팅의 웹검색을 `현재 입력 한 줄 -> 단발 검색 -> 결과 통째 주입`
경로에서 `전체 대화문맥 -> 검색계획 -> 실제 검색/필요 URL 재조회 -> 근거 대조 ->
인라인 인용 답변 -> 같은 근거 후속질문` 경로로 전환한다. 검색을 실행하지 않은 채
실행하겠다고 답하거나, 읽지 않은 검색결과를 출처로 노출하거나, 한국어 후속지시를
새 검색어로 오인하는 상태를 실패로 처리한다.

완료는 단위 테스트나 fake endpoint 통과가 아니다. 현재 단일 설치본의 기존 사용자
계정과 Codex OAuth 연결을 사용해 `http://127.0.0.1:7860`의 실제 headed browser에서
검색, 후속질문, 출처 열기, 실패/재시도, 취소와 기존 핵심 기능 회귀를 확인하고,
테스트 레코드를 제거한 뒤 로컬 `dev`, `origin/dev`, 새 불변 tag/release가 같은
커밋을 가리킬 때만 달성된다.

이 릴리스의 `-ko`는 메뉴 번역을 뜻하지 않는다. 한국어 사용자가 주어·목적어를
생략하고 지시어·존대·후속지시를 사용하는 실제 대화에서도 의도, 검색 대상, 도구
범위, 이전 근거와 완료 상태가 유지되는 “한국어 의미 브리지”를 제공해야 한다.
영어 규칙 옆에 임시 한국어 정규식 몇 개를 덧붙이는 데서 끝내지 않고, 공통 언어
계약과 양언어 회귀 corpus로 Chat/Agent/Search 경계를 검증한다.

## 현재 확인된 결함과 가설

1. `use_web=true`인 일반 채팅이 `chat_processor.build_context_preface()`의 레거시
   사전검색을 실행한 뒤 같은 요청을 `stream_agent_loop()`에도 보내 검색 도구를 다시
   제공한다. 검색 근거의 출처와 질의가 이중화된다.
2. 레거시 사전검색의 질의 추출은 현재 사용자 메시지만 보고, 앞선 질문과 답변을 보지
   않는다. “그렇다면 이번에는 제대로 할 수 있을까요?” 같은 후속지시가 독립 검색어가
   된다.
3. route와 agent loop의 continuation/웹 intent 패턴이 영어 중심이다. 한국어 검색,
   확인, 재시도, 동일 근거 후속질문이 안정적으로 같은 작업을 잇지 못한다.
4. `comprehensive_web_search()`는 검색결과 전체를 UI source 목록으로 만든 뒤 상위
   일부 페이지만 fetch한다. 읽지 못한 URL도 사용 가능한 근거처럼 보일 수 있다.
5. 검색 도구 설명이 `단일 quick fact`에 지나치게 고정되어, 비교·검증 질문에서도
   한 번 검색 후 방법론만 설명하거나 충분한 교차검증 없이 종료할 수 있다.
6. 일반 intent-without-action guard는 영어 약속 문구 중심이고 “검색해 보겠습니다”와
   실제 성공한 검색 호출 사이의 완료 계약이 없다.
7. `src/action_intents.py`, `src/agent_loop.py`, `routes/chat_routes.py`,
   `routes/chat_helpers.py`의 low-signal/continuation/domain routing과 여러 system prompt가
   영어 어순과 영어 동사에 의존한다. UI만 한국어여도 내부 의미 전달은 영어판과
   동등하지 않다.

## 변경하지 않을 경계

- 웹검색은 매 turn 명시적 opt-in이다. 토글 off와 명시적 false는 항상 fail-closed다.
- 자동 웹검색 turn에서는 `web_search`와 `web_fetch` 외의 개인 데이터, shell, 파일,
  Documents, Notes, 메일, 캘린더, 일반 MCP 도구를 열지 않는다.
- Contract Review의 선택 근거/법률 전용 정책과 Deep Research의 별도 job 흐름은
  유지한다.
- Compare mode의 공유 사전검색 계약은 별도로 보존하고 회귀 테스트한다.
- 검색어 전문, 질문 전문, 페이지 본문, OAuth/API credential을 로그·Git·운영노트에
  남기지 않는다. 진단에는 hash, 건수, 상태, latency만 남긴다.
- 테스트는 비식별 데이터만 사용하며 실제 이메일, 사용자 Vault, 기억, 기존 Documents,
  유료 API key 호출을 변경하지 않는다.
- 기존 `v0.1.9-ko`부터 `v0.1.12-ko`까지의 tag는 이동·삭제하지 않는다.

## 설계 계약

### 0. 한국어 의미 브리지

- 공통 모듈에서 한국어 입력의 정규화, 명시적 도구 의도, 최신성, 승인/재시도,
  지시어 기반 continuation, casual low-signal, 주제 전환을 판별한다.
- `그것/그거/위 내용/방금 근거/앞서 말한 것/그렇다면/그러면/이번에는`처럼 이전
  turn이 있어야 해석되는 표현은 bounded recent context와 결합한다.
- `검색해줘`, `찾아봐`, `확인해 주세요`, `최신`, `현재`, `오늘`, `이번 주`의
  검색/최신성 의도와 `저장해줘`, `열어줘`, `다시 해줘`, `취소해줘`의 실행 의도를
  설명 질문과 구분한다.
- 검색 질의 재작성 시 한국어 고유명사, 법령명, 숫자, 날짜, 제품명, 인용구를 보존하고
  사용자의 후속지시 문장 자체를 검색어로 사용하지 않는다.
- 모델 prompt에는 한국어 대화에서 생략된 목적어를 임의로 만들지 말고 recent context로
  해소하며, 불명확하면 도구를 오호출하지 않도록 하는 계약을 명시한다.
- 한국어 지원 추가로 기존 영어, Polish 등 현재 지원 흐름이 회귀하지 않도록 같은 의미의
  bilingual parameterized tests를 둔다.

### 1. 단일 검색 실행 경로

- 일반 Chat + 웹검색 opt-in은 내부적으로 agent loop를 사용하되 레거시
  `build_context_preface(use_web=True)`를 호출하지 않는다.
- Compare mode만 기존 shared prefetch를 유지한다.
- UI의 Chat/Agent 선택 의미는 유지하고, 조용한 웹 실행 때문에 세션 자체가 사용자가
  선택하지 않은 agent mode로 영구 변경되지 않도록 실행 mode와 표시 mode를 분리한다.

### 2. 문맥 기반 검색계획

- 최신 사용자 입력과 bounded recent history를 함께 사용한다.
- 한국어 명시 검색/최신성 표현과 `네`, `그렇게 해줘`, `다시 검색해줘`, `이번에는
  실제로 확인해줘`, `위 질문을 근거로` 같은 continuation을 지원한다.
- casual greeting과 주제 전환은 오래된 웹 문맥을 상속하지 않는다.
- 검색계획은 단순 사실은 1회, 비교·최신동향·검증은 복수 질의와 출처 대조를 허용하되
  동일 질의 반복과 무한 loop를 제한한다.

### 3. 근거 상태와 인용

- source 상태를 `discovered`, `fetched`, `usable`, `cited`로 구분한다.
- UI에 정상 근거로 노출하는 목록은 fetch에 성공하고 읽을 수 있는 내용이 있는 source로
  한정한다. 검색 snippet만 사용한 경우 그 사실을 별도로 표시한다.
- 최종 답변의 인용 annotation과 source URL/title을 일관되게 저장한다.
- fetch 실패, 빈 본문, timeout, 429/provider/runtime 오류는 정상 근거로 위장하지 않고
  구분된 오류로 모델과 UI에 전달한다.

### 4. 완료 감독

- 웹검색이 필요한 turn은 성공한 `web_search` 또는 `web_fetch` 호출 전에는 완료할 수
  없다.
- “검색하겠습니다/확인해 보겠습니다” 같은 한국어·영어 실행 약속 후 tool call이 없으면
  제한된 재시도를 강제한다.
- 재시도 후에도 실행하지 못하면 검색하지 않았다고 명시하고 종료한다.
- 결과가 부족하면 부족한 근거와 실패 원인을 답변에 포함하고, 임의 사실이나 순위를
  만들지 않는다.

## TDD 작업 순서

### Task 0: 한국어 의미 회귀 corpus와 공통 계약

Files:
- Add: `src/korean_semantics.py` 또는 기존 공통 intent 모듈에 동등한 경계
- Add: `tests/fixtures/korean_semantic_turns.json`
- Add: `tests/test_korean_semantic_bridge.py`
- Modify: `src/action_intents.py`
- Modify: `src/agent_loop.py`
- Modify: `routes/chat_routes.py`
- Modify: `routes/chat_helpers.py`

Corpus:
- 독립 요청: 검색/최신성/뉴스/가격/법률조회/문서열기/저장/취소/재시도
- 후속 요청: `그렇게 해줘`, `그 근거만`, `방금 것과 비교해줘`, `이번에는 실제로
  검색해줘`, `그렇다면 잘할 수 있을까요?`
- 설명 질문: `웹검색은 어떻게 사용하나요?`, `저장 기능이 무엇인가요?`
- low signal/주제 전환: 인사, 감사, 사과, 새 주제로 넘어가는 완전한 질문
- 형태 변형: 해요체/하십시오체/반말, 띄어쓰기 변형, 한영 혼용, 조사 생략

Steps:
1. 현재 영어 중심 구현에서 잘못 분류되는 corpus를 RED로 기록한다.
2. normalization 결과에는 원문을 보존하고 보안/identity 판단에는 LLM 추론을 쓰지 않는다.
3. route와 agent loop가 같은 helper 결과를 소비하도록 중복 정규식을 제거한다.
4. intent, continuation, retrieval query, allowed tool family가 기대값과 일치하게 만든다.
5. Chat history trim/compaction 후에도 마지막 관련 한국어 목적어가 유지되는 회귀를
   추가한다.

### Task 1: 경로 분리 회귀를 먼저 RED로 고정

Files:
- Modify: `tests/test_chat_route_tool_policy.py`
- Modify: `tests/test_chat_helpers.py`
- Add: `tests/test_agentic_web_search_routing.py`
- Modify: `routes/chat_routes.py`
- Modify: `routes/chat_helpers.py`

Steps:
1. 일반 Chat + `use_web=true`가 preface web search를 0회 호출하고 agent loop만 호출하는
   실패 테스트를 추가한다.
2. Compare mode가 기존 prefetch를 계속 호출하는 테스트를 추가한다.
3. 표시 session mode와 내부 agentic execution mode가 분리되는 테스트를 추가한다.
4. Contract Review와 explicit false가 모든 일반 웹/MCP 도구를 차단하는 테스트를 추가한다.
5. 최소 route 변경으로 GREEN을 만든다.

### Task 2: 한국어 검색·후속지시 문맥 계승

Files:
- Modify: `src/action_intents.py`
- Modify: `src/agent_loop.py`
- Modify: `routes/chat_routes.py`
- Modify: `tests/test_action_intents.py`
- Add: `tests/test_agentic_web_search_context.py`

Steps:
1. 한국어 명시 검색, 최신 뉴스/가격/현황, 재검색, 승인/계속 후속문 테스트를 RED로 만든다.
2. casual/주제전환이 stale 웹 문맥을 상속하지 않는 negative test를 추가한다.
3. bounded recent context로 retrieval query를 만들고 privacy-safe trace만 남긴다.
4. 같은 주제 follow-up과 delta retrieval이 기존 근거를 재사용하되 필요한 새 검색만
   추가하는 테스트를 GREEN으로 만든다.

### Task 3: 읽은 근거만 노출하고 검색 실패를 구조화

Files:
- Modify: `services/search/core.py`
- Modify: `src/agent_tools/web_tools.py`
- Modify: `tests/test_search_core.py` 또는 기존 search test 모듈
- Add: `tests/test_web_search_evidence_contract.py`

Steps:
1. fetch하지 않았거나 fetch 실패한 결과가 verified source 목록에 포함되지 않는 RED
   테스트를 만든다.
2. 성공/빈 결과/timeout/429/provider/runtime 상태를 서로 다른 결과로 검증한다.
3. 검색결과 순위와 source index가 fetch completion 순서에 영향받지 않는지 검증한다.
4. 읽을 수 있는 fetched source와 snippet-only candidate를 분리한 구조를 반환한다.
5. 기존 UI source renderer와 저장 metadata가 새 구조를 안전하게 소비하도록 호환성을
   유지한다.

### Task 4: agent prompt와 완료 gate

Files:
- Modify: `src/agent_loop.py`
- Modify: `src/tool_index.py`
- Modify: `tests/test_agent_loop.py`
- Add: `tests/test_agentic_web_search_completion.py`

Steps:
1. 복수 출처 비교 질의가 검색 없이 방법만 설명하면 실패하는 테스트를 만든다.
2. 한국어/영어 future-tense promise 뒤 tool call이 없으면 nudge하는 테스트를 추가한다.
3. 성공한 웹 tool call, usable source, 최종 grounded answer의 완료 조건을 구현한다.
4. 동일 호출 반복, round/budget 초과, 취소가 명확한 종료 이벤트를 내는지 검증한다.
5. 개인/파일/MCP 도구가 자동 웹 turn에서 forced/retrieved되지 않는지 검증한다.

### Task 5: UI 진행·오류·인용 회귀

Files:
- Modify as needed: `static/js/chat.js`
- Modify as needed: existing web source/tool event renderers
- Add/modify: browser-facing JS tests and `scripts/qa/` scenario

Steps:
1. 검색 계획/검색 중/fetch/교차검증/재시도/실패/취소 상태가 실제 event에서 UI로
   연결되는지 확인한다.
2. 최종 source panel에는 usable source만 표시하고 링크가 열린다.
3. 답변이 source 번호/링크와 불일치하지 않는지 검사한다.
4. 새 오류와 failed request, console error, 중복 검색 카드가 0인지 검사한다.

### Task 6: 회귀·보안·성능 검증 폐쇄 루프

Commands/gates:
- 변경 Python: `venv/bin/python -m py_compile ...`
- 변경 JavaScript: `node --check ...`
- targeted pytest: 새 테스트와 chat/agent/search/tool-policy 테스트
- 기존 핵심: Chat, Deep Research, Contract Review, Vault Explorer, Kordoc, Korean Law,
  renderer gallery, session/model/reasoning/context budget/compaction/metrics/MCP manager
- 전체: `venv/bin/python -m pytest`
- 정적 검사: repository의 기존 lint/static commands
- diff: `git diff --check`

Acceptance:
- 최종 passed 수는 baseline `4986 passed / 3 skipped`에서 추가 테스트만큼 증가한다.
- 기존 테스트 감소는 허용하지 않는다.
- 질문/검색어/본문/credential의 새 plaintext 로그가 없다.
- 실제 token usage가 없으면 estimate로 명시하며 actual로 표시하지 않는다.

### Task 7: 실제 7860 Codex OAuth headed-browser E2E

환경:
- repo/cwd: 현재 단일 설치 checkout (`$REPO`)
- URL: `http://127.0.0.1:7860`
- 사용자 설치본의 기존 계정과 Codex OAuth endpoint/model
- 비식별, 고유 prefix의 임시 chat/session 데이터

Journey:
1. 기존 계정 로그인 및 기존 Documents/채팅/메모/Deep Research count를 값 노출 없이
   확인한다.
2. Chat 모드에서 웹검색을 켜고 시점이 명확한 실제 질의를 보낸다.
3. 실제 stream에서 search/fetch 진행, usable source, 인라인 인용, source 링크를 확인한다.
4. “그렇다면 방금 근거에서 무엇이 달라졌나요?”와 한국어 재검색 지시로 동일 근거
   재사용/delta retrieval을 확인한다.
5. 검색 취소 후 상태, 재시도 후 정상 완료를 확인한다.
6. provider/runtime 실패를 안전하게 재현할 수 있는 비파괴 경로가 있으면 실패 UI를
   확인하고, 없으면 deterministic E2E 증거와 실제 환경 `NOT TESTED`를 분리한다.
7. 일반 Chat, Deep Research 진입, Contract Review/Vault Explorer, renderer gallery,
   Documents 저장 버튼이 회귀하지 않았는지 확인한다.
8. console error, failed request, stale/duplicate source, 실행 약속만 한 답변이 0인지
   확인한다.
9. 생성한 chat/session/document/note/test fixture를 삭제하고 baseline 개인화 count를
   다시 확인한다.

Fake model/provider E2E는 결정론적 회귀 증거로만 기록하며 이 gate를 대체하지 않는다.
실제 외부 provider가 실패하면 성공으로 보고하지 않고 원인과 `FAILED` 또는
`NOT TESTED`를 명시한다.

### Task 8: 릴리스·운영 정렬

1. feature branch에서 모든 gate를 다시 통과한다.
2. Lore Commit Protocol 형식으로 커밋한다.
3. `dev`에 `--ff-only` 반영하고 `origin/dev`에 push한다.
4. 로컬 HEAD와 `origin/dev`가 동일한지 확인한다.
5. 새 안정 tag `v0.1.13-ko`와 GitHub Release를 같은 최종 commit에 생성한다.
6. 기존 tag가 이동하지 않았고 새 release source archive가 내려받아지는지 확인한다.
7. 바탕화면 실행기의 승인 commit을 새 `dev` commit으로 갱신한다.
8. `.env`, `data/app.db`, `data/.app_key`, memory/vector/upload registry의 KST 백업을
   생성하고 pair/integrity/decryption/count를 값 노출 없이 재검증한다.
9. Second Brain의 운영 인덱스/현재 상태/출력 계약/리스크/새 세션 기록/active handoff를
   실제 수치로 갱신한다.
10. 7860을 현재 checkout에서 재기동하고 listener cwd, health, 로그인 E2E를 재확인한다.
11. feature branch, 임시 fixture/process/artifact를 정리한다.

최종 상태:
- local branch: `dev` 하나
- registered worktree: 기본 설치본 하나
- git status: clean
- local HEAD = `origin/dev` = `v0.1.13-ko` = GitHub Release target
- `.codex/worktrees` Odysseus 잔여: 0
- 기존 `v0.1.9-ko`~`v0.1.12-ko`: 불변
- 7860 listener cwd: 현재 단일 설치 checkout (`$REPO`)

## 보고 계약

최종 보고에는 다음 실제 증거를 포함한다.

- 실행 URL, branch, commit, tag/release, origin 일치 여부
- 실제 7860 Codex OAuth browser journey별 PASS/FAIL/NOT TESTED
- deterministic tests와 실제 외부 통합 증거의 명확한 분리
- 전체 pytest passed/skipped/warnings/time과 baseline 대비 증가분
- syntax/lint/static/diff-check 결과
- 검색 품질 결함별 원인과 수정 파일
- 개인화 보존 count, decrypt failure, DB/vector integrity
- Git branch/worktree/status, 7860 cwd/health
- 테스트 데이터와 임시 process 정리 결과
- 변경한 Second Brain 기록과 KST 완료시각
- 기존 tag 불변 및 새 release 생성 결과
