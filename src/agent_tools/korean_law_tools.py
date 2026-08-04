"""Fail-closed Korean Law MCP bridge for normal Odysseus chat.

The model receives one bounded native tool instead of the generic MCP
inventory.  Server discovery is deterministic and the existing Contract
Review adapter pins and revalidates the exact server/tool identities before
and after each read-only call.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from collections import defaultdict
from typing import Any, Mapping

from src.tool_utils import get_mcp_manager


_ALLOWED_ARGUMENTS = frozenset({"query", "source_type", "article"})
_SERVER_PRODUCTS = frozenset({"koreanlaw", "koreanlawmcp"})
_REQUIRED_TOOLS = {
    "law": frozenset({"search_law", "get_law_text"}),
    "precedent": frozenset({"search_decisions", "get_decision_text"}),
}


def _product(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _safe_timeout() -> float:
    try:
        value = float(os.getenv("ODYSSEUS_CONTRACT_REVIEW_LAW_TIMEOUT_SECONDS", "60"))
    except (TypeError, ValueError):
        return 60.0
    if value != value or value in (float("inf"), float("-inf")):
        return 60.0
    return max(0.05, min(value, 900.0))


async def _progress(ctx: Mapping[str, Any], stage: str, message: str) -> None:
    callback = ctx.get("progress_cb")
    if not callable(callback):
        return
    result = callback({"stage": stage, "message": message})
    if inspect.isawaitable(result):
        await result


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": message, "error_code": code, "exit_code": 1}


def _select_server(manager: Any, source_type: str) -> tuple[str | None, dict[str, Any] | None]:
    try:
        inventory = manager.get_all_tools()
    except Exception:
        return None, _error("mcp_inventory_unavailable", "Korean Law MCP 도구 목록을 확인할 수 없습니다.")
    if not isinstance(inventory, list):
        return None, _error("mcp_inventory_unavailable", "Korean Law MCP 도구 목록을 확인할 수 없습니다.")

    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"names": [], "products": set()})
    for item in inventory:
        if not isinstance(item, Mapping) or item.get("is_disabled"):
            continue
        server_id = str(item.get("server_id") or "")
        name = str(item.get("name") or "")
        if not server_id or not name:
            continue
        grouped[server_id]["names"].append(name)
        grouped[server_id]["products"].add(_product(item.get("server_name") or server_id))

    required = _REQUIRED_TOOLS[source_type]
    candidates = []
    for server_id, details in grouped.items():
        products = details["products"]
        names = details["names"]
        if len(products) != 1 or not products <= _SERVER_PRODUCTS:
            continue
        if all(names.count(tool) == 1 for tool in required):
            candidates.append(server_id)

    if not candidates:
        return None, _error("mcp_not_configured", "사용 가능한 Korean Law MCP 서버를 찾지 못했습니다.")
    if len(candidates) != 1:
        return None, _error("law_server_ambiguous", "승인 가능한 Korean Law MCP 서버가 둘 이상이라 자동 선택을 중단했습니다.")
    return candidates[0], None


class KoreanLawLookupTool:
    async def execute(self, content: str, ctx: Mapping[str, Any]) -> dict[str, Any]:
        try:
            args = json.loads(content) if isinstance(content, str) and content.strip() else {}
        except (TypeError, ValueError):
            return _error("invalid_request", "법률 조회 인자는 JSON 객체여야 합니다.")
        if not isinstance(args, dict):
            return _error("invalid_request", "법률 조회 인자는 JSON 객체여야 합니다.")
        if set(args) - _ALLOWED_ARGUMENTS:
            return _error("law_argument_forbidden", "허용되지 않은 법률 조회 인자가 포함되어 있습니다.")

        query = str(args.get("query") or "").strip()
        source_type = str(args.get("source_type") or "law").strip().casefold()
        article = str(args.get("article") or "").strip()
        if not query:
            return _error("invalid_request", "조회할 정확한 법령명 또는 판례 검색어가 필요합니다.")
        if source_type not in _REQUIRED_TOOLS:
            return _error("invalid_request", "source_type은 law 또는 precedent만 허용됩니다.")
        if len(query) > 500 or len(article) > 80:
            return _error("invalid_request", "법률 조회 범위가 너무 큽니다.")
        if source_type == "precedent" and article:
            return _error("law_argument_forbidden", "판례 조회에는 조문 번호를 전달할 수 없습니다.")

        manager = get_mcp_manager()
        if manager is None:
            return _error("mcp_not_configured", "Korean Law MCP가 연결되어 있지 않습니다.")
        server_id, selection_error = _select_server(manager, source_type)
        if selection_error is not None:
            return selection_error

        await _progress(ctx, "law_search", "공식 법률 근거 후보를 조회하는 중입니다.")
        try:
            # Lazy import avoids reintroducing the agent_tools/tool_execution
            # circular import.  This adapter owns exact identity pinning,
            # TOCTOU revalidation, exact-match verification, and safe errors.
            from src.contract_review import ContractReviewError, KoreanLawAdapter
        except Exception:
            return _error("law_runtime_error", "공식 법률 근거 조회기를 불러오지 못했습니다.")

        try:
            if source_type == "law":
                tool = "search_law"
                arguments: dict[str, Any] = {"query": query, "display": 5}
                if article:
                    arguments["jo"] = article
            else:
                tool = "search_decisions"
                arguments = {
                    "domain": "precedent",
                    "query": query,
                    "display": 5,
                }
            evidence = await KoreanLawAdapter(manager, timeout=_safe_timeout()).call(
                owner=str(ctx.get("owner") or ""),
                server_id=str(server_id),
                tool=tool,
                arguments=arguments,
            )
        except ContractReviewError as exc:
            return _error(exc.code, str(exc))
        except Exception:
            return _error("law_runtime_error", "공식 법률 근거 조회 중 런타임 오류가 발생했습니다.")

        await _progress(ctx, "law_verified", "법령·판례 식별자와 공식 원문을 재검증했습니다.")
        output = str(evidence.get("output") or "").strip()
        citation_id = str(evidence.get("citation_id") or "law.go.kr")
        return {
            "stdout": f"공식 법률 근거: {citation_id}\n\n{output}",
            "stderr": "",
            "exit_code": 0,
            "evidence_type": "official_legal",
            "source": "law.go.kr",
            "citation_id": citation_id,
            "verified_tool": evidence.get("tool"),
            "discovery_tool": evidence.get("discovery_tool"),
            "descriptor_fingerprint": evidence.get("descriptor_fingerprint"),
        }
