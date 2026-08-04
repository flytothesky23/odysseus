import asyncio
import json

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
                "metadata": {"web_sources": [prior_source]},
            },
            {"role": "user", "content": "방금 확인한 같은 근거만 재사용해서 한 문장으로 설명해줘."},
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
