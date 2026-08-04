"""Tests for agent_loop.py — _detect_admin_intent, _compute_final_metrics,
and _append_tool_results. Uses mock imports to avoid loading the full app stack."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

_MOCKED_IMPORTS = [
    'sqlalchemy', 'sqlalchemy.orm', 'sqlalchemy.ext', 'sqlalchemy.ext.declarative',
    'sqlalchemy.ext.hybrid', 'sqlalchemy.sql', 'sqlalchemy.sql.expression',
    'src.database',
    'src.agent_tools',
    'core.models', 'core.database',
]
_INJECTED_IMPORT_STUBS = {}
_PREEXISTING_AGENT_LOOP = sys.modules.get("src.agent_loop")


def _drop_module_if_same(name, expected):
    if sys.modules.get(name) is expected:
        sys.modules.pop(name, None)
    parent_name, _, attr = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None and getattr(parent, "__dict__", {}).get(attr) is expected:
        delattr(parent, attr)


# Mock heavy dependencies before importing. Only clean up stubs this file
# created so pre-existing conftest/pytest modules keep their intended state.
for mod in _MOCKED_IMPORTS:
    if mod not in sys.modules:
        stub = MagicMock()
        sys.modules[mod] = stub
        _INJECTED_IMPORT_STUBS[mod] = stub

_IMPORTED_AGENT_LOOP = None
try:
    from src.agent_loop import (
        TOOL_SECTIONS,
        _detect_admin_intent,
        _classify_agent_request,
        _compute_final_metrics,
        _append_tool_results,
        _insert_before_latest_user,
        _merge_web_source_ledger,
        _legal_completion_problem,
        _limit_strict_legal_tool_blocks,
        _limit_strict_web_tool_blocks,
        _prior_verified_web_sources,
        _prior_verified_web_evidence,
        _recent_context_for_retrieval,
        _select_answer_web_sources,
        _web_tool_call_limit,
        _web_completion_problem,
        _wants_web_delta_retrieval,
        _wants_prior_web_evidence_reuse,
        _MCP_KEYWORDS,
    )
    _IMPORTED_AGENT_LOOP = sys.modules.get("src.agent_loop")
finally:
    if _PREEXISTING_AGENT_LOOP is None and _IMPORTED_AGENT_LOOP is not None:
        _drop_module_if_same("src.agent_loop", _IMPORTED_AGENT_LOOP)
    for _mod, _stub in _INJECTED_IMPORT_STUBS.items():
        _drop_module_if_same(_mod, _stub)


def test_import_stubs_do_not_leak_into_later_tests():
    leaked = [
        mod for mod, stub in _INJECTED_IMPORT_STUBS.items()
        if sys.modules.get(mod) is stub
    ]
    assert leaked == []
    if _PREEXISTING_AGENT_LOOP is None:
        assert sys.modules.get("src.agent_loop") is not _IMPORTED_AGENT_LOOP


def test_mcp_keyword_gate_matches_literal_mcp_requests():
    assert "mcp" in _MCP_KEYWORDS


def test_strict_web_turn_gets_a_finite_default_tool_budget():
    assert _web_tool_call_limit(0, web_completion_required=True) == 4
    assert _web_tool_call_limit(3, web_completion_required=True) == 3
    assert _web_tool_call_limit(0, web_completion_required=False) == 0


def test_strict_textual_web_calls_keep_bounded_search_then_fetch_pipeline():
    blocks = [
        SimpleNamespace(tool_type="web_search", content="first query"),
        SimpleNamespace(tool_type="web_search", content="second query"),
        SimpleNamespace(tool_type="web_fetch", content="https://first.example.test"),
        SimpleNamespace(tool_type="web_fetch", content="https://second.example.test"),
        SimpleNamespace(tool_type="web_search", content="fifth query"),
    ]

    assert _limit_strict_web_tool_blocks(
        blocks,
        used_native=False,
        web_completion_required=True,
    ) == blocks[:4]
    assert _limit_strict_web_tool_blocks(
        blocks,
        used_native=True,
        web_completion_required=True,
    ) == blocks


def test_strict_textual_web_calls_drop_duplicate_queries_before_execution():
    blocks = [
        SimpleNamespace(tool_type="web_search", content="same query"),
        SimpleNamespace(tool_type="web_search", content=" same query "),
        SimpleNamespace(tool_type="web_fetch", content="https://example.test/source"),
    ]

    assert _limit_strict_web_tool_blocks(
        blocks,
        used_native=False,
        web_completion_required=True,
    ) == [blocks[0], blocks[2]]


def test_strict_textual_korean_law_calls_execute_sequentially():
    blocks = [
        SimpleNamespace(tool_type="korean_law_lookup", content="first"),
        SimpleNamespace(tool_type="korean_law_lookup", content="second"),
    ]

    assert _limit_strict_legal_tool_blocks(
        blocks,
        used_native=False,
        legal_completion_required=True,
    ) == [blocks[0]]
    assert _limit_strict_legal_tool_blocks(
        blocks,
        used_native=True,
        legal_completion_required=True,
    ) == blocks


def test_legal_completion_requires_verified_identity_in_final_answer():
    assert _legal_completion_problem(
        "대한민국헌법 제10조입니다.",
        attempted_calls=1,
        successful_calls=1,
        verified_evidence=1,
    ) == "missing_legal_citation"
    assert _legal_completion_problem(
        "공식 근거: law.go.kr · 대한민국헌법 · MST 61603, 제10조 본문입니다.",
        attempted_calls=1,
        successful_calls=1,
        verified_evidence=1,
    ) == ""


def test_legal_completion_accepts_explicit_runtime_failure_only():
    assert _legal_completion_problem(
        "법률을 설명할 수 없습니다.",
        attempted_calls=1,
        successful_calls=0,
        verified_evidence=0,
    ) == "legal_tool_failed_without_disclosure"
    assert _legal_completion_problem(
        "Korean Law MCP 조회가 timeout으로 실패해 공식 원문을 확인하지 못했습니다.",
        attempted_calls=1,
        successful_calls=0,
        verified_evidence=0,
    ) == ""


def test_polish_internet_search_request_classifies_as_web():
    intent = _classify_agent_request(
        [],
        "Wyszukaj w internecie i podaj temperaturę w Lubartowie dzisiaj",
    )

    assert intent["low_signal"] is False
    assert "web" in intent["domains"]


def test_korean_web_followup_reuses_recent_bounded_context():
    messages = [
        {"role": "user", "content": "최신 Codex 릴리스를 웹에서 검색해줘"},
        {"role": "assistant", "content": "공식 문서와 릴리스 근거를 확인했습니다."},
        {"role": "user", "content": "그럼 이번에는 실제로 다시 검색해줘."},
    ]
    intent = _classify_agent_request(messages, messages[-1]["content"])

    assert intent["continuation"] is True
    assert "web" in intent["domains"]
    assert "최신 Codex 릴리스" in intent["retrieval_query"]


def test_korean_new_topic_does_not_reuse_stale_web_context():
    messages = [
        {"role": "user", "content": "최신 Codex 릴리스를 웹에서 검색해줘"},
        {"role": "assistant", "content": "공식 문서를 확인했습니다."},
        {"role": "user", "content": "그런데 파이썬의 GIL이 무엇인지 설명해 주세요."},
    ]
    intent = _classify_agent_request(messages, messages[-1]["content"])

    assert intent["continuation"] is False
    assert "최신 Codex 릴리스" not in intent["retrieval_query"]


def test_korean_repair_turn_resolves_to_last_substantive_question():
    substantive = (
        "현재 Vault와 정리된 LLM Wiki Vault를 분리해 운영하는 세부 방안을 "
        "웹 근거와 함께 안내해줘."
    )
    messages = [
        {"role": "user", "content": "이전에는 계약서 보존 방식을 물었습니다."},
        {"role": "assistant", "content": "이전 주제에 답했습니다."},
        {"role": "user", "content": substantive},
        {"role": "assistant", "content": "웹 근거를 답변에 연결하지 못했습니다."},
        {"role": "user", "content": "제대로 피드백을 못하신듯 마지막 질문에 대한"},
        {"role": "assistant", "content": "다시 시도해 주세요."},
        {"role": "user", "content": "위의 맥락이 이상한데 질문에 답이 아닌듯"},
    ]

    intent = _classify_agent_request(messages, messages[-1]["content"])

    assert intent["continuation"] is True
    assert intent["retrieval_query"] == substantive
    assert _recent_context_for_retrieval(messages) == substantive
    assert _wants_prior_web_evidence_reuse(messages[-1]["content"])


def test_fresh_followup_requests_delta_retrieval_not_plain_reuse():
    text = "방금 답변의 기존 근거는 유지하고 최신 사례를 추가로 웹에서 찾아 보완해줘."

    assert _wants_web_delta_retrieval(text)
    assert not _wants_web_delta_retrieval("방금 확인한 같은 근거만 다시 설명해줘.")
    assert not _wants_web_delta_retrieval(
        "방금 확인한 같은 두 공식 근거만 재사용해서, 두 기능 중 비개발자에게 "
        "더 직접적인 기능을 한 문장으로 설명해 주세요. 새 웹검색은 하지 마세요."
    )


def test_web_completion_rejects_korean_plan_instead_of_answer():
    problem = _web_completion_problem(
        "이번에는 GitHub와 Reddit을 교차 검증해서 정리하겠습니다.",
        attempted_calls=1,
        successful_calls=1,
        usable_sources=3,
    )

    assert problem == "plan_without_answer"


def test_web_completion_accepts_grounded_korean_answer_with_citation():
    problem = _web_completion_problem(
        "최근 변경의 핵심은 에이전트 도구 범위 축소입니다 [1].",
        attempted_calls=1,
        successful_calls=1,
        usable_sources=2,
    )

    assert problem == ""


def test_web_completion_requires_an_actual_tool_attempt():
    problem = _web_completion_problem(
        "현재 검색 도구를 사용할 수 없어 확인하지 못했습니다.",
        attempted_calls=0,
        successful_calls=0,
        usable_sources=0,
    )

    assert problem == "no_web_tool_attempt"


def test_web_completion_accepts_explicit_reuse_of_verified_prior_sources():
    problem = _web_completion_problem(
        "격리된 worktree는 파일 변경을 분리해 충돌을 줄입니다 [1].",
        attempted_calls=0,
        successful_calls=0,
        usable_sources=1,
        reused_sources=1,
    )

    assert problem == ""


def test_prior_web_evidence_reuse_requires_verified_metadata_and_explicit_reference():
    messages = [
        {"role": "user", "content": "공식 문서를 검색해줘"},
        {
            "role": "assistant",
            "content": "공식 근거를 확인했습니다 [1].",
            "metadata": {
                "web_sources": [
                    {
                        "url": "https://openai.com/example",
                        "title": "Official source",
                        "fetched": True,
                        "usable": True,
                        "evidence_status": "fetched",
                    },
                    {
                        "url": "https://untrusted.example/candidate",
                        "title": "Candidate only",
                        "fetched": False,
                        "usable": False,
                        "evidence_status": "candidate",
                    },
                ],
                "tool_events": [{
                    "tool": "web_fetch",
                    "command": "https://openai.com/example",
                    "output": (
                        "PRIOR_FETCHED_BODY_SENTINEL\n"
                        "Source: https://openai.com/example"
                    ),
                    "exit_code": 0,
                }],
            },
        },
        {"role": "user", "content": "방금 확인한 같은 근거만 재사용해서 설명해줘."},
    ]

    assert _wants_prior_web_evidence_reuse(messages[-1]["content"]) is True
    assert _prior_verified_web_sources(messages) == [
        {
            "url": "https://openai.com/example",
            "title": "Official source",
            "fetched": True,
            "usable": True,
            "evidence_status": "fetched",
        }
    ]
    assert "PRIOR_FETCHED_BODY_SENTINEL" in _prior_verified_web_evidence(messages)


def test_prior_web_evidence_body_is_not_inferred_from_source_metadata_only():
    messages = [{
        "role": "assistant",
        "content": "요약 [1].",
        "metadata": {
            "web_sources": [{
                "url": "https://example.test/source",
                "title": "Source",
                "fetched": True,
                "usable": True,
                "evidence_status": "fetched",
            }],
        },
    }]

    assert _prior_verified_web_sources(messages)
    assert _prior_verified_web_evidence(messages) == ""


def test_prior_web_evidence_excludes_successful_events_outside_verified_manifest():
    verified_url = "https://official.example/guide"
    messages = [{
        "role": "assistant",
        "content": "검증된 답변 [1].",
        "metadata": {
            "web_sources": [{
                "url": verified_url,
                "title": "Official guide",
                "fetched": True,
                "usable": True,
                "evidence_status": "fetched",
            }],
            "tool_events": [
                {
                    "tool": "web_search",
                    "command": "unrelated repair complaint",
                    "output": (
                        "UNRELATED_BODY_MUST_NOT_BE_REUSED\n"
                        "https://unrelated.example/post"
                    ),
                    "exit_code": 0,
                },
                {
                    "tool": "web_fetch",
                    "command": verified_url,
                    "output": f"VERIFIED_BODY_MUST_BE_REUSED\nSource: {verified_url}",
                    "exit_code": 0,
                },
            ],
        },
    }]

    evidence = _prior_verified_web_evidence(messages)

    assert "VERIFIED_BODY_MUST_BE_REUSED" in evidence
    assert "UNRELATED_BODY_MUST_NOT_BE_REUSED" not in evidence


def test_prior_web_evidence_extracts_only_verified_fetched_blocks_from_search_output():
    official_one = "https://openai.com/index/introducing-the-codex-app"
    official_two = "https://github.com/openai/codex/blob/main/README.md?plain=1"
    candidate = "https://untrusted.example/candidate"
    messages = [{
        "role": "assistant",
        "content": "공식 자료 두 건을 비교했습니다 [1][2].",
        "metadata": {
            "web_sources": [
                {
                    "url": official_one,
                    "title": "Introducing the Codex app",
                    "fetched": True,
                    "usable": True,
                    "evidence_status": "fetched",
                },
                {
                    "url": official_two,
                    "title": "openai/codex README",
                    "fetched": True,
                    "usable": True,
                    "evidence_status": "fetched",
                },
            ],
            "tool_events": [{
                "tool": "web_search",
                "command": '{"query":"Codex official comparison"}',
                "output": (
                    "DISCOVERED CANDIDATES (not citable unless also fetched below):\n"
                    f"[CANDIDATE 1] Untrusted\n    URL: {candidate}\n\n"
                    "FETCHED PAGE CONTENT:\n"
                    f"[CONTENT 1] From: {official_one}\n"
                    "Title: Introducing the Codex app\n"
                    "------------------------------\n"
                    "OPENAI_OFFICIAL_BODY_SENTINEL\n\n"
                    f"[CONTENT 2] From: {official_two}\n"
                    "Title: openai/codex README\n"
                    "------------------------------\n"
                    "GITHUB_OFFICIAL_BODY_SENTINEL\n\n"
                    "======================================================================\n"
                    "END OF WEB SEARCH RESULTS\n"
                ),
                "exit_code": 0,
            }],
        },
    }]

    evidence = _prior_verified_web_evidence(messages)

    assert "OPENAI_OFFICIAL_BODY_SENTINEL" in evidence
    assert "GITHUB_OFFICIAL_BODY_SENTINEL" in evidence
    assert candidate not in evidence


def test_web_source_ledger_deduplicates_and_final_answer_selects_direct_links():
    ledger, mapping = _merge_web_source_ledger(
        [
            {
                "url": "https://openai.com/first",
                "title": "First",
                "fetched": True,
                "usable": True,
            }
        ],
        [
            {
                "url": "https://openai.com/first/",
                "title": "First duplicate",
                "fetched": True,
                "usable": True,
            },
            {
                "url": "https://openai.com/second",
                "title": "Second",
                "fetched": True,
                "usable": True,
            },
        ],
    )

    assert len(ledger) == 2
    assert mapping == {1: 1, 2: 2}
    selected = _select_answer_web_sources(
        "근거는 [공식 페이지](https://openai.com/second)입니다 [1].",
        ledger,
    )
    assert [source["url"] for source in selected] == ["https://openai.com/second"]


def test_web_source_ledger_keeps_prior_github_readme_identity_for_repo_root_alias():
    """A delta search must not replace the verified README with its repo landing URL."""

    readme_url = "https://github.com/openai/codex/blob/main/README.md?plain=1"
    ledger, mapping = _merge_web_source_ledger(
        [{
            "url": readme_url,
            "title": "openai/codex README",
            "fetched": True,
            "usable": True,
        }],
        [{
            "url": "https://github.com/openai/codex",
            "title": "openai/codex",
            "fetched": True,
            "usable": True,
        }],
    )

    assert len(ledger) == 1
    assert ledger[0]["url"] == readme_url
    assert mapping == {1: 1}
    selected = _select_answer_web_sources(
        "공식 저장소 설명입니다 [GitHub](https://github.com/openai/codex).",
        ledger,
    )
    assert [source["url"] for source in selected] == [readme_url]


def test_web_completion_accepts_honest_failure_after_tool_error():
    problem = _web_completion_problem(
        "웹 검색이 429 제한으로 실패하여 최신 정보를 확인하지 못했습니다.",
        attempted_calls=1,
        successful_calls=0,
        usable_sources=0,
    )

    assert problem == ""


def test_web_completion_rejects_uncited_answer_when_sources_exist():
    problem = _web_completion_problem(
        "최근 변경의 핵심은 에이전트 도구 범위 축소입니다.",
        attempted_calls=1,
        successful_calls=1,
        usable_sources=2,
    )

    assert problem == "missing_citation"


def test_web_tool_prompt_requires_same_turn_grounded_synthesis():
    prompt = TOOL_SECTIONS["web_search"]

    assert "same turn" in prompt.lower()
    assert "[n]" in prompt.lower()
    assert "methodology" in prompt.lower()


def test_insert_before_latest_user_places_context_before_last_user_turn():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "latest"},
    ]
    context = {"role": "system", "content": "context"}

    out = _insert_before_latest_user(messages, context)

    assert out == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        context,
        {"role": "user", "content": "latest"},
    ]
    assert messages == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "latest"},
    ]


def test_insert_before_latest_user_appends_when_no_user_message_exists():
    messages = [{"role": "assistant", "content": "reply"}]
    context = {"role": "system", "content": "context"}

    assert _insert_before_latest_user(messages, context) == [messages[0], context]


# ---------------------------------------------------------------------------
# _detect_admin_intent
# ---------------------------------------------------------------------------

class TestDetectAdminIntent:
    """Test admin-intent detection from the last user message."""

    def _msgs(self, text: str):
        """Helper: wrap text in a minimal messages list."""
        return [{"role": "user", "content": text}]

    # --- Should detect admin intent ---

    def test_add_endpoint(self):
        assert _detect_admin_intent(self._msgs("add a new endpoint")) is True

    def test_create_endpoint(self):
        assert _detect_admin_intent(self._msgs("create endpoint for openai")) is True

    def test_manage_sessions(self):
        assert _detect_admin_intent(self._msgs("list all sessions")) is True

    def test_rename_session(self):
        assert _detect_admin_intent(self._msgs("rename this session")) is True

    def test_archive_session(self):
        assert _detect_admin_intent(self._msgs("archive old sessions")) is True

    def test_configure_settings(self):
        assert _detect_admin_intent(self._msgs("configure my settings")) is True

    def test_mcp_server(self):
        assert _detect_admin_intent(self._msgs("add an MCP server")) is True

    def test_api_key(self):
        assert _detect_admin_intent(self._msgs("update the API key")) is True

    def test_list_models(self):
        assert _detect_admin_intent(self._msgs("list models available")) is True

    def test_switch_model(self):
        assert _detect_admin_intent(self._msgs("switch model to gpt-4")) is True

    def test_manage_skills(self):
        assert _detect_admin_intent(self._msgs("show me my skills")) is True

    def test_schedule_task(self):
        assert _detect_admin_intent(self._msgs("schedule a cron task")) is True

    def test_case_insensitive(self):
        assert _detect_admin_intent(self._msgs("MANAGE SESSIONS")) is True

    # --- Should NOT detect admin intent ---

    def test_hello(self):
        assert _detect_admin_intent(self._msgs("hello")) is False

    def test_write_code(self):
        assert _detect_admin_intent(self._msgs("write some python code")) is False

    def test_explain_concept(self):
        assert _detect_admin_intent(self._msgs("explain how transformers work")) is False

    def test_general_question(self):
        assert _detect_admin_intent(self._msgs("what is the capital of France?")) is False

    # --- Edge cases ---

    def test_empty_messages(self):
        assert _detect_admin_intent([]) is False

    def test_no_user_message(self):
        assert _detect_admin_intent([{"role": "assistant", "content": "hi"}]) is False

    def test_multimodal_content(self):
        """Content as a list of blocks (vision messages)."""
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "rename this session please"},
        ]}]
        assert _detect_admin_intent(msgs) is True

    def test_multimodal_no_admin(self):
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "describe this image"},
        ]}]
        assert _detect_admin_intent(msgs) is False

    def test_uses_last_user_message(self):
        """Should check only the last user message."""
        msgs = [
            {"role": "user", "content": "rename this session"},
            {"role": "assistant", "content": "done"},
            {"role": "user", "content": "thanks, now just say hello"},
        ]
        assert _detect_admin_intent(msgs) is False


# ---------------------------------------------------------------------------
# _compute_final_metrics
# ---------------------------------------------------------------------------

class TestComputeFinalMetrics:
    """Test metric computation with real and estimated usage."""

    def _base_args(self, **overrides):
        defaults = dict(
            messages=[{"role": "user", "content": "hello world"}],
            full_response="This is a test response.",
            total_duration=2.0,
            time_to_first_token=0.5,
            context_length=8192,
            real_input_tokens=100,
            real_output_tokens=50,
            has_real_usage=True,
            tool_events=[],
            round_texts=[],
            model="test-model",
            last_round_input_tokens=0,
            prep_timings=None,
        )
        defaults.update(overrides)
        return defaults

    def test_real_usage_tokens(self):
        m = _compute_final_metrics(**self._base_args())
        assert m["input_tokens"] == 100
        assert m["output_tokens"] == 50
        assert m["total_tokens"] == 150
        assert m["usage_source"] == "real"

    def test_estimated_usage_tokens(self):
        m = _compute_final_metrics(**self._base_args(
            has_real_usage=False,
            real_input_tokens=0,
            real_output_tokens=0,
        ))
        # Estimated: len("hello world\n") // 4 = 3
        assert m["input_tokens"] == 3
        assert m["usage_source"] == "estimated"

    def test_tps_calculation(self):
        m = _compute_final_metrics(**self._base_args(
            real_output_tokens=100,
            total_duration=2.0,
        ))
        assert m["tokens_per_second"] == 50.0

    def test_tps_zero_duration(self):
        m = _compute_final_metrics(**self._base_args(total_duration=0.0))
        assert m["tokens_per_second"] == 0

    def test_context_percent(self):
        m = _compute_final_metrics(**self._base_args(
            real_input_tokens=4096,
            context_length=8192,
        ))
        assert m["context_percent"] == 50.0

    def test_context_percent_capped_at_100(self):
        m = _compute_final_metrics(**self._base_args(
            real_input_tokens=10000,
            context_length=8192,
        ))
        assert m["context_percent"] == 100.0

    def test_context_percent_zero_context_length(self):
        m = _compute_final_metrics(**self._base_args(context_length=0))
        assert m["context_percent"] == 0

    def test_last_round_input_tokens_used_for_context_pct(self):
        """When last_round_input_tokens > 0, it should be used for context %."""
        m = _compute_final_metrics(**self._base_args(
            real_input_tokens=100,
            last_round_input_tokens=4096,
            context_length=8192,
        ))
        assert m["context_percent"] == 50.0

    def test_response_time(self):
        m = _compute_final_metrics(**self._base_args(total_duration=3.456))
        assert m["response_time"] == 3.46

    def test_time_to_first_token(self):
        m = _compute_final_metrics(**self._base_args(time_to_first_token=0.123))
        assert m["time_to_first_token"] == 0.12

    def test_time_to_first_token_none(self):
        m = _compute_final_metrics(**self._base_args(time_to_first_token=None))
        assert m["time_to_first_token"] == 0

    def test_model_returned(self):
        m = _compute_final_metrics(**self._base_args(model="gpt-4o"))
        assert m["model"] == "gpt-4o"

    def test_prep_timings_included(self):
        m = _compute_final_metrics(**self._base_args(
            time_to_first_token=1.25,
            prep_timings={"request_setup": 0.2, "tool_selection": 0.3, "prompt_build": 0.15},
        ))
        assert m["agent_prep_time"] == 0.65
        assert m["agent_model_wait_time"] == 0.6
        assert m["agent_prep_breakdown"] == {
            "request_setup": 0.2,
            "tool_selection": 0.3,
            "prompt_build": 0.15,
        }

    def test_tool_events_included(self):
        events = [{"tool": "bash", "duration": 1.0}]
        texts = ["round 1 text"]
        m = _compute_final_metrics(**self._base_args(
            tool_events=events,
            round_texts=texts,
        ))
        assert m["tool_events"] == events
        assert m["round_texts"] == texts

    def test_no_tool_events_excluded(self):
        m = _compute_final_metrics(**self._base_args(tool_events=[], round_texts=[]))
        assert "tool_events" not in m
        assert "round_texts" not in m


# ---------------------------------------------------------------------------
# _append_tool_results — native tool-call message shaping
# ---------------------------------------------------------------------------

class TestAppendToolResultsNativeContent:
    """After a native tool call with no prose, the assistant message's content
    must be JSON null (None), not an empty string. Google Gemini's
    OpenAI-compatible endpoint and Ollama both reject `tool_calls` + ""
    content with HTTP 400, which breaks every tool-using turn."""

    def _native(self):
        return [{"id": "call_abc", "name": "web_fetch", "arguments": '{"url": "https://example.com"}'}]

    def test_empty_text_yields_null_content(self):
        messages = []
        _append_tool_results(
            messages, "", self._native(), [{}], ["page text"],
            used_native=True, round_num=1,
        )
        assistant = messages[0]
        assert assistant["role"] == "assistant"
        assert assistant["content"] is None  # NOT ""
        assert assistant["tool_calls"][0]["id"] == "call_abc"
        assert assistant["tool_calls"][0]["type"] == "function"
        # tool result follows as a role:tool message keyed by tool_call_id
        assert messages[1]["role"] == "tool"
        assert messages[1]["tool_call_id"] == "call_abc"
        assert messages[1]["content"] == "page text"

    def test_whitespace_only_text_yields_null_content(self):
        messages = []
        _append_tool_results(
            messages, "   \n\t  ", self._native(), [{}], ["r"],
            used_native=True, round_num=2,
        )
        assert messages[0]["content"] is None

    def test_real_prose_is_preserved(self):
        messages = []
        _append_tool_results(
            messages, "Let me check that page.", self._native(), [{}], ["r"],
            used_native=True, round_num=1,
        )
        assert messages[0]["content"] == "Let me check that page."

    def test_non_native_path_unaffected(self):
        # The text-block fallback path still wraps results in a user message.
        messages = []
        _append_tool_results(
            messages, "thinking...", [], ["tool output"], [],
            used_native=False, round_num=1,
        )
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "thinking..."
        assert messages[1]["role"] == "user"
        assert "tool output" in messages[1]["content"]


class TestAppendToolResultsThoughtSignature:
    """Gemini 3 returns an opaque thought_signature (in extra_content) with each
    function call and rejects the follow-up turn with HTTP 400 unless it is
    echoed back on the assistant tool_call. _append_tool_results must replay it
    when present, and omit the field entirely otherwise (other providers never
    send it)."""

    def test_extra_content_is_replayed_when_present(self):
        native = [{
            "id": "call_g",
            "name": "app_api",
            "arguments": '{"action": "get_memory"}',
            "extra_content": {"google": {"thought_signature": "EuIDCt8DAQ=="}},
        }]
        messages = []
        _append_tool_results(
            messages, "", native, [{}], ["mem"],
            used_native=True, round_num=1,
        )
        tc = messages[0]["tool_calls"][0]
        assert tc["extra_content"] == {"google": {"thought_signature": "EuIDCt8DAQ=="}}
        # function payload is still well-formed alongside it
        assert tc["function"]["name"] == "app_api"
        assert tc["id"] == "call_g"

    def test_no_extra_content_key_when_absent(self):
        native = [{"id": "call_o", "name": "app_api", "arguments": "{}"}]
        messages = []
        _append_tool_results(
            messages, "", native, [{}], ["r"],
            used_native=True, round_num=1,
        )
        # No empty/None extra_content leaks onto non-Gemini tool calls.
        assert "extra_content" not in messages[0]["tool_calls"][0]


# ---------------------------------------------------------------------------
# web_search sources extraction — key lookup regression (#443)
# ---------------------------------------------------------------------------

import json as _json


class TestWebSearchSourcesKeyLookup:
    """The web_search tool returns {"output": ..., "exit_code": 0}.
    The sources-extraction block in stream_agent_loop must read from the
    "output" key, not only from "results"/"stdout" (which web_search never
    sets).  Without the fix the SOURCES marker is never found, no
    web_sources SSE event is emitted, and the raw JSON blob leaks into the
    LLM's round-2 context."""

    _SOURCES = [{"title": "Example", "url": "https://example.com", "snippet": "test"}]

    def _make_result(self, key: str = "output") -> dict:
        sources_json = _json.dumps(self._SOURCES)
        text = f"Search results here.\n\n<!-- SOURCES:{sources_json} -->"
        return {key: text, "exit_code": 0}

    # ── Regression: the old lookup missed "output" ──────────────────────

    def test_old_lookup_missed_output_key(self):
        """Documents the bug: result.get('results') and result.get('stdout')
        are both absent when web_search returns its canonical {"output": ...}
        shape, so _src_text was always '' and the if-block never ran."""
        result = self._make_result("output")
        old_src_text = result.get("results") or result.get("stdout") or ""
        assert old_src_text == "", "confirms the pre-fix behaviour"

    def test_fixed_lookup_finds_output_key(self):
        """After the fix, "output" is checked first so _src_text is non-empty."""
        result = self._make_result("output")
        src_text = result.get("output") or result.get("results") or result.get("stdout") or ""
        assert src_text != ""
        assert "SOURCES" in src_text

    # ── Marker extraction works once _src_text is non-empty ─────────────

    def test_sources_extracted_from_output(self):
        result = self._make_result("output")
        src_text = result.get("output") or result.get("results") or result.get("stdout") or ""
        marker = "<!-- SOURCES:"
        idx = src_text.find(marker)
        end = src_text.find(" -->", idx)
        extracted = _json.loads(src_text[idx + len(marker):end])
        assert extracted == self._SOURCES

    def test_marker_stripped_from_output_key(self):
        """After extraction the "output" value is cleaned so the LLM never
        sees the raw JSON blob in its round-2 context."""
        result = self._make_result("output")
        src_text = result.get("output") or result.get("results") or result.get("stdout") or ""
        marker = "<!-- SOURCES:"
        idx = src_text.find(marker)
        clean = src_text[:idx].rstrip()
        # Apply to the correct key (was the bug: only "results"/"stdout" were updated)
        if "output" in result:
            result["output"] = clean
        assert "SOURCES" not in result["output"]
        assert result["output"] == "Search results here."

    # ── Backward compat: "results"/"stdout" keys still work ─────────────

    def test_results_key_still_works(self):
        result = self._make_result("results")
        src_text = result.get("output") or result.get("results") or result.get("stdout") or ""
        assert src_text != ""
        assert "SOURCES" in src_text

    def test_stdout_key_still_works(self):
        result = self._make_result("stdout")
        src_text = result.get("output") or result.get("results") or result.get("stdout") or ""
        assert src_text != ""
        assert "SOURCES" in src_text
