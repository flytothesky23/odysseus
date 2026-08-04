import json

import pytest

from src.mcp_identity import stdio_launch_identity_hash
from src.agent_tools import korean_law_tools
from src.agent_tools.korean_law_tools import KoreanLawLookupTool
from src.agent_tools import ToolBlock, function_call_to_tool_block
from src.tool_execution import execute_tool_block


class FakeLawManager:
    def __init__(self, *, server_ids=("korean-law",), inventory_error=False):
        self.server_ids = tuple(server_ids)
        self.inventory_error = inventory_error
        self.inventory_generation = 3
        self.calls = []

    def get_server_status(self, server_id):
        return {"status": "connected", "identity": f"{server_id}-identity"}

    def get_all_openai_schemas(self, disabled_map=None):
        return [
            {
                "type": "function",
                "function": {
                    "name": "mcp__unrelated__dangerous",
                    "description": "must never reach a Korean legal turn",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def get_all_tools(self, disabled_map=None):
        if self.inventory_error:
            raise RuntimeError("inventory unavailable")
        rows = []
        for server_id in self.server_ids:
            for name in (
                "search_law",
                "get_law_text",
                "search_decisions",
                "get_decision_text",
            ):
                rows.append(
                    {
                        "server_id": server_id,
                        "server_name": "Korean Law MCP",
                        "connection_identity": f"{server_id}-identity",
                        "launch_identity_hash": stdio_launch_identity_hash(
                            "npx", ["-y", "korean-law-mcp@4.9.2"]
                        ),
                        "connection_status": "connected",
                        "inventory_generation": self.inventory_generation,
                        "name": name,
                        "qualified_name": f"mcp__{server_id}__{name}",
                        "description": "read-only fixture",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                        "annotations": {"readOnlyHint": True},
                        "is_disabled": False,
                    }
                )
        return rows

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name.endswith("__search_law"):
            return {
                "stdout": (
                    "검색 결과 (총 1건):\n\n📍 정확매칭 (1건):\n"
                    "1. 대한민국헌법 [현행]\n   - 법령ID: 001444\n   - MST: 61603\n"
                ),
                "exit_code": 0,
            }
        if name.endswith("__get_law_text"):
            return {
                "stdout": "법령명: 대한민국헌법\n제10조 모든 국민은 인간으로서의 존엄과 가치를 가진다.",
                "exit_code": 0,
            }
        if name.endswith("__search_decisions"):
            return {
                "stdout": (
                    "판례 검색 결과 (총 1건, 1페이지):\n\n"
                    "[12345] 손해배상\n  사건번호: 2020다12345\n  법원: 대법원\n"
                ),
                "exit_code": 0,
            }
        return {
            "stdout": (
                "=== 손해배상 ===\n\n기본 정보:\n  사건번호: 2020다12345\n"
                "판결요지:\n검증된 판례"
            ),
            "exit_code": 0,
        }


@pytest.mark.asyncio
async def test_agent_law_lookup_verifies_search_result_with_official_body(monkeypatch):
    manager = FakeLawManager()
    monkeypatch.setattr(korean_law_tools, "get_mcp_manager", lambda: manager)

    result = await KoreanLawLookupTool().execute(
        json.dumps({"query": "대한민국헌법", "source_type": "law", "article": "제10조"}),
        {"owner": "alice"},
    )

    assert result["exit_code"] == 0
    assert result["evidence_type"] == "official_legal"
    assert result["source"] == "law.go.kr"
    assert result["citation_id"] == "law.go.kr · 대한민국헌법 · MST 61603"
    assert "제10조" in result["stdout"]
    assert manager.calls == [
        (
            "mcp__korean-law__search_law",
            {"query": "대한민국헌법", "display": 5, "jo": "제10조"},
        ),
        ("mcp__korean-law__get_law_text", {"mst": "61603", "jo": "제10조"}),
    ]


@pytest.mark.asyncio
async def test_agent_law_lookup_uses_precedent_verification_pair(monkeypatch):
    manager = FakeLawManager()
    monkeypatch.setattr(korean_law_tools, "get_mcp_manager", lambda: manager)

    result = await KoreanLawLookupTool().execute(
        json.dumps({"query": "지급 지연 손해배상", "source_type": "precedent"}),
        {"owner": "alice"},
    )

    assert result["exit_code"] == 0
    assert result["citation_id"] == "law.go.kr · 2020다12345 · ID 12345"
    assert manager.calls == [
        (
            "mcp__korean-law__search_decisions",
            {"domain": "precedent", "query": "지급 지연 손해배상", "display": 5},
        ),
        (
            "mcp__korean-law__get_decision_text",
            {"domain": "precedent", "id": "12345"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_law_lookup_fails_closed_on_inventory_error_or_ambiguity(monkeypatch):
    for manager, code in (
        (FakeLawManager(inventory_error=True), "mcp_inventory_unavailable"),
        (FakeLawManager(server_ids=("law-one", "law-two")), "law_server_ambiguous"),
    ):
        monkeypatch.setattr(
            korean_law_tools, "get_mcp_manager", lambda manager=manager: manager
        )
        result = await KoreanLawLookupTool().execute(
            json.dumps({"query": "대한민국헌법", "source_type": "law"}),
            {"owner": "alice"},
        )

        assert result["exit_code"] == 1
        assert result["error_code"] == code
        assert manager.calls == []


@pytest.mark.asyncio
async def test_agent_law_lookup_rejects_same_named_server_with_wrong_launch_identity(monkeypatch):
    manager = FakeLawManager()
    original = manager.get_all_tools

    def swapped_inventory(disabled_map=None):
        rows = original(disabled_map)
        for row in rows:
            row["launch_identity_hash"] = stdio_launch_identity_hash(
                "node", ["/tmp/untrusted-korean-law-server.js"]
            )
        return rows

    manager.get_all_tools = swapped_inventory
    monkeypatch.setattr(korean_law_tools, "get_mcp_manager", lambda: manager)
    result = await KoreanLawLookupTool().execute(
        json.dumps({"query": "대한민국헌법", "source_type": "law"}),
        {"owner": "alice"},
    )
    assert result["exit_code"] == 1
    assert result["error_code"] == "law_server_forbidden"
    assert manager.calls == []


@pytest.mark.asyncio
async def test_agent_law_lookup_rejects_unbounded_or_unknown_arguments(monkeypatch):
    manager = FakeLawManager()
    monkeypatch.setattr(korean_law_tools, "get_mcp_manager", lambda: manager)

    result = await KoreanLawLookupTool().execute(
        json.dumps(
            {
                "query": "대한민국헌법",
                "source_type": "law",
                "server_id": "attacker-controlled",
            }
        ),
        {"owner": "alice"},
    )

    assert result["exit_code"] == 1
    assert result["error_code"] == "law_argument_forbidden"
    assert manager.calls == []


def test_native_function_call_converts_to_bounded_law_tool_block():
    block = function_call_to_tool_block(
        "korean_law_lookup",
        json.dumps({"query": "대한민국헌법", "source_type": "law", "article": "제10조"}),
    )

    assert block == ToolBlock(
        "korean_law_lookup",
        json.dumps({"query": "대한민국헌법", "source_type": "law", "article": "제10조"}),
    )


@pytest.mark.asyncio
async def test_tool_dispatch_preserves_owner_and_returns_verified_evidence(monkeypatch):
    manager = FakeLawManager()
    monkeypatch.setattr(korean_law_tools, "get_mcp_manager", lambda: manager)

    desc, result = await execute_tool_block(
        ToolBlock(
            "korean_law_lookup",
            json.dumps({"query": "대한민국헌법", "source_type": "law"}),
        ),
        owner="alice",
    )

    assert desc == "korean_law_lookup"
    assert result["exit_code"] == 0
    assert result["evidence_type"] == "official_legal"


@pytest.mark.asyncio
async def test_korean_legal_agent_turn_exposes_only_safe_evidence_tool(monkeypatch):
    import src.agent_loop as agent_loop

    manager = FakeLawManager()
    monkeypatch.setattr(agent_loop, "get_mcp_manager", lambda: manager)
    monkeypatch.setattr(korean_law_tools, "get_mcp_manager", lambda: manager)
    monkeypatch.setattr(agent_loop, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(agent_loop, "estimate_tokens", lambda *args, **kwargs: 10)

    sent_schema_names = []
    round_number = {"value": 0}

    async def fake_stream(_candidates, messages, **kwargs):
        round_number["value"] += 1
        sent_schema_names.append(
            {
                tool.get("function", {}).get("name") or tool.get("name")
                for tool in (kwargs.get("tools") or [])
            }
        )
        if round_number["value"] == 1:
            yield "data: " + json.dumps(
                {
                    "delta": (
                        "공식 법령 조회 도구를 사용할 수 없어 확인하지 못했습니다. "
                        "곧 다시 시도하겠습니다."
                    )
                }
            ) + "\n\n"
            yield "data: " + json.dumps(
                {
                    "type": "tool_calls",
                    "calls": [
                        {
                            "name": "korean_law_lookup",
                            "arguments": json.dumps(
                                {
                                    "query": "대한민국헌법",
                                    "source_type": "law",
                                    "article": "제10조",
                                }
                            ),
                        }
                    ],
                }
            ) + "\n\n"
        else:
            yield "data: " + json.dumps(
                {
                    "delta": (
                        "공식 근거: law.go.kr · 대한민국헌법 · MST 61603. "
                        "제10조는 인간의 존엄과 가치를 규정합니다. "
                        "모델 해석: 계약 조항과의 직접 관련성은 별도로 검토해야 합니다. "
                        "불확실성: 구체적 사실관계는 제공되지 않았습니다."
                    )
                }
            ) + "\n\n"
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream)

    chunks = [
        chunk
        async for chunk in agent_loop.stream_agent_loop(
            "https://api.openai.com/v1",
            "gpt-test",
            [{"role": "user", "content": "대한민국헌법 제10조의 공식 법률 근거를 확인해줘"}],
            max_rounds=3,
            relevant_tools={
                "bash",
                "manage_memory",
                "mcp__unrelated__dangerous",
                "korean_law_lookup",
            },
        )
    ]

    visible_text = "".join(
        str(json.loads(chunk[6:]).get("delta") or "")
        for chunk in chunks
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]")
    )
    assert "대한민국헌법" in visible_text
    assert "제10조" in visible_text
    assert "사용할 수 없어" not in visible_text
    assert "law.go.kr" in visible_text
    assert sum('"type": "tool_start"' in chunk for chunk in chunks) == 1
    assert manager.calls[:2] == [
        (
            "mcp__korean-law__search_law",
            {"query": "대한민국헌법", "display": 5, "jo": "제10조"},
        ),
        ("mcp__korean-law__get_law_text", {"mst": "61603", "jo": "제10조"}),
    ]
    assert sent_schema_names
    assert "korean_law_lookup" in sent_schema_names[0]
    assert "bash" not in sent_schema_names[0]
    assert "manage_memory" not in sent_schema_names[0]
    assert "mcp__unrelated__dangerous" not in sent_schema_names[0]
    assert sent_schema_names[1] == set()
