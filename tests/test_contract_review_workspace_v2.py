import asyncio
import errno
import json
import os
from pathlib import Path

import pytest

from src.contract_review import (
    CONTRACT_REVIEW_BLOCKS,
    KORDOC_READ_ONLY_TOOLS,
    KOREAN_LAW_READ_ONLY_TOOLS,
    ContractReviewError,
    ContractReviewJobManager,
    ContractReviewWorkspaceService,
    KordocAdapter,
    KoreanLawAdapter,
    build_contract_review_markdown,
    build_contract_review_turn_context,
    confine_workspace_file,
    contract_review_tool_policy,
    validate_contract_review_result,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def contract_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    vault = workspace / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    _write(
        vault / "기본 계약.md",
        """---
title: 용역 기본 계약서
aliases: [MSA, 마스터 계약]
---
# 계약
대금은 검수 후 삼십 일 이내 지급한다.
""",
    )
    _write(
        vault / "amendments" / "Liability.md",
        """---
title: Liability Side Letter
aliases:
  - 책임 제한
  - Special Terms
---
# Side Letter
The liability cap is limited to the annual fee.
""",
    )
    _write(vault / ".private" / "credential.md", "secret")
    (vault / "ignored.txt").write_text("not markdown", encoding="utf-8")
    return workspace, vault


def _index(service, workspace, owner="alice"):
    return service.index_vault(owner, str(workspace), "vault")


def test_metadata_index_and_korean_search_read_no_bodies(contract_workspace, monkeypatch):
    workspace, _vault = contract_workspace
    service = ContractReviewWorkspaceService(max_body_candidates=1)
    calls = []
    original = service._read_note_body
    monkeypatch.setattr(service, "_read_note_body", lambda *a, **k: (calls.append(a[2]), original(*a, **k))[1])

    indexed = _index(service, workspace)
    assert [note["path"] for note in indexed["notes"]] == [
        "amendments/Liability.md",
        "기본 계약.md",
    ]
    assert str(workspace) not in json.dumps(indexed, ensure_ascii=False)

    cases = {
        "기본 계약.md": "filename",
        "용역 기본 계약서": "title",
        "amendments": "path",
        "책임 제한": "aliases",
    }
    for query, _field in cases.items():
        result = service.search("alice", indexed["snapshot_id"], indexed["vault_id"], query)
        assert result["body_read_count"] == 0
        assert result["results"]
    assert calls == []


def test_bounded_body_search_and_delta_follow_up(contract_workspace, monkeypatch):
    workspace, _vault = contract_workspace
    service = ContractReviewWorkspaceService(max_body_candidates=1, max_body_chars=4000)
    indexed = _index(service, workspace)
    calls = []
    original = service._read_note_body

    def spy(owner, snapshot, relative_path, *args, **kwargs):
        calls.append(relative_path)
        return original(owner, snapshot, relative_path, *args, **kwargs)

    monkeypatch.setattr(service, "_read_note_body", spy)
    body = service.search(
        "alice",
        indexed["snapshot_id"],
        indexed["vault_id"],
        "liability cap",
        include_body=True,
        candidate_paths=["amendments/Liability.md", "기본 계약.md"],
    )
    assert body["body_read_count"] == 1
    assert calls == ["amendments/Liability.md"]

    first = build_contract_review_turn_context(
        service,
        owner="alice",
        session_id="session-1",
        snapshot_id=indexed["snapshot_id"],
        vault_id=indexed["vault_id"],
        selected_paths=["기본 계약.md"],
    )
    reused = build_contract_review_turn_context(
        service,
        owner="alice",
        session_id="session-1",
        snapshot_id=indexed["snapshot_id"],
        vault_id=indexed["vault_id"],
        selected_paths=["기본 계약.md"],
    )
    delta = build_contract_review_turn_context(
        service,
        owner="alice",
        session_id="session-1",
        snapshot_id=indexed["snapshot_id"],
        vault_id=indexed["vault_id"],
        selected_paths=["기본 계약.md", "amendments/Liability.md"],
    )
    assert first["scope"]["strategy"] == "fresh"
    assert reused["scope"]["strategy"] == "reuse"
    assert delta["scope"]["strategy"] == "delta"
    assert delta["scope"]["delta_paths"] == ["amendments/Liability.md"]
    assert len(reused["evidence"]) == 1
    assert len(delta["evidence"]) == 2
    # Initial selected body, no reread for reuse, only one added body for delta.
    assert calls[-2:] == ["기본 계약.md", "amendments/Liability.md"]


def test_owner_scope_and_auth_disabled_single_owner(contract_workspace):
    workspace, _vault = contract_workspace
    service = ContractReviewWorkspaceService()
    alice = _index(service, workspace, owner="alice")

    with pytest.raises(ContractReviewError) as exc:
        service.search("bob", alice["snapshot_id"], alice["vault_id"], "계약")
    assert exc.value.code == "snapshot_unavailable"

    single = _index(service, workspace, owner="")
    assert service.search("", single["snapshot_id"], single["vault_id"], "계약")["results"]
    with pytest.raises(ContractReviewError):
        service.open_note("alice", single["snapshot_id"], single["vault_id"], "기본 계약.md")


def test_stale_deleted_root_swap_and_scope_escape_fail_closed(contract_workspace, tmp_path):
    workspace, vault = contract_workspace
    service = ContractReviewWorkspaceService()
    indexed = _index(service, workspace)

    with pytest.raises(ContractReviewError) as exc:
        service.open_note("alice", indexed["snapshot_id"], indexed["vault_id"], "../outside.md")
    assert exc.value.code == "outside_scope"

    note = vault / "기본 계약.md"
    note.write_text(note.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
    os.utime(note, None)
    with pytest.raises(ContractReviewError) as exc:
        service.open_note("alice", indexed["snapshot_id"], indexed["vault_id"], "기본 계약.md")
    assert exc.value.code == "stale_evidence"

    note.unlink()
    with pytest.raises(ContractReviewError) as exc:
        service.open_note("alice", indexed["snapshot_id"], indexed["vault_id"], "기본 계약.md")
    assert exc.value.code == "stale_evidence"

    moved = workspace / "old-vault"
    vault.rename(moved)
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    with pytest.raises(ContractReviewError) as exc:
        service.search("alice", indexed["snapshot_id"], indexed["vault_id"], "계약")
    assert exc.value.code == "vault_changed"


def test_symlink_absolute_and_credentials_never_become_evidence(contract_workspace, tmp_path):
    workspace, vault = contract_workspace
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"fixture")
    document = workspace / "documents" / "contract.pdf"
    document.parent.mkdir()
    document.write_bytes(b"fixture")
    env_file = workspace / ".env"
    env_file.write_text("REDACTED", encoding="utf-8")
    escape = workspace / "documents" / "escape.pdf"
    try:
        escape.symlink_to(outside)
        (vault / "escape.md").symlink_to(tmp_path / "outside.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")

    assert confine_workspace_file(str(workspace), "documents/contract.pdf") == str(document.resolve())
    for raw in (str(outside), "../outside.pdf", "documents/escape.pdf", ".env"):
        with pytest.raises(ContractReviewError):
            confine_workspace_file(str(workspace), raw)
    indexed = _index(ContractReviewWorkspaceService(), workspace)
    assert "escape.md" not in {note["path"] for note in indexed["notes"]}


class FakeMcpManager:
    def __init__(self, *, kind="kordoc", server_name=None, result=None, status="connected", delay=0):
        self.kind = kind
        self.server_name = server_name or kind
        self.status = status
        self.result = result if result is not None else {"stdout": "# Parsed fixture", "exit_code": 0}
        self.delay = delay
        self.calls = []
        self.inventory_generation = 7
        self.raise_inventory = False
        self.schema_version = 1

    def get_server_status(self, server_id):
        return {
            "status": self.status,
            "identity": f"{self.kind}-local",
            "tool_count": 1,
        }

    def get_all_tools(self, disabled_map=None):
        if self.raise_inventory:
            raise RuntimeError("inventory unavailable")
        tool = "parse_document" if self.kind == "kordoc" else "search_law"
        schema = {
            "type": "object",
            "properties": {"file_path" if self.kind == "kordoc" else "query": {"type": "string"}},
            "x-version": self.schema_version,
        }
        return [{
            "server_id": self.kind,
            "server_name": self.server_name,
            "connection_identity": f"{self.kind}-local",
            "connection_status": self.status,
            "inventory_generation": self.inventory_generation,
            "name": tool,
            "qualified_name": f"mcp__{self.kind}__{tool}",
            "description": "read-only fixture",
            "input_schema": schema,
            "annotations": {"readOnlyHint": True},
            "is_disabled": False,
        }]

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_kordoc_pins_identity_and_revalidates_path_before_and_after_call(contract_workspace):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "contract.pdf"
    doc.parent.mkdir()
    doc.write_bytes(b"fixture")
    manager = FakeMcpManager(delay=0.01)
    adapter = KordocAdapter(manager, timeout=1)
    admission = adapter.admit(
        owner="alice", server_id="kordoc", tool="parse_document",
        workspace=str(workspace), relative_path="documents/contract.pdf", arguments={},
    )
    task = asyncio.create_task(adapter.execute(admission))
    await asyncio.sleep(0)
    manager.schema_version = 2
    with pytest.raises(ContractReviewError) as exc:
        await task
    assert exc.value.code == "mcp_identity_changed"
    assert manager.calls == []


@pytest.mark.asyncio
async def test_kordoc_inventory_allowlist_timeout_and_parser_failures(contract_workspace):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "contract.hwp"
    doc.parent.mkdir()
    doc.write_bytes(b"fixture")

    manager = FakeMcpManager()
    manager.raise_inventory = True
    with pytest.raises(ContractReviewError) as exc:
        KordocAdapter(manager).admit(
            owner="alice", server_id="kordoc", tool="parse_document",
            workspace=str(workspace), relative_path="documents/contract.hwp", arguments={},
        )
    assert exc.value.code == "mcp_inventory_unavailable"

    for forbidden in ("fill_form", "compare_documents"):
        with pytest.raises(ContractReviewError) as exc:
            KordocAdapter(FakeMcpManager()).admit(
                owner="alice", server_id="kordoc", tool=forbidden,
                workspace=str(workspace), relative_path="documents/contract.hwp", arguments={},
            )
        assert exc.value.code == "kordoc_tool_forbidden"

    with pytest.raises(ContractReviewError) as exc:
        await KordocAdapter(FakeMcpManager(delay=0.05), timeout=0.001).call(
            owner="alice", server_id="kordoc", tool="parse_document",
            workspace=str(workspace), relative_path="documents/contract.hwp", arguments={},
        )
    assert exc.value.code == "mcp_timeout"

    with pytest.raises(ContractReviewError) as exc:
        await KordocAdapter(FakeMcpManager(result={"stderr": "parser failed", "exit_code": 1})).call(
            owner="alice", server_id="kordoc", tool="parse_document",
            workspace=str(workspace), relative_path="documents/contract.hwp", arguments={},
        )
    assert exc.value.code == "parser_error"


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", [".pdf", ".docx", ".xlsx", ".hwp", ".hwpx"])
async def test_kordoc_supported_fixtures_are_parsed_read_only(contract_workspace, suffix):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / f"fixture{suffix}"
    doc.parent.mkdir(exist_ok=True)
    doc.write_bytes(b"non-identifying fixture")
    manager = FakeMcpManager(result={"stdout": f"parsed {suffix}", "exit_code": 0})

    result = await KordocAdapter(manager, timeout=1).call(
        owner="alice", server_id="kordoc", tool="parse_document",
        workspace=str(workspace), relative_path=f"documents/fixture{suffix}", arguments={},
    )

    assert result["state"] == "completed"
    assert result["document"] == f"documents/fixture{suffix}"
    assert manager.calls[0][0] == "mcp__kordoc__parse_document"
    assert str(workspace) not in json.dumps(result)


def test_cloud_placeholder_is_not_accepted_as_evidence(contract_workspace, monkeypatch):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "placeholder.pdf"
    doc.parent.mkdir(exist_ok=True)
    doc.write_bytes(b"fixture")
    real_open = open

    def placeholder_open(path, *args, **kwargs):
        if os.path.realpath(path) == str(doc.resolve()) and args and args[0] == "rb":
            raise OSError(errno.EAGAIN, "not downloaded")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", placeholder_open)
    with pytest.raises(ContractReviewError) as exc:
        confine_workspace_file(str(workspace), "documents/placeholder.pdf")
    assert exc.value.code == "cloud_placeholder_unavailable"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("not_configured", "mcp_not_configured"),
        ("disabled", "mcp_disabled"),
        ("disconnected", "mcp_disconnected"),
        ("error", "mcp_runtime_error"),
    ],
)
def test_kordoc_runtime_diagnostics_are_typed(contract_workspace, status, expected):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "contract.pdf"
    doc.parent.mkdir(exist_ok=True)
    doc.write_bytes(b"fixture")
    with pytest.raises(ContractReviewError) as exc:
        KordocAdapter(FakeMcpManager(status=status)).admit(
            owner="alice", server_id="kordoc", tool="parse_document",
            workspace=str(workspace), relative_path="documents/contract.pdf", arguments={},
        )
    assert exc.value.code == expected


def test_kordoc_rejects_same_named_tool_from_unapproved_server(contract_workspace):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "contract.pdf"
    doc.parent.mkdir(exist_ok=True)
    doc.write_bytes(b"fixture")
    with pytest.raises(ContractReviewError) as exc:
        KordocAdapter(FakeMcpManager(server_name="generic-parser")).admit(
            owner="alice", server_id="kordoc", tool="parse_document",
            workspace=str(workspace), relative_path="documents/contract.pdf", arguments={},
        )
    assert exc.value.code == "kordoc_server_forbidden"


@pytest.mark.asyncio
async def test_korean_law_official_evidence_and_diagnostics():
    ok = FakeMcpManager(
        kind="korean-law",
        result={"stdout": "법령명: 대한민국헌법\n법령ID: 1\n시행일: 1988-02-25", "exit_code": 0},
    )
    evidence = await KoreanLawAdapter(ok, timeout=1).call(
        owner="alice", server_id="korean-law", tool="search_law",
        arguments={"query": "대한민국헌법", "display": 1},
    )
    assert evidence["state"] == "completed"
    assert evidence["evidence_type"] == "official_legal"
    assert evidence["source"] == "law.go.kr"
    assert "대한민국헌법" in evidence["output"]

    with pytest.raises(ContractReviewError) as exc:
        await KoreanLawAdapter(FakeMcpManager(kind="korean-law", result={"stderr": "429", "exit_code": 1})).call(
            owner="alice", server_id="korean-law", tool="search_law",
            arguments={"query": "대한민국헌법"},
        )
    assert exc.value.code == "law_rate_limited"

    with pytest.raises(ContractReviewError) as exc:
        await KoreanLawAdapter(FakeMcpManager(kind="korean-law")).call(
            owner="alice", server_id="korean-law", tool="execute_tool",
            arguments={"tool_name": "anything", "params": {}},
        )
    assert exc.value.code == "law_tool_forbidden"


@pytest.mark.asyncio
async def test_jobs_are_owner_scoped_and_cancel_is_terminal(contract_workspace):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "contract.docx"
    doc.parent.mkdir()
    doc.write_bytes(b"fixture")
    jobs = ContractReviewJobManager(KordocAdapter(FakeMcpManager(delay=0.2), timeout=1))
    job = jobs.start_kordoc(
        owner="alice", server_id="kordoc", tool="parse_document",
        workspace=str(workspace), relative_path="documents/contract.docx", arguments={},
    )
    with pytest.raises(ContractReviewError) as exc:
        jobs.get("bob", job["id"])
    assert exc.value.code == "job_unavailable"
    cancelled = await jobs.cancel("alice", job["id"])
    assert cancelled["state"] == "cancelled"
    await asyncio.sleep(0)
    assert jobs.get("alice", job["id"])["state"] == "cancelled"


def _valid_result():
    return {
        "schema_version": "contract-review.v2",
        "generated_at": "2026-08-02T17:00:00+09:00",
        "session_id": "session-1",
        "evidence_fingerprint": "e" * 64,
        "usage": {"source": "estimated", "input_tokens": 120, "output_tokens": 40},
        "review_summary": {"text": "Summary"},
        "local_document_evidence": [{
            "id": "doc-1", "evidence_type": "local_document",
            "path": "documents/contract.pdf", "verification_state": "verified",
        }],
        "vault_note_evidence": [{
            "id": "note-1", "evidence_type": "vault_note",
            "path": "기본 계약.md", "verification_state": "verified",
        }],
        "official_legal_evidence": [{
            "id": "law-1", "evidence_type": "official_legal", "source": "law.go.kr",
            "citation_id": "법령ID:1", "verification_state": "verified",
        }],
        "model_interpretation": {"text": "Interpretation", "evidence_ids": ["law-1"]},
        "uncertainty_and_follow_up": ["Confirm governing law."],
    }


def test_result_schema_separates_evidence_interpretation_uncertainty_and_usage():
    result = validate_contract_review_result(_valid_result())
    assert list(result["blocks"]) == list(CONTRACT_REVIEW_BLOCKS)
    assert result["generated_at"].endswith("+09:00")
    assert result["usage"]["source"] == "estimated"
    markdown = build_contract_review_markdown(result)
    for heading in ("검토 요약", "로컬 문서 근거", "Vault 노트 근거", "법령·판례 공식 근거", "모델의 해석/권고", "불확실성·추가 확인"):
        assert heading in markdown
        assert markdown.count(f"## {heading}") == 1
    assert "estimated" in markdown.lower()

    utc = _valid_result()
    utc["generated_at"] = "2026-08-02T08:00:00+00:00"
    with pytest.raises(ContractReviewError):
        validate_contract_review_result(utc)

    fake_actual = _valid_result()
    fake_actual["usage"] = {"source": "actual", "input_tokens": None, "output_tokens": None}
    with pytest.raises(ContractReviewError):
        validate_contract_review_result(fake_actual)

    oversized = _valid_result()
    oversized["vault_note_evidence"][0]["content"] = "x" * 6_001
    with pytest.raises(ContractReviewError):
        validate_contract_review_result(oversized)


def test_contract_review_policy_blocks_all_generic_mcp_and_mutation_tools():
    policy = contract_review_tool_policy()
    assert policy.disable_mcp is True
    assert policy.block_all_tool_calls is True
    for tool in ("bash", "python", "read_file", "create_document", "mcp__kordoc__parse_document", "mcp__korean-law__search_law"):
        assert policy.blocks(tool)
    assert set(KORDOC_READ_ONLY_TOOLS) >= {"parse_document", "parse_metadata", "parse_pages"}
    assert set(KOREAN_LAW_READ_ONLY_TOOLS) == {"search_law", "get_law_text", "search_decisions", "get_decision_text"}
