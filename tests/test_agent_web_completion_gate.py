import asyncio
import json
import time

import src.agent_loop as al
from src.tool_policy import WEB_TOOL_NAMES


def _collect(gen):
    async def run():
        return [chunk async for chunk in gen]

    return asyncio.run(run())


def _events(chunks):
    parsed = []
    for chunk in chunks:
        if not chunk.startswith("data: ") or chunk.startswith("data: [DONE]"):
            continue
        parsed.append(json.loads(chunk[6:]))
    return parsed


def _schema_names(tools):
    return {
        tool.get("function", {}).get("name") or tool.get("name")
        for tool in (tools or [])
    }


def test_web_turn_buffers_plans_and_releases_only_grounded_answer(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    schemas_by_round = []
    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        schemas_by_round.append(_schema_names(kwargs.get("tools")))
        current = round_number["value"]
        if current == 1:
            yield "data: " + json.dumps({
                "delta": "이번에는 최신 자료를 검색해서 비교하겠습니다."
            }) + "\n\n"
            yield "data: " + json.dumps({
                "type": "tool_calls",
                "calls": [{
                    "name": "web_search",
                    "arguments": json.dumps({
                        "query": "최신 Codex 변경 사항",
                        "time_filter": "week",
                    }),
                }],
            }) + "\n\n"
        elif current == 2:
            yield "data: " + json.dumps({
                "delta": "핵심 변경은 도구 범위를 더 엄격히 제한한 것입니다."
            }) + "\n\n"
        else:
            yield "data: " + json.dumps({
                "delta": "핵심 변경은 도구 범위를 더 엄격히 제한한 것입니다 [1]."
            }) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append(block.tool_type)
        sources = [{
            "url": "https://example.test/codex",
            "title": "Codex release",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }]
        return (
            "web_search",
            {
                "output": (
                    "[CONTENT 1] fetched evidence\n\n"
                    "<!-- SOURCES:" + json.dumps(sources) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    chunks = _collect(al.stream_agent_loop(
        "https://api.openai.com/v1",
        "gpt-test",
        [{"role": "user", "content": "이번에는 실제로 최신 내용을 웹에서 검색해줘."}],
        max_rounds=4,
        relevant_tools={"bash", "manage_memory", "mcp__unrelated__dangerous"},
        forced_tools=set(WEB_TOOL_NAMES),
    ))
    events = _events(chunks)
    visible_text = "".join(
        event.get("delta", "")
        for event in events
        if not event.get("thinking")
    )

    assert executed == ["web_search"]
    assert "검색해서 비교하겠습니다" not in visible_text
    assert visible_text == (
        "핵심 변경은 도구 범위를 더 엄격히 제한한 것입니다 "
        "[출처 1](https://example.test/codex)."
    )
    assert any(event.get("type") == "web_sources" for event in events)
    assert len([event for event in events if event.get("type") == "agent_step"]) >= 2

    assert schemas_by_round
    assert {"web_search", "web_fetch"}.issubset(schemas_by_round[0])
    assert schemas_by_round[2] == set()
    assert "bash" not in schemas_by_round[0]
    assert "manage_memory" not in schemas_by_round[0]
    assert not any(name and name.startswith("mcp__unrelated__") for name in schemas_by_round[0])


def test_explicit_web_turn_falls_back_to_search_when_model_only_announces_need(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        if round_number["value"] == 1:
            delta = "인라인 인용을 확인하려면 웹 검색이 필요합니다."
        else:
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "AUTOMATIC_SEARCH_BODY_SENTINEL" in joined
            assert "VERIFIED WEB EVIDENCE MANIFEST" in joined
            delta = "공식 문서는 로컬 코딩 에이전트 기능을 설명합니다 [1]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append((block.tool_type, json.loads(block.content)["query"]))
        source = {
            "url": "https://openai.test/codex",
            "title": "Official Codex",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    "AUTOMATIC_SEARCH_BODY_SENTINEL\n\n"
                    "```sources\n[1] Official Codex\n"
                    "    https://openai.test/codex\n```\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    query = "공식 Codex 문서를 웹에서 확인해줘."
    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": query}],
        max_rounds=3,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == [("web_search", query)]
    assert not any(event.get("type") == "web_completion_failed" for event in events)
    assert "필요합니다" not in "".join(event.get("delta", "") for event in events)


def test_named_source_retrieval_contract_is_injected_before_first_model_call(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        joined = "\n".join(str(message.get("content") or "") for message in messages)
        if round_number["value"] == 1:
            assert "STRICT WEB RETRIEVAL CONTRACT" in joined
            assert "one focused search for each named source" in joined
            assert "quoted title/topic plus an official site/domain constraint" in joined
            delta = '```web_search\n{"query":"site:official.test \\\"Named page\\\""}\n```'
        else:
            delta = "명명된 공식 문서를 확인했습니다 [1]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    async def fake_execute(*args, **kwargs):
        source = {
            "url": "https://official.test/named-page",
            "title": "Named page",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    "NAMED_PAGE_BODY\n\n```sources\n[1] Named page\n"
                    "    https://official.test/named-page\n```\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "두 명명된 공식 문서를 각각 검색해 비교해줘."}],
        max_rounds=3,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert not any(event.get("type") == "web_completion_failed" for event in events)


def test_web_tool_budget_transitions_to_grounded_synthesis_instead_of_stopping(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    rounds = {"value": 0}
    schemas_by_round = []

    async def fake_stream(_candidates, messages, **kwargs):
        rounds["value"] += 1
        schemas_by_round.append(_schema_names(kwargs.get("tools")))
        if rounds["value"] == 1:
            yield "data: " + json.dumps({
                "type": "tool_calls",
                "calls": [
                    {"name": "web_search", "arguments": json.dumps({"query": f"official source {i}"})}
                    for i in range(1, 5)
                ],
            }) + "\n\n"
        else:
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "VERIFIED WEB EVIDENCE MANIFEST" in joined
            assert "WEB TOOL BUDGET COMPLETE" in joined
            yield "data: " + json.dumps({
                "delta": "공식 문서 네 개를 비교한 결론입니다 [1]."
            }) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        query = str(block.content)
        index = int(query.rsplit(" ", 1)[-1])
        executed.append(query)
        source = {
            "url": f"https://official.test/source-{index}",
            "title": f"Official source {index}",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    f"FETCHED_BODY_{index}\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "https://api.openai.com/v1",
        "gpt-test",
        [{"role": "user", "content": "공식 출처 네 개를 검색해 비교해줘."}],
        max_rounds=3,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == [f"official source {i}" for i in range(1, 5)]
    assert schemas_by_round[1] == set()
    assert not any(event.get("type") == "budget_exceeded" for event in events)
    assert "공식 문서 네 개를 비교한 결론입니다" in "".join(
        event.get("delta", "") for event in events
    )


def test_out_of_range_numeric_citation_is_rejected_and_rewritten(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        if round_number["value"] == 1:
            delta = '```web_search\n{"query":"official source"}\n```'
        elif round_number["value"] == 2:
            delta = "확인된 사실입니다 [99]."
        else:
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "Remove every URL and claim" in joined
            delta = "확인된 사실입니다 [1]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    async def fake_execute(*args, **kwargs):
        source = {
            "url": "https://official.test/source",
            "title": "Official source",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    "OFFICIAL_BODY\n\n```sources\n[1] Official source\n"
                    "    https://official.test/source\n```\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "공식 자료를 웹에서 확인해줘."}],
        max_rounds=4,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))
    visible = "".join(event.get("delta", "") for event in events)

    assert "[99]" not in visible
    assert visible == "확인된 사실입니다 [출처 1](https://official.test/source)."
    assert not any(event.get("type") == "web_completion_failed" for event in events)


def test_web_followup_reuses_verified_prior_evidence_without_forcing_delta_search(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    async def fake_stream(_candidates, messages, **kwargs):
        assert any(
            "VERIFIED PRIOR WEB EVIDENCE" in str(message.get("content") or "")
            for message in messages
        )
        assert any(
            "PRIOR_WORKTREE_BODY_SENTINEL" in str(message.get("content") or "")
            for message in messages
        )
        yield "data: " + json.dumps({
            "delta": "격리된 worktree는 변경 파일을 분리해 같은 저장소의 충돌을 줄입니다 [1]."
        }) + "\n\n"
        yield "data: [DONE]\n\n"

    async def should_not_execute(*args, **kwargs):
        raise AssertionError("explicit same-evidence reuse must not require a new web call")

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", should_not_execute, raising=False)

    prior_source = {
        "url": "https://openai.com/index/introducing-the-codex-app",
        "title": "Introducing the Codex app",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }
    chunks = _collect(al.stream_agent_loop(
        "https://api.openai.com/v1",
        "gpt-test",
        [
            {"role": "user", "content": "Codex 앱 공식 기능을 검색해줘."},
            {
                "role": "assistant",
                "content": "worktree 격리를 확인했습니다 [1].",
                "metadata": {
                    "web_sources": [prior_source],
                    "tool_events": [{
                        "tool": "web_fetch",
                        "command": prior_source["url"],
                        "output": (
                            "PRIOR_WORKTREE_BODY_SENTINEL\nSource: "
                            + prior_source["url"]
                        ),
                        "exit_code": 0,
                    }],
                },
            },
            {
                "role": "user",
                "content": (
                    "방금 확인한 같은 두 공식 근거만 재사용해서, 두 기능 중 "
                    "비개발자에게 더 직접적인 기능을 한 문장으로 설명해 주세요. "
                    "새 웹검색은 하지 마세요."
                ),
            },
        ],
        max_rounds=2,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    ))
    events = _events(chunks)

    assert not any(event.get("type") == "web_completion_failed" for event in events)
    source_events = [event for event in events if event.get("type") == "web_sources"]
    assert source_events[-1]["data"] == [prior_source]
    assert "격리된 worktree" in "".join(event.get("delta", "") for event in events)


def test_korean_repair_followup_reuses_evidence_and_resolves_original_question(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    original_question = (
        "현재 Vault와 정리된 LLM Wiki Vault를 분리해 운영하는 세부 방안을 "
        "웹 근거와 함께 안내해줘."
    )

    async def fake_stream(_candidates, messages, **kwargs):
        joined = "\n".join(str(message.get("content") or "") for message in messages)
        assert "VERIFIED PRIOR WEB EVIDENCE" in joined
        assert "PRIOR_VAULT_BODY_SENTINEL" in joined
        assert "RESOLVED SUBSTANTIVE USER REQUEST" in joined
        assert original_question in joined
        yield "data: " + json.dumps({
            "delta": "원본 Vault는 기록 보존용, Wiki Vault는 검토된 지식용으로 분리합니다 [1]."
        }) + "\n\n"
        yield "data: [DONE]\n\n"

    async def should_not_execute(*args, **kwargs):
        raise AssertionError("repair follow-up must not search the complaint text")

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", should_not_execute, raising=False)

    prior_source = {
        "url": "https://example.test/vault-operations",
        "title": "Vault operations",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }
    events = _events(_collect(al.stream_agent_loop(
        "https://api.openai.com/v1",
        "gpt-test",
        [
            {"role": "user", "content": original_question},
            {
                "role": "assistant",
                "content": "초기 답변 [1].",
                "metadata": {
                    "web_sources": [prior_source],
                    "tool_events": [{
                        "tool": "web_search",
                        "command": "Vault operations",
                        "output": (
                            "PRIOR_VAULT_BODY_SENTINEL\nSource: "
                            + prior_source["url"]
                        ),
                        "exit_code": 0,
                    }],
                },
            },
            {"role": "user", "content": "제대로 피드백을 못하신듯 마지막 질문에 대한"},
            {"role": "assistant", "content": "다시 시도해 주세요."},
            {"role": "user", "content": "위의 맥락이 이상한데 질문에 답이 아닌듯"},
        ],
        max_rounds=2,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert not any(event.get("type") == "web_completion_failed" for event in events)
    assert "원본 Vault는 기록 보존용" in "".join(
        event.get("delta", "") for event in events
    )


def test_web_delta_followup_keeps_prior_ledger_and_requires_one_new_search(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    rounds = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        rounds["value"] += 1
        joined = "\n".join(str(message.get("content") or "") for message in messages)
        assert "VERIFIED PRIOR WEB EVIDENCE" in joined
        assert "DELTA WEB RETRIEVAL REQUIRED" in joined
        assert "PRIOR_PRINCIPLES_BODY_SENTINEL" in joined
        if rounds["value"] == 1:
            delta = '```web_search\n{"query":"2026 Obsidian knowledge vault workflow case study"}\n```'
        else:
            assert "DELTA_CASE_BODY_SENTINEL" in joined
            delta = "기존 분리 원칙은 유지하되 새 사례에서는 검토 큐를 추가합니다 [1][2]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append((block.tool_type, json.loads(block.content)["query"]))
        source = {
            "url": "https://example.test/new-vault-case",
            "title": "New vault case",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    "DELTA_CASE_BODY_SENTINEL\n\n"
                    "```sources\n[1] New vault case\n"
                    "    https://example.test/new-vault-case\n```\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    prior_source = {
        "url": "https://example.test/vault-principles",
        "title": "Vault principles",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }
    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [
            {"role": "user", "content": "두 Vault 분리 운영 방안을 웹에서 조사해줘."},
            {
                "role": "assistant",
                "content": "원본과 검토본을 분리합니다 [1].",
                "metadata": {
                    "web_sources": [prior_source],
                    "tool_events": [{
                        "tool": "web_fetch",
                        "command": prior_source["url"],
                        "output": (
                            "PRIOR_PRINCIPLES_BODY_SENTINEL\nSource: "
                            + prior_source["url"]
                        ),
                        "exit_code": 0,
                    }],
                },
            },
            {
                "role": "user",
                "content": "방금 답변의 기존 근거는 유지하고 최신 사례를 추가로 웹에서 찾아 보완해줘.",
            },
        ],
        max_rounds=3,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == [
        ("web_search", "2026 Obsidian knowledge vault workflow case study")
    ]
    source_events = [event for event in events if event.get("type") == "web_sources"]
    assert [source["url"] for source in source_events[-1]["data"]] == [
        "https://example.test/vault-principles",
        "https://example.test/new-vault-case",
    ]
    assert not any(event.get("type") == "web_completion_failed" for event in events)


def test_provisional_web_markdown_never_autocreates_code_document(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    rounds = {"value": 0}
    provisional = "\n".join(f"임시 정리 {index}" for index in range(35))

    async def fake_stream(_candidates, messages, **kwargs):
        rounds["value"] += 1
        if rounds["value"] == 1:
            delta = (
                f"```markdown\n{provisional}\n```\n"
                '```web_search\n{"query":"official vault workflow"}\n```'
            )
        else:
            delta = "검증된 운영 원칙만 정리했습니다 [1]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append(block.tool_type)
        if block.tool_type != "web_search":
            raise AssertionError("provisional markdown must not become a document tool")
        source = {
            "url": "https://example.test/vault",
            "title": "Vault workflow",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    "FETCHED_BODY\n\n<!-- SOURCES:"
                    + json.dumps([source])
                    + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "Vault 운영 방안을 웹에서 조사해줘."}],
        max_rounds=3,
        session_id="session-test",
        owner="alice",
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == ["web_search"]
    assert not any(event.get("type") == "doc_stream_open" for event in events)
    assert not any(
        event.get("type") == "doc_update" and event.get("title", "").startswith("Code (")
        for event in events
    )


def test_accepted_web_answer_upserts_knowledge_artifact_after_citation_gate(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    rounds = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        rounds["value"] += 1
        if rounds["value"] == 1:
            delta = '```web_search\n{"query":"official knowledge workflow"}\n```'
        else:
            delta = "# 운영 원칙\n\n검증된 자료를 기준으로 지식을 분리·갱신합니다 [1]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    async def fake_execute(block, *args, **kwargs):
        source = {
            "url": "https://example.test/knowledge",
            "title": "Knowledge workflow",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": "BODY\n\n<!-- SOURCES:" + json.dumps([source]) + " -->",
                "exit_code": 0,
            },
        )

    upserts = []

    async def fake_upsert(**kwargs):
        upserts.append(kwargs)
        return {
            "action": "create",
            "doc_id": "artifact-1",
            "title": "웹 지식 · Vault 운영 방안",
            "language": "markdown",
            "content": kwargs["answer"],
            "version": 1,
        }

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)
    monkeypatch.setattr(al, "upsert_web_knowledge_artifact", fake_upsert, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "Vault 운영 방안을 웹에서 조사해줘."}],
        max_rounds=3,
        session_id="session-test",
        owner="alice",
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert len(upserts) == 1
    assert "[출처 1](https://example.test/knowledge)" in upserts[0]["answer"]
    assert upserts[0]["query"] == "Vault 운영 방안을 웹에서 조사해줘."
    assert upserts[0]["continuation"] is False
    doc_events = [event for event in events if event.get("type") == "doc_update"]
    assert doc_events[-1]["doc_id"] == "artifact-1"
    assert not any(event.get("type") == "web_completion_failed" for event in events)


def test_textual_multi_source_web_turn_executes_both_distinct_lookups(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        if round_number["value"] == 1:
            yield "data: " + json.dumps({
                "delta": (
                    "```web_search\n{\"query\":\"OpenAI Codex app official\"}\n```\n"
                    "```web_search\n{\"query\":\"GitHub openai codex README\"}\n```\n"
                    "```web_fetch\nhttps://openai.test/codex\n```\n"
                    "```web_fetch\nhttps://github.test/openai/codex\n```"
                ),
            }) + "\n\n"
        else:
            joined_messages = "\n".join(str(message.get("content") or "") for message in messages)
            assert "OPENAI_FETCHED_BODY_SENTINEL" in joined_messages
            assert "GITHUB_README_BODY_SENTINEL" in joined_messages
            assert "VERIFIED WEB EVIDENCE MANIFEST" in joined_messages
            assert "[3] Official Codex app" in joined_messages
            assert "[4] openai/codex README" in joined_messages
            yield "data: " + json.dumps({
                "delta": "두 출처 모두 로컬 작업 위임과 코드 검토를 지원합니다 [3][4].",
            }) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append((block.tool_type, block.content))
        if block.tool_type == "web_fetch":
            is_github = "github.test" in block.content
            source = {
                "url": block.content,
                "title": "openai/codex README" if is_github else "Official Codex app",
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            }
            return (
                "web_fetch",
                {
                    "output": (
                        "GITHUB_README_BODY_SENTINEL"
                        if is_github
                        else "OPENAI_FETCHED_BODY_SENTINEL"
                    ),
                    "exit_code": 0,
                    "web_source": source,
                },
            )

        query = json.loads(block.content)["query"]
        if "GitHub" in query:
            source = {
                "url": "https://search.test/github-candidate",
                "title": "GitHub candidate",
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            }
        else:
            source = {
                "url": "https://search.test/openai-candidate",
                "title": "OpenAI candidate",
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            }
        return (
            "web_search",
            {
                "output": (
                    "[CONTENT 1] fetched evidence\n\n"
                    "```sources\n[1] " + source["title"] + "\n"
                    "    " + source["url"] + "\n```\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    chunks = _collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "두 공식 출처를 각각 웹에서 확인해 비교해줘."}],
        max_rounds=3,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    ))
    events = _events(chunks)

    assert executed == [
        ("web_search", '{"query":"OpenAI Codex app official"}'),
        ("web_search", '{"query":"GitHub openai codex README"}'),
        ("web_fetch", "https://openai.test/codex"),
        ("web_fetch", "https://github.test/openai/codex"),
    ]
    assert not any(event.get("type") == "web_completion_failed" for event in events)
    visible = "".join(event.get("delta", "") for event in events)
    assert "[출처 1](https://openai.test/codex)" in visible
    assert "[출처 2](https://github.test/openai/codex)" in visible
    source_events = [event for event in events if event.get("type") == "web_sources"]
    assert [source["url"] for source in source_events[-1]["data"]] == [
        "https://openai.test/codex",
        "https://github.test/openai/codex",
    ]


def test_unverified_primary_url_is_fetched_before_final_synthesis(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    round_number = {"value": 0}
    official_url = "https://openai.test/index/introducing-the-codex-app"

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        current = round_number["value"]
        if current == 1:
            delta = '```web_search\n{"query":"GitHub openai codex README"}\n```'
        elif current == 2:
            delta = (
                "공통 기능은 로컬 코딩 에이전트입니다 "
                f"[OpenAI 공식 소개]({official_url}) [1]."
            )
        elif current == 3:
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert official_url in joined
            assert "fetch" in joined.casefold()
            delta = f"```web_fetch\n{official_url}\n```"
        else:
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "OPENAI_PRIMARY_BODY_SENTINEL" in joined
            assert "[2] Introducing the Codex app" in joined
            delta = "두 문서 모두 로컬 코딩 에이전트 기능을 제공합니다 [1][2]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append((block.tool_type, block.content))
        if block.tool_type == "web_fetch":
            return (
                "web_fetch",
                {
                    "output": "OPENAI_PRIMARY_BODY_SENTINEL",
                    "exit_code": 0,
                    "web_source": {
                        "url": official_url,
                        "title": "Introducing the Codex app",
                        "evidence_status": "fetched",
                        "fetched": True,
                        "usable": True,
                    },
                },
            )
        source = {
            "url": "https://github.test/openai/codex",
            "title": "openai/codex README",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_search",
            {
                "output": (
                    "GITHUB_BODY_SENTINEL\n\n"
                    "```sources\n[1] openai/codex README\n"
                    "    https://github.test/openai/codex\n```\n\n"
                    "<!-- SOURCES:" + json.dumps([source]) + " -->"
                ),
                "exit_code": 0,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "공식 Codex 앱과 README를 비교해줘."}],
        max_rounds=5,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == [
        ("web_search", '{"query":"GitHub openai codex README"}'),
        ("web_fetch", official_url),
    ]
    assert not any(event.get("type") == "web_completion_failed" for event in events)
    visible = "".join(event.get("delta", "") for event in events)
    assert "[출처 1](https://github.test/openai/codex)" in visible
    assert "[출처 2](https://openai.test/index/introducing-the-codex-app)" in visible


def test_unverified_primary_urls_are_deterministically_fetched_when_model_omits_calls(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    openai_url = "https://openai.test/index/introducing-the-codex-app"
    github_url = "https://github.test/openai/codex"
    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        current = round_number["value"]
        if current == 1:
            delta = '```web_search\n{"query":"Codex official sources"}\n```'
        elif current == 2:
            delta = (
                "두 공식 원문을 직접 확인해야 합니다. "
                f"[OpenAI]({openai_url}) [GitHub]({github_url})."
            )
        elif current == 3:
            # Subscription endpoints sometimes acknowledge the completion
            # nudge but omit the textual web_fetch fences entirely.
            delta = "공식 원문을 확인하겠습니다."
        else:
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "OPENAI_PRIMARY_BODY_SENTINEL" in joined
            assert "GITHUB_PRIMARY_BODY_SENTINEL" in joined
            delta = "두 자료 모두 코딩 에이전트 기능을 설명합니다 [2][3]."
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append((block.tool_type, block.content))
        if block.tool_type == "web_search":
            source = {
                "url": "https://search.test/background",
                "title": "Background",
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            }
            return (
                "web_search",
                {
                    "output": (
                        "BACKGROUND_BODY\n\n<!-- SOURCES:"
                        + json.dumps([source])
                        + " -->"
                    ),
                    "exit_code": 0,
                },
            )
        source_url = block.content
        source = {
            "url": source_url,
            "title": "OpenAI official" if source_url == openai_url else "GitHub README",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_fetch",
            {
                "output": (
                    "OPENAI_PRIMARY_BODY_SENTINEL"
                    if source_url == openai_url
                    else "GITHUB_PRIMARY_BODY_SENTINEL"
                ),
                "exit_code": 0,
                "web_source": source,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "http://127.0.0.1:9999/v1",
        "gpt-test",
        [{"role": "user", "content": "두 공식 원문을 실제로 읽고 비교해줘."}],
        max_rounds=4,
        max_tool_calls=3,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == [
        ("web_search", '{"query":"Codex official sources"}'),
        ("web_fetch", openai_url),
        ("web_fetch", github_url),
    ]
    assert not any(event.get("type") == "web_completion_failed" for event in events)
    visible = "".join(event.get("delta", "") for event in events)
    assert "[출처 1](" + openai_url + ")" in visible
    assert "[출처 2](" + github_url + ")" in visible


def test_malformed_nested_web_citations_are_canonical_clickable_links():
    ledger = [
        {
            "url": "https://irrelevant.test/one",
            "title": "Irrelevant",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        },
        {
            "url": "https://openai.test/app",
            "title": "Official app",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        },
        {
            "url": "https://github.test/repo",
            "title": "README",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        },
    ]
    selected = [ledger[1], ledger[2]]
    malformed = (
        "공통 기능입니다. "
        "[OpenAI 공식 소개 [[2]](https://openai.test/app)] "
        "[GitHub README [[3]](https://github.test/repo)]"
    )

    normalized = al._canonicalize_web_citations(malformed, ledger, selected)

    assert normalized == (
        "공통 기능입니다. "
        "[출처 1](https://openai.test/app) "
        "[출처 2](https://github.test/repo)"
    )


def test_numeric_marker_nested_inside_markdown_link_label_is_canonicalized():
    ledger = [
        {
            "url": "https://openai.test/app",
            "title": "Official app",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        },
        {
            "url": "https://github.test/repo",
            "title": "README",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        },
    ]
    malformed = (
        "공통 기능입니다. "
        "[OpenAI 공식 소개 [1]](https://openai.test/app) "
        "[GitHub README [2]](https://github.test/repo)"
    )

    normalized = al._canonicalize_web_citations(malformed, ledger, ledger)

    assert normalized == (
        "공통 기능입니다. "
        "[출처 1](https://openai.test/app) "
        "[출처 2](https://github.test/repo)"
    )


def test_adjacent_duplicate_web_citations_collapse_to_one_link():
    ledger = [{
        "url": "https://openai.test/app",
        "title": "Official app",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }]
    duplicated = (
        "공통 기능입니다. "
        "[공식 소개](https://openai.test/app) "
        "**[출처 1](https://openai.test/app)** "
        "[1]"
    )

    normalized = al._canonicalize_web_citations(duplicated, ledger, ledger)

    assert normalized == "공통 기능입니다. [출처 1](https://openai.test/app)"


def test_parenthesized_adjacent_duplicate_web_citations_collapse_to_one_link():
    ledger = [{
        "url": "https://openai.test/app",
        "title": "Official app",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }]
    duplicated = (
        "핵심 변화입니다. "
        "([공식 발표](https://openai.test/app)) "
        "[출처 1](https://openai.test/app)"
    )

    normalized = al._canonicalize_web_citations(duplicated, ledger, ledger)

    assert normalized == "핵심 변화입니다. [출처 1](https://openai.test/app)"


def test_delta_web_batch_preserves_fetch_budget_by_running_one_discovery_search():
    blocks = [
        al.ToolBlock("web_search", '{"query":"latest Codex update"}'),
        al.ToolBlock("web_search", '{"query":"site:openai.com Codex July 2026"}'),
        al.ToolBlock("web_fetch", "https://openai.com/index/introducing-upgrades-to-codex"),
    ]

    limited = al._limit_strict_web_tool_blocks(
        blocks,
        used_native=False,
        web_completion_required=True,
        web_delta_required=True,
    )

    assert [(block.tool_type, block.content) for block in limited] == [
        ("web_search", '{"query":"latest Codex update"}'),
        ("web_fetch", "https://openai.com/index/introducing-upgrades-to-codex"),
    ]


def test_delta_fallback_search_uses_only_the_current_followup_request():
    current = "기존 두 근거는 유지하고 OpenAI 최신 공식 Codex 업데이트 한 건만 찾아줘."
    over_resolved = "\n".join([
        current,
        "방금 확인한 같은 근거만 재사용해줘.",
        "OpenAI 앱 소개와 GitHub README를 비교해줘.",
    ])

    query = al._web_fallback_query(
        current,
        over_resolved,
        web_delta_required=True,
    )

    assert query == (
        f"site:openai.com/index/ Codex Product {time.strftime('%Y')} "
        "official OpenAI latest update release"
    )
    assert "같은 근거만 재사용" not in query
    assert "GitHub README" not in query


def test_delta_fallback_search_removes_e2e_marker_before_intent_compaction():
    query = al._web_fallback_query(
        "WEB-E2E-20260804-1402-DELTA: 오늘 기준 OpenAI 공식 Codex 제품 "
        "업데이트 페이지에서 가장 최근 업데이트 한 건만 찾아줘.",
        "old context that must not leak",
        web_delta_required=True,
    )

    assert query.startswith("site:openai.com/index/ Codex Product ")
    assert "WEB-E2E" not in query
    assert "old context" not in query


def test_delta_model_search_is_rewritten_to_compact_query_before_execution():
    compact = "site:openai.com/index/ Codex Product 2026 official OpenAI latest update release"
    blocks = [
        al.ToolBlock(
            "web_search",
            json.dumps({
                "query": "기존 두 근거를 유지하고 오늘 기준 가장 최근 업데이트를 찾아줘",
                "time_filter": "day",
            }, ensure_ascii=False),
        ),
        al.ToolBlock(
            "web_fetch",
            "https://openai.com/index/codex-for-every-role-tool-workflow/",
        ),
    ]

    rewritten = al._rewrite_delta_web_search_blocks(blocks, compact)

    assert json.loads(rewritten[0].content) == {"query": compact}
    assert rewritten[1] == blocks[1]


def test_delta_query_rewrite_preserves_useful_model_reformulation():
    user_query = "방금 답변의 근거는 유지하고 최신 사례를 하나 더 찾아줘."

    assert not al._delta_query_was_compacted(user_query, user_query)
    assert not al._delta_query_was_compacted(
        "WEB-E2E-20260804-1424-DELTA: " + user_query,
        user_query,
    )
    assert al._delta_query_was_compacted(
        user_query,
        "site:openai.com/index/ Codex Product 2026 official OpenAI latest update release",
    )


def test_web_final_answer_drops_leading_methodology_promise():
    answer = (
        "두 출처의 본문을 다시 대조해 공통 기능을 추리겠습니다."
        "확인된 공통 기능은 코딩 에이전트입니다. "
        "[출처 1](https://openai.test/app)"
    )

    assert al._strip_web_methodology_prefix(answer) == (
        "확인된 공통 기능은 코딩 에이전트입니다. "
        "[출처 1](https://openai.test/app)"
    )


def test_web_final_answer_keeps_substantive_future_tense_claim():
    answer = (
        "Codex는 긴 작업을 계속 수행하겠습니다라는 문구가 아니라, "
        "지속 작업을 지원한다고 설명합니다. "
        "[출처 1](https://openai.test/app)"
    )

    assert al._strip_web_methodology_prefix(answer) == answer


def test_named_codex_comparison_resolves_exact_primary_fetch_targets():
    urls = al._required_named_web_fetch_urls(
        "OpenAI 공식 Codex 앱 소개와 GitHub openai/codex README를 실제로 읽어 비교해줘."
    )

    assert urls == [
        "https://openai.com/index/introducing-the-codex-app",
        "https://github.com/openai/codex/blob/main/README.md?plain=1",
    ]


def test_subscription_web_round_reanchors_original_request_and_fetches_named_sources(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *args, **kwargs: 10, raising=False)

    query = (
        "OpenAI 공식 Codex 앱 소개와 GitHub openai/codex README를 실제로 읽고, "
        "공통 기능 두 가지를 한국어 표로 비교해줘."
    )
    openai_url = "https://openai.com/index/introducing-the-codex-app"
    github_url = "https://github.com/openai/codex/blob/main/README.md?plain=1"
    rounds = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        rounds["value"] += 1
        current = rounds["value"]
        if current == 1:
            delta = (
                '```web_search\n{"query":"site:openai.com Codex app"}\n```\n'
                '```web_search\n{"query":"site:openai.com introducing Codex app"}\n```'
            )
        elif current == 2:
            # This is what the real subscription model returned when the tool
            # output became the last conversational input. The loop must not
            # accept or display it; it must fetch the still-missing named pages.
            delta = "무엇을 도와드릴까요?"
        else:
            conversation = [message for message in messages if message.get("role") != "system"]
            assert conversation[-1]["role"] == "user"
            assert "WEB SYNTHESIS CONTINUATION REQUEST" in conversation[-1]["content"]
            assert query in conversation[-1]["content"]
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "OPENAI_PRIMARY_BODY_SENTINEL" in joined
            assert "GITHUB_PRIMARY_BODY_SENTINEL" in joined
            delta = (
                "| 공통 기능 | OpenAI 앱 소개 | GitHub README |\n"
                "|---|---|---|\n"
                "| 로컬 에이전트 | 지원 [1] | 지원 [2] |\n"
                "| 작업 위임 | 지원 [1] | 지원 [2] |"
            )
        yield "data: " + json.dumps({"delta": delta}) + "\n\n"
        yield "data: [DONE]\n\n"

    executed = []

    async def fake_execute(block, *args, **kwargs):
        executed.append((block.tool_type, block.content))
        if block.tool_type == "web_search":
            source = {
                "url": "https://openai.com/unrelated-candidate",
                "title": "Unrelated candidate",
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            }
            return (
                "web_search",
                {
                    "output": "UNRELATED_BODY\n\n<!-- SOURCES:"
                    + json.dumps([source])
                    + " -->",
                    "exit_code": 0,
                },
            )
        source = {
            "url": block.content,
            "title": "OpenAI Codex app" if block.content == openai_url else "openai/codex README",
            "evidence_status": "fetched",
            "fetched": True,
            "usable": True,
        }
        return (
            "web_fetch",
            {
                "output": (
                    "OPENAI_PRIMARY_BODY_SENTINEL"
                    if block.content == openai_url
                    else "GITHUB_PRIMARY_BODY_SENTINEL"
                ),
                "exit_code": 0,
                "web_source": source,
            },
        )

    monkeypatch.setattr(al, "stream_llm_with_fallback", fake_stream, raising=False)
    monkeypatch.setattr(al, "execute_tool_block", fake_execute, raising=False)

    events = _events(_collect(al.stream_agent_loop(
        "https://chatgpt.com/backend-api/codex",
        "gpt-5.6-luna",
        [{"role": "user", "content": query}],
        max_rounds=3,
        max_tool_calls=4,
        relevant_tools={"web_search", "web_fetch"},
        forced_tools=set(WEB_TOOL_NAMES),
    )))

    assert executed == [
        ("web_fetch", openai_url),
        ("web_fetch", github_url),
    ]
    visible = "".join(event.get("delta", "") for event in events)
    assert "무엇을 도와드릴까요" not in visible
    assert "| 공통 기능 |" in visible
    assert not any(event.get("type") == "web_completion_failed" for event in events)
