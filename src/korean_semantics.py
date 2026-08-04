"""Deterministic Korean intent and continuation helpers.

These helpers are deliberately small and fail-closed.  They do not decide
authorization or filesystem/tool identity; callers still apply their normal
per-turn policy.  Their job is to keep Korean conversational meaning from
being discarded before the LLM/tool policy sees it.
"""

from __future__ import annotations

import re
from typing import Set


_HANGUL_RE = re.compile(r"[가-힣]")
_EXPLANATORY_RE = re.compile(
    r"(?:어떻게\s*(?:사용|쓰|작동|동작|하)|"
    r"(?:무엇|뭐|어떤\s*의미|무슨\s*뜻|기능이\s*뭔|사용법|방법을?\s*알려))"
)
_ACTION_END_RE = re.compile(
    r"(?:해|해줘|해주세요|해\s*주세요|해라|하자|할래|할까요|할\s*수\s*있|"
    r"봐|봐줘|보세요|보자|줘|주세요|진행|실행|확인|검증|검색|조회|찾아)"
)
_WEB_WORD_RE = re.compile(
    r"(?:웹|인터넷|온라인|검색|검색결과|출처|링크|사이트|뉴스|날씨|환율|시세|"
    r"주가|가격|최신|현재|오늘|이번\s*주|검색해|찾아봐|조회)"
)
_DIRECT_WEB_ACTION_RE = re.compile(
    r"(?:검색(?:해|하|해서|하여|해줘|해\s*줘|해\s*주세요|해주세요)|"
    r"찾아(?:봐|줘|주세요|보|서)|조회(?:해|하|해서|해주세요)|"
    r"교차\s*검증|사실\s*확인)"
)
_PERSONAL_SEARCH_TARGET_RE = re.compile(
    r"(?:메일|이메일|받은편지함|메모|노트|문서|Documents|파일|폴더|Vault|볼트|옵시디언|"
    r"채팅|대화|세션|대화\s*기록)"
)
_FRESH_SUBJECT_RE = re.compile(
    r"(?:뉴스|날씨|환율|시세|주가|가격|현황|상태|릴리스|버전|업데이트|사건|정책|법령)"
)
_FRESHNESS_RE = re.compile(r"(?:최신|현재|오늘|지금|이번\s*주|최근|실시간)")
_EXPLICIT_WEB_MEDIUM_RE = re.compile(r"(?:웹|인터넷|온라인|구글)")

_CASUAL_RE = re.compile(
    r"^\s*(?:안녕(?:하세요|하십니까)?|감사(?:합니다|해요)?|고마워(?:요)?|"
    r"미안(?:해|합니다|해요)?|죄송(?:합니다|해요)?|반가워(?:요)?|응|네|예)"
    r"\s*[.!?~ㅋㅎ]*\s*$"
)
_CONTINUATION_EXACT_RE = re.compile(
    r"^\s*(?:네|예|응|좋아|알겠어|알겠습니다|계속(?:해|해주세요)?|"
    r"진행(?:해|해주세요)?|다시(?:\s*해|\s*해주세요)?|재시도(?:해|해주세요)?|"
    r"그렇게(?:\s*해|\s*해주세요)?|그대로(?:\s*해|\s*해주세요)?)"
    r"\s*[.!?~]*\s*$"
)
_CONTEXT_REFERENCE_RE = re.compile(
    r"(?:그렇다면|그러면|그럼|그런데\s*이번에는|이번에는|방금|"
    r"위(?:의)?\s*(?:맥락|질문|내용|답변)|(?:마지막|직전|앞선|이전)\s*(?:질문|답변)|"
    r"앞서|이어서|그중|이\s*경우|그\s*부분|이를?|"
    r"그\s*(?:근거|결과|내용|질문|지시)|동일한?\s*근거|그대로|그렇게)"
)
_REPAIR_FOLLOWUP_RE = re.compile(
    r"(?:"
    r"(?:마지막|직전|앞선|이전)\s*(?:질문|답변)|"
    r"위(?:의)?\s*(?:맥락|질문|내용|답변)|"
    r"(?:방금|앞선|이전).{0,24}(?:요청|질문|내용).{0,48}"
    r"(?:다시\s*시도|재시도|다시\s*해)|"
    r"(?:맥락|답변|피드백).{0,28}(?:이상|아니|못|누락|놓쳤|끊)|"
    r"(?:질문).{0,20}(?:답|응답).{0,20}(?:아니|못|누락|놓쳤)"
    r")",
    re.DOTALL,
)
_TOPIC_SWITCH_RE = re.compile(r"(?:새\s*주제로|주제를\s*바꿔|다른\s*주제|그런데\s+[가-힣A-Za-z0-9_-]{2,})")
_KOREAN_QUESTION_END_RE = re.compile(r"(?:인가요|뭔가요|무엇인가요|알려\s*주세요|설명해\s*주세요)[?\s]*$")
_CONTEXTUAL_QUESTION_RE = re.compile(
    r"(?:어떻게|왜|무엇|뭐|어떤|어디|언제|누가).{0,60}"
    r"(?:나요|가요|까요|인가요|한가요|되나요)|"
    r"(?:나요|까요|인가요|한가요|되나요|맞나요|유지되나요)[?\s]*$"
)

_PROMISE_RE = re.compile(
    r"(?:검색|확인|검증|조회|찾아보|살펴보|조사|실행|열어보|저장)"
    r"[^.\n]{0,50}(?:하겠습니다|겠습니다|해\s*보겠습니다|해보겠습니다|해볼게요|해\s*볼게요|"
    r"보겠습니다|볼게요)"
)

_PAST_CONVERSATION_RE = re.compile(
    r"(?:예전|이전|과거|지난|전에).{0,50}(?:채팅|대화|세션)|"
    r"(?:채팅|대화|세션).{0,50}(?:기록|목록|찾|검색|논의|이야기)"
)
_LEGAL_EVIDENCE_RE = re.compile(
    r"(?:법령|법조문|조문|판례|대법원|헌법재판소|현행법|법률\s*근거|공식\s*법률|"
    r"법적\s*(?:해석|검토|분석)|법률적\s*(?:해석|검토|분석)|제\d+조)"
)
_LOCAL_EVIDENCE_SOURCE_RE = re.compile(
    r"(?:(?:고정|선택|첨부)(?:된|한)?|현재|이|해당)?\s*"
    r"(?:메모|노트|문서|파일|Vault|볼트|옵시디언)"
    r"(?:의|에|에서|만|를|을|로|으로|\s)*"
    r"(?:파싱\s*문서|내용|본문|근거|자료|사실)?",
    re.I,
)
_LOCAL_EVIDENCE_ANALYSIS_RE = re.compile(
    r"(?:요약|분석|설명|정리|비교|검토|구분|추출|질문에\s*답|알려)"
)
_LOCAL_EVIDENCE_MUTATION_RE = re.compile(
    r"(?:저장|작성|생성|추가|수정|편집|삭제|기록|만들|넣|등록|보내|답장|예약|업데이트|바꿔)"
)

_SEMANTIC_TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9_]+")
_KOREAN_PARTICLE_SUFFIXES = tuple(sorted({
    "으로부터", "에게서", "한테서", "에서부터", "까지는", "부터는",
    "에서는", "으로는", "에게는", "한테는", "이라도", "라도",
    "으로", "에서", "에게", "한테", "까지", "부터", "처럼", "보다",
    "이라고", "라고", "과", "와", "을", "를", "은", "는", "이", "가",
    "의", "에", "도", "만", "로", "랑",
}, key=len, reverse=True))
_KOREAN_VERB_ENDINGS = tuple(sorted({
    "해주시겠어요", "해주실래요", "해주세요", "해주십시오", "해주겠어요",
    "하겠습니다", "했습니다", "합니다", "입니다", "인가요", "할까요",
    "하세요", "해보세요", "해줘요", "해줘", "해요", "해라",
}, key=len, reverse=True))


def _normalize_korean_token(token: str) -> str:
    value = str(token or "")
    if len(value) < 2:
        return value
    for ending in _KOREAN_VERB_ENDINGS:
        if value.endswith(ending) and len(value) - len(ending) >= 1:
            value = value[:-len(ending)]
            break
    for suffix in _KOREAN_PARTICLE_SUFFIXES:
        if value.endswith(suffix) and len(value) - len(suffix) >= 2:
            value = value[:-len(suffix)]
            break
    if value.endswith("법상") and len(value) > 2:
        value = value[:-1]
    return value


def semantic_tokens(text: str) -> list[str]:
    """Tokenize Korean/Latin text for deterministic lexical retrieval.

    This deliberately small normalization layer removes common Korean
    particles and polite endings. It improves private local retrieval without
    translating text externally or adding a heavyweight morphology package.
    """

    tokens: list[str] = []
    for raw in _SEMANTIC_TOKEN_RE.findall(str(text or "")):
        token = _normalize_korean_token(raw) if contains_hangul(raw) else raw.lower()
        if token:
            tokens.append(token)
    return tokens


def contains_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(str(text or "")))


def is_korean_explanatory_question(text: str) -> bool:
    value = str(text or "").strip()
    return contains_hangul(value) and bool(_EXPLANATORY_RE.search(value))


def is_korean_casual_low_signal(text: str) -> bool:
    value = str(text or "").strip()
    return bool(value and _CASUAL_RE.fullmatch(value))


def is_korean_web_context(text: str) -> bool:
    return contains_hangul(text) and bool(_WEB_WORD_RE.search(str(text or "")))


def is_korean_web_intent(text: str) -> bool:
    """Return true only for an actionable Korean web lookup.

    Personal/local searches remain outside this detector unless the user
    explicitly says web/internet/online.  Tool-policy opt-in is enforced by the
    caller, so this is routing evidence rather than permission.
    """

    value = str(text or "").strip()
    if not contains_hangul(value) or is_korean_explanatory_question(value):
        return False
    explicit_medium = bool(_EXPLICIT_WEB_MEDIUM_RE.search(value))
    if _PERSONAL_SEARCH_TARGET_RE.search(value) and not explicit_medium:
        return False
    if explicit_medium and (_DIRECT_WEB_ACTION_RE.search(value) or _ACTION_END_RE.search(value)):
        return True
    if _DIRECT_WEB_ACTION_RE.search(value):
        return True
    return bool(
        _FRESHNESS_RE.search(value)
        and _FRESH_SUBJECT_RE.search(value)
        and _ACTION_END_RE.search(value)
    )


def is_korean_local_evidence_analysis(text: str) -> bool:
    """Distinguish reading pinned evidence from mutating a note/document.

    Korean requests commonly mention the container noun (``메모``, ``문서``)
    before asking for a summary.  Treating the noun itself as a notes action
    routes an ordinary evidence-grounded chat into the mutation agent.  A
    genuine create/update/save verb keeps the request on the tool path.
    """

    value = str(text or "").strip()
    return bool(
        contains_hangul(value)
        and _LOCAL_EVIDENCE_SOURCE_RE.search(value)
        and _LOCAL_EVIDENCE_ANALYSIS_RE.search(value)
        and not _LOCAL_EVIDENCE_MUTATION_RE.search(value)
    )


def is_korean_contextual_followup(text: str, recent_context: str) -> bool:
    """Whether a Korean turn intentionally continues a recent web task."""

    value = str(text or "").strip()
    if not value or not is_korean_web_context(recent_context):
        return False
    if is_korean_repair_followup(value):
        return True
    if _TOPIC_SWITCH_RE.search(value) and not re.search(r"이번에는|방금|위\s*(?:질문|내용)", value):
        return False
    if _CONTINUATION_EXACT_RE.fullmatch(value):
        return True
    if not _CONTEXT_REFERENCE_RE.search(value):
        return False
    if (
        is_korean_explanatory_question(value)
        and not _CONTEXTUAL_QUESTION_RE.search(value)
        and not re.search(r"할\s*수\s*있", value)
    ):
        return False
    return bool(
        _ACTION_END_RE.search(value)
        or _CONTEXTUAL_QUESTION_RE.search(value)
        or re.search(r"(?:잘\s*할\s*수\s*있|가능할까요|되나요|해줄래)", value)
    )


def is_korean_repair_followup(text: str) -> bool:
    """Whether a Korean turn repairs a missed or context-broken answer.

    These short turns must never become literal retrieval queries.  They refer
    to the last substantive user request even when they omit an action verb.
    """

    value = str(text or "").strip()
    return bool(value and contains_hangul(value) and _REPAIR_FOLLOWUP_RE.search(value))


def is_korean_explicit_continuation(text: str) -> bool:
    """Whether the turn explicitly refers to a preceding instruction/result."""

    value = str(text or "").strip()
    if not value or not contains_hangul(value):
        return False
    if is_korean_repair_followup(value):
        return True
    if _TOPIC_SWITCH_RE.search(value) and not re.search(r"이번에는|방금|위\s*(?:질문|내용)", value):
        return False
    if _CONTINUATION_EXACT_RE.fullmatch(value):
        return True
    return bool(
        _CONTEXT_REFERENCE_RE.search(value)
        and (
            _ACTION_END_RE.search(value)
            or _CONTEXTUAL_QUESTION_RE.search(value)
            or re.search(r"(?:잘\s*할\s*수\s*있|가능할까요|되나요|해줄래)", value)
        )
    )


def detect_korean_domains(text: str) -> Set[str]:
    """Map Korean wording onto the agent loop's existing domain families."""

    value = str(text or "").strip()
    if not contains_hangul(value):
        return set()
    domains: Set[str] = set()
    past_conversation = bool(_PAST_CONVERSATION_RE.search(value))
    legal_evidence = bool(_LEGAL_EVIDENCE_RE.search(value))
    # "제10조가 어떻게 적용되나요?" is an explanatory sentence, but it still
    # asks for a legal conclusion that must be grounded in official law.  Keep
    # generic feature/how-to questions tool-free while preserving legal intent.
    if is_korean_explanatory_question(value) and not legal_evidence:
        return set()
    if past_conversation:
        domains.add("sessions")
    if legal_evidence:
        domains.add("legal")
    if is_korean_web_intent(value) and (
        not legal_evidence or bool(_EXPLICIT_WEB_MEDIUM_RE.search(value))
    ):
        domains.add("web")
    if re.search(r"(?:이메일|메일|받은편지함|답장|회신|전달)", value):
        domains.add("email")
    if re.search(r"(?:일정|캘린더|달력|회의|약속|리마인더|할\s*일|체크리스트|메모|노트)", value):
        domains.add("notes_calendar_tasks")
    if re.search(r"(?:Documents|보고서|문서|초안|개요|편집|교정|작성)", value):
        domains.add("documents")
    if re.search(r"(?:레포|리포지토리|코드|소스|테스트|디버그|파일|폴더|터미널|셸|깃|브랜치|커밋)", value):
        domains.add("files")
    if re.search(r"(?:설정|엔드포인트|API\s*토큰|웹훅|MCP\s*설정)", value, re.I):
        domains.add("settings")
    if re.search(r"(?:채팅\s*목록|채팅\s*기록|세션|대화\s*(?:목록|기록))", value):
        domains.add("sessions")
    if re.search(r"(?:패널|사이드바|화면|메뉴|열어|보여|켜줘|꺼줘|전환)", value):
        domains.add("ui")
    if past_conversation and not re.search(r"(?:패널|사이드바|화면|메뉴)", value):
        domains.discard("ui")
    return domains


def looks_like_korean_action_promise(text: str) -> bool:
    value = str(text or "").strip()
    return contains_hangul(value) and bool(_PROMISE_RE.search(value))
