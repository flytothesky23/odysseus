import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from routes import chat_helpers, chat_routes
from src.agent_tools import ToolBlock
from src.contract_review import ContractReviewError, contract_review_tool_policy, extract_contract_review_result
from src.tool_execution import execute_tool_block


def _route(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"{method} {path} route not registered")


def test_contract_review_question_is_redacted_from_events_and_mismatch_logs(monkeypatch, caplog):
    events = []
    webhook = SimpleNamespace(
        fire_and_forget=lambda name, payload: events.append((name, payload)),
    )
    monkeypatch.setattr(chat_helpers, "effective_user", lambda request: "alice")
    monkeypatch.setattr("src.event_bus.fire_event", lambda *args, **kwargs: None)

    secret_question = "원문 계약의 비공개 질문 전문"
    chat_helpers.fire_message_event(
        SimpleNamespace(),
        webhook,
        "session-1",
        SimpleNamespace(model="selected-model"),
        secret_question,
        redact_message=True,
    )
    repaired = chat_routes._ensure_current_request_is_latest_user(
        [{"role": "user", "content": "different"}],
        secret_question,
        redact_log=True,
    )

    assert events[0][1]["message"] == "[sensitive content omitted]"
    assert repaired[-1]["content"] == secret_question
    assert secret_question not in caplog.text


def test_inactive_chat_stream_status_is_an_idle_success(monkeypatch):
    monkeypatch.setattr(chat_routes, "_verify_session_owner", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_routes.agent_runs, "is_active", lambda _session_id: False)
    router = chat_routes.setup_chat_routes(*[MagicMock() for _ in range(6)])
    target = _route(router, "/api/chat/stream_status/{session_id}", "GET")

    result = asyncio.run(target(SimpleNamespace(), "session-1"))

    assert result == {"status": "idle", "detached": False}


@pytest.mark.asyncio
async def test_contract_evidence_enters_existing_context_before_compaction(monkeypatch):
    captured = {}

    async def fake_preprocess(*args, **kwargs):
        message = args[1]
        return chat_helpers.PreprocessedMessage(
            enhanced_message=message, user_content=message, text_for_context=message,
            youtube_transcripts=[], attachment_meta=[],
        )

    async def fake_compact(sess, endpoint_url, model, messages, headers, owner=None):
        captured["messages"] = messages
        return messages, 8192, False

    monkeypatch.setattr(chat_helpers, "preprocess", fake_preprocess)
    monkeypatch.setattr(chat_helpers, "extract_preset", lambda *a, **k: chat_helpers.PresetInfo(0.2, 1024, None, None))
    monkeypatch.setattr(chat_helpers, "add_user_message", lambda sess, _h, p, incognito=False: sess.messages.append({"role": "user", "content": p.user_content}))
    monkeypatch.setattr(chat_helpers, "load_prefs_for_user", lambda owner: {})
    monkeypatch.setattr(chat_helpers, "effective_user", lambda request: "alice")
    monkeypatch.setattr(chat_helpers, "_normalize_model_id_from_cache", lambda sess: None)
    monkeypatch.setattr(chat_helpers, "normalize_model_id", lambda *a, **k: None)
    monkeypatch.setattr(chat_helpers, "maybe_compact", fake_compact)
    monkeypatch.setattr(chat_helpers, "trim_for_context", lambda messages, context_length: messages)

    sess = SimpleNamespace(endpoint_url="http://model.test/v1", model="selected-model", headers={}, messages=[], history=[])
    sess.get_context_messages = lambda: list(sess.messages)
    processor = SimpleNamespace(build_context_preface=lambda **kwargs: ([], [], []), _last_used_memories=[])
    evidence = {
        "schema": "contract-review-context.v2", "strategy": "reuse",
        "evidence_fingerprint": "e" * 64,
        "vault_note_evidence": [{"path": "Agreement.md", "content": "bounded quote"}],
        "local_document_evidence": [], "official_legal_evidence": [],
    }

    context = await chat_helpers.build_chat_context(
        sess, SimpleNamespace(), SimpleNamespace(), processor,
        message="같은 근거로 다시 검토해줘", session_id="session-1",
        preset_id="contract_review", agent_mode=True,
        additional_untrusted_context=evidence,
    )
    serialized = str(captured["messages"])
    assert "contract review evidence" in serialized.lower()
    assert "bounded quote" in serialized
    assert context.context_length == 8192
    assert sess.model == "selected-model"


def test_contract_review_executor_blocks_unknown_generic_mcp_namespace(monkeypatch):
    called = False

    class Manager:
        async def call_tool(self, *args, **kwargs):
            nonlocal called
            called = True
            return {"stdout": "should not run", "exit_code": 0}

    monkeypatch.setattr("src.tool_execution.get_mcp_manager", lambda: Manager())
    desc, result = asyncio.run(execute_tool_block(
        ToolBlock("mcp__new-server__new-read-tool", "{}"),
        owner="alice", tool_policy=contract_review_tool_policy(),
    ))
    assert desc.endswith("BLOCKED")
    assert result["exit_code"] == 1
    assert called is False


def test_model_result_requires_one_exact_fence_and_server_owned_metrics():
    payload = {
        "schema_version": "contract-review.v2",
        "review_summary": {"text": "Summary"},
        "local_document_evidence": [],
        "vault_note_evidence": [],
        "official_legal_evidence": [],
        "model_interpretation": {"text": "Interpretation", "evidence_ids": []},
        "uncertainty_and_follow_up": ["Verify"],
    }
    fenced = "```contract-review-result\n" + json.dumps(payload) + "\n```"
    result = extract_contract_review_result(
        fenced,
        session_id="session-1",
        evidence_fingerprint="e" * 64,
        metrics={"usage_source": "actual", "input_tokens": 10, "output_tokens": 4},
        evidence_context={
            "local_document_evidence": [],
            "vault_note_evidence": [],
            "official_legal_evidence": [],
        },
    )
    assert result["session_id"] == "session-1"
    assert result["usage"] == {"source": "actual", "input_tokens": 10, "output_tokens": 4}
    assert result["generated_at"].endswith("+09:00")

    with pytest.raises(ContractReviewError):
        extract_contract_review_result(
            "extra prose\n" + fenced,
            session_id="session-1",
            evidence_fingerprint="e" * 64,
        )


def test_model_cannot_invent_or_relabel_verified_evidence():
    payload = {
        "schema_version": "contract-review.v2",
        "review_summary": {"text": "Summary"},
        "local_document_evidence": [],
        "vault_note_evidence": [{
            "id": "invented", "evidence_type": "vault_note",
            "path": "Agreement.md", "verification_state": "verified",
        }],
        "official_legal_evidence": [],
        "model_interpretation": {"text": "Interpretation", "evidence_ids": []},
        "uncertainty_and_follow_up": ["Verify"],
    }
    fenced = "```contract-review-result\n" + json.dumps(payload) + "\n```"
    with pytest.raises(ContractReviewError) as exc:
        extract_contract_review_result(
            fenced,
            session_id="session-1",
            evidence_fingerprint="e" * 64,
            evidence_context={
                "local_document_evidence": [],
                "vault_note_evidence": [{
                    "id": "verified-note", "evidence_type": "vault_note",
                    "path": "Agreement.md", "verification_state": "verified",
                }],
                "official_legal_evidence": [],
            },
        )
    assert exc.value.code == "unsupported_evidence"


def test_model_interpretation_cannot_cite_an_invented_evidence_id():
    payload = {
        "schema_version": "contract-review.v2",
        "review_summary": {"text": "Summary"},
        "local_document_evidence": [],
        "vault_note_evidence": [],
        "official_legal_evidence": [],
        "model_interpretation": {"text": "Interpretation", "evidence_ids": ["invented"]},
        "uncertainty_and_follow_up": ["Verify"],
    }
    fenced = "```contract-review-result\n" + json.dumps(payload) + "\n```"
    with pytest.raises(ContractReviewError) as exc:
        extract_contract_review_result(
            fenced,
            session_id="session-1",
            evidence_fingerprint="e" * 64,
            evidence_context={
                "local_document_evidence": [],
                "vault_note_evidence": [],
                "official_legal_evidence": [],
            },
        )
    assert exc.value.code == "unsupported_evidence"


def test_actual_codex_interpretation_array_is_normalized_without_inventing_citations():
    """The real Codex provider may express multiple interpretations as an array."""

    local_id = "local-verified"
    note_id = "note-verified"
    law_id = "law-verified"
    payload = {
        "schema_version": "contract-review.v2",
        "review_summary": {"content": "Two bounded risks were found."},
        "local_document_evidence": [{
            "id": local_id,
            "evidence_type": "local_document",
            "path": "documents/contract.pdf",
            "verification_state": "verified",
            "content": "Payment is due within thirty days after acceptance.",
        }],
        "vault_note_evidence": [{
            "id": note_id,
            "evidence_type": "vault_note",
            "path": "Agreements/Main.md",
            "verification_state": "verified",
            "content": "검수 완료 후 삼십 일 이내에 대금을 지급한다.",
        }],
        "official_legal_evidence": [{
            "id": law_id,
            "evidence_type": "official_legal",
            "source": "law.go.kr",
            "verification_state": "verified",
            "citation_id": "law.go.kr · 대한민국헌법 · MST 61603",
            "content": "법령명: 대한민국헌법",
        }],
        "model_interpretation": [
            {"risk": "검수 완료 시점 불명확", "analysis": "기산점 분쟁 위험이 있다."},
            {"risk": "지급 지연 보호수단 부족", "analysis": "후속 조치를 확인해야 한다."},
        ],
        "uncertainty_and_follow_up": [{
            "issue": "직접 적용 법령 미확인",
            "detail": "제공된 공식 근거의 직접성이 제한된다.",
            "follow_up": "관련 현행 조문을 추가 확인한다.",
        }],
    }
    result = extract_contract_review_result(
        "```contract-review-result\n" + json.dumps(payload, ensure_ascii=False) + "\n```",
        session_id="session-actual-codex",
        evidence_fingerprint="e" * 64,
        metrics={"usage_source": "actual", "input_tokens": 2180, "output_tokens": 1139},
        evidence_context={
            "local_document_evidence": [payload["local_document_evidence"][0]],
            "vault_note_evidence": [payload["vault_note_evidence"][0]],
            "official_legal_evidence": [payload["official_legal_evidence"][0]],
        },
    )

    interpretation = result["blocks"]["model_interpretation"]
    assert interpretation["items"] == payload["model_interpretation"]
    assert interpretation["evidence_ids"] == []
    assert result["usage"] == {"source": "actual", "input_tokens": 2180, "output_tokens": 1139}


def test_interpretation_array_still_rejects_an_invented_item_evidence_id():
    payload = {
        "schema_version": "contract-review.v2",
        "review_summary": {"text": "Summary"},
        "local_document_evidence": [],
        "vault_note_evidence": [],
        "official_legal_evidence": [],
        "model_interpretation": [{
            "risk": "Unsupported",
            "analysis": "Invented citation",
            "evidence_ids": ["invented"],
        }],
        "uncertainty_and_follow_up": ["Verify"],
    }
    with pytest.raises(ContractReviewError) as exc:
        extract_contract_review_result(
            "```contract-review-result\n" + json.dumps(payload) + "\n```",
            session_id="session-1",
            evidence_fingerprint="e" * 64,
            evidence_context={
                "local_document_evidence": [],
                "vault_note_evidence": [],
                "official_legal_evidence": [],
            },
        )
    assert exc.value.code == "unsupported_evidence"


def test_official_citation_identity_is_server_owned_when_model_omits_or_changes_it():
    canonical = {
        "id": "law-verified",
        "evidence_type": "official_legal",
        "source": "law.go.kr",
        "citation_id": "law.go.kr · 대한민국헌법 · MST 61603",
        "verification_state": "verified",
    }
    payload = {
        "schema_version": "contract-review.v2",
        "review_summary": {"text": "Summary"},
        "local_document_evidence": [],
        "vault_note_evidence": [],
        "official_legal_evidence": [{
            key: value for key, value in canonical.items() if key != "citation_id"
        }],
        "model_interpretation": {"text": "Interpretation", "evidence_ids": [canonical["id"]]},
        "uncertainty_and_follow_up": ["Verify"],
    }
    kwargs = {
        "session_id": "session-1",
        "evidence_fingerprint": "e" * 64,
        "evidence_context": {
            "local_document_evidence": [],
            "vault_note_evidence": [],
            "official_legal_evidence": [canonical],
        },
    }

    result = extract_contract_review_result(
        "```contract-review-result\n" + json.dumps(payload, ensure_ascii=False) + "\n```",
        **kwargs,
    )
    assert result["blocks"]["official_legal_evidence"][0]["citation_id"] == canonical["citation_id"]

    payload["official_legal_evidence"][0]["citation_id"] = "law.go.kr · forged · MST 0"
    with pytest.raises(ContractReviewError) as exc:
        extract_contract_review_result(
            "```contract-review-result\n" + json.dumps(payload, ensure_ascii=False) + "\n```",
            **kwargs,
        )
    assert exc.value.code == "unsupported_evidence"
