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
from src.mcp_manager import stdio_launch_identity_hash


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


def test_metadata_and_body_search_are_confined_to_compact_note_scope(contract_workspace):
    workspace, _vault = contract_workspace
    service = ContractReviewWorkspaceService(max_body_candidates=2)
    indexed = _index(service, workspace)
    scope = {
        "default_included": False,
        "rules": [{"path": "amendments", "included": True}],
    }

    included = service.search(
        "alice", indexed["snapshot_id"], indexed["vault_id"], "책임 제한",
        note_scope=scope,
    )
    excluded = service.search(
        "alice", indexed["snapshot_id"], indexed["vault_id"], "용역 기본 계약서",
        note_scope=scope,
    )
    assert [item["path"] for item in included["results"]] == ["amendments/Liability.md"]
    assert excluded["results"] == []

    with pytest.raises(ContractReviewError) as exc:
        service.search(
            "alice", indexed["snapshot_id"], indexed["vault_id"], "지급",
            include_body=True,
            candidate_paths=["기본 계약.md"],
            note_scope=scope,
        )
    assert exc.value.code == "outside_scope"


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


def test_reindexed_modified_note_invalidates_same_path_body_cache(contract_workspace, monkeypatch):
    workspace, vault = contract_workspace
    service = ContractReviewWorkspaceService(max_body_chars=4000)
    first_index = _index(service, workspace)
    calls = []
    original = service._read_note_body

    def spy(owner, snapshot, relative_path, *args, **kwargs):
        calls.append(relative_path)
        return original(owner, snapshot, relative_path, *args, **kwargs)

    monkeypatch.setattr(service, "_read_note_body", spy)
    first = service.build_turn_context(
        owner="alice", session_id="same-session",
        snapshot_id=first_index["snapshot_id"], vault_id=first_index["vault_id"],
        selected_paths=["기본 계약.md"], analysis_mode="general",
    )
    assert "재색인 변경 문장" not in first["evidence"][0]["content"]

    note = vault / "기본 계약.md"
    note.write_text(
        note.read_text(encoding="utf-8") + "\n재색인 변경 문장\n",
        encoding="utf-8",
    )
    second_index = _index(service, workspace)
    refreshed = service.build_turn_context(
        owner="alice", session_id="same-session",
        snapshot_id=second_index["snapshot_id"], vault_id=second_index["vault_id"],
        selected_paths=["기본 계약.md"], analysis_mode="general",
    )

    assert refreshed["strategy"] == "delta"
    assert refreshed["delta_paths"] == ["기본 계약.md"]
    assert "재색인 변경 문장" in refreshed["evidence"][0]["content"]
    assert calls == ["기본 계약.md", "기본 계약.md"]


def test_explicit_vault_markdown_save_uses_existing_folder_kst_frontmatter_and_no_overwrite(contract_workspace):
    workspace, vault = contract_workspace
    service = ContractReviewWorkspaceService()
    indexed = _index(service, workspace)
    target = vault / "amendments" / "계약 검토 결과.md"
    assert not target.exists()

    saved = service.save_markdown_note(
        owner="alice",
        snapshot_id=indexed["snapshot_id"],
        vault_id=indexed["vault_id"],
        folder="amendments",
        title="계약 검토 결과",
        markdown="# 결론\n\n명시적으로 저장한 비식별 분석 결과",
    )

    assert saved["path"] == "amendments/계약 검토 결과.md"
    assert saved["created_at"].endswith("+09:00")
    assert saved["reindex_required"] is True
    content = target.read_text(encoding="utf-8")
    assert content.startswith("---\ntitle: \"계약 검토 결과\"\n")
    assert "created:" in content and "+09:00" in content
    assert "source: odysseus\n" in content
    assert content.endswith("# 결론\n\n명시적으로 저장한 비식별 분석 결과\n")

    with pytest.raises(ContractReviewError) as exc:
        service.save_markdown_note(
            owner="alice", snapshot_id=indexed["snapshot_id"], vault_id=indexed["vault_id"],
            folder="amendments", title="계약 검토 결과", markdown="overwrite",
        )
    assert exc.value.code == "note_exists"
    assert "overwrite" not in target.read_text(encoding="utf-8")


def test_vault_markdown_save_rejects_owner_escape_hidden_symlink_and_stale_root(contract_workspace, tmp_path):
    workspace, vault = contract_workspace
    service = ContractReviewWorkspaceService()
    indexed = _index(service, workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (vault / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")

    cases = [
        ("bob", "amendments", "owner"),
        ("alice", "../outside", "traversal"),
        ("alice", str(outside), "absolute"),
        ("alice", ".private", "hidden"),
        ("alice", "escape", "symlink"),
        ("alice", "missing", "missing"),
    ]
    for owner, folder, title in cases:
        with pytest.raises(ContractReviewError):
            service.save_markdown_note(
                owner=owner, snapshot_id=indexed["snapshot_id"], vault_id=indexed["vault_id"],
                folder=folder, title=title, markdown="must not be written",
            )
    assert not any(outside.iterdir())

    moved = workspace / "old-vault"
    vault.rename(moved)
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    with pytest.raises(ContractReviewError) as exc:
        service.save_markdown_note(
            owner="alice", snapshot_id=indexed["snapshot_id"], vault_id=indexed["vault_id"],
            folder=".", title="stale", markdown="must not be written",
        )
    assert exc.value.code == "vault_changed"
    assert not (vault / "stale.md").exists()


def test_memo_only_context_reuses_and_deltas_without_requiring_a_vault_snapshot():
    service = ContractReviewWorkspaceService()
    memo_a = {
        "id": "11111111-1111-4111-8111-111111111111",
        "evidence_type": "odysseus_note",
        "title": "검토 메모",
        "content": "Kordoc로 파싱한 제한된 본문",
        "stat_fingerprint": "a" * 64,
        "verification_state": "verified",
    }
    memo_b = {
        "id": "22222222-2222-4222-8222-222222222222",
        "evidence_type": "odysseus_note",
        "title": "추가 메모",
        "content": "추가 검토 근거",
        "stat_fingerprint": "b" * 64,
        "verification_state": "verified",
    }

    fresh = service.build_turn_context(
        owner="alice", session_id="memo-session", snapshot_id="", vault_id="",
        selected_paths=[], odysseus_note_evidence=[memo_a], analysis_mode="general",
    )
    reused = service.build_turn_context(
        owner="alice", session_id="memo-session", snapshot_id="", vault_id="",
        selected_paths=[], odysseus_note_evidence=[memo_a], analysis_mode="general",
    )
    delta = service.build_turn_context(
        owner="alice", session_id="memo-session", snapshot_id="", vault_id="",
        selected_paths=[], odysseus_note_evidence=[memo_a, memo_b], analysis_mode="legal",
    )

    assert fresh["strategy"] == "fresh"
    assert reused["strategy"] == "reuse"
    assert delta["strategy"] == "delta"
    assert fresh["analysis_mode"] == "general"
    assert delta["analysis_mode"] == "legal"
    assert [item["title"] for item in delta["odysseus_note_evidence"]] == ["검토 메모", "추가 메모"]
    assert all("path" not in item for item in delta["odysseus_note_evidence"])


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


def test_virtual_obsidian_vault_mounts_are_pinned_without_allowing_arbitrary_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    vault = workspace / "vault"
    source_vault = tmp_path / "source-vault"
    config = tmp_path / "obsidian-config"
    outside = tmp_path / "outside"
    vault.mkdir(parents=True)
    config.mkdir()
    (source_vault / ".obsidian").mkdir(parents=True)
    outside.mkdir()
    _write(source_vault / "계약" / "지급.md", "# 지급\n검수 후 30일 이내 지급한다.")
    _write(source_vault / "직접.md", "# 직접 노트")
    _write(outside / "탈출.md", "credential-like content")
    try:
        (vault / ".obsidian").symlink_to(config, target_is_directory=True)
        (vault / "계약").symlink_to(source_vault / "계약", target_is_directory=True)
        (vault / "직접.md").symlink_to(source_vault / "직접.md")
        (vault / "탈출.md").symlink_to(outside / "탈출.md")
        (source_vault / "계약" / "중첩탈출").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")

    service = ContractReviewWorkspaceService()
    indexed = _index(service, workspace)
    assert {note["path"] for note in indexed["notes"]} == {"계약/지급.md", "직접.md"}
    assert service.open_note(
        "alice", indexed["snapshot_id"], indexed["vault_id"], "계약/지급.md",
    )["content"].startswith("# 지급")

    replacement_vault = tmp_path / "replacement-vault"
    (replacement_vault / ".obsidian").mkdir(parents=True)
    _write(replacement_vault / "계약" / "지급.md", "swapped")
    (vault / "계약").unlink()
    (vault / "계약").symlink_to(replacement_vault / "계약", target_is_directory=True)
    with pytest.raises(ContractReviewError) as exc:
        service.search("alice", indexed["snapshot_id"], indexed["vault_id"], "지급")
    assert exc.value.code == "vault_changed"


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
        self.launch_identity_hash = (
            stdio_launch_identity_hash("npx", ["-y", "kordoc@4.2.5", "mcp"])
            if kind == "kordoc" else "law-fixture"
        )

    def get_server_status(self, server_id):
        return {
            "status": self.status,
            "identity": f"{self.kind}-local",
            "tool_count": 1,
        }

    def get_all_tools(self, disabled_map=None):
        if self.raise_inventory:
            raise RuntimeError("inventory unavailable")
        tools = ["parse_document"] if self.kind == "kordoc" else [
            "search_law", "get_law_text", "search_decisions", "get_decision_text",
        ]
        return [{
            "server_id": self.kind,
            "server_name": self.server_name,
            "connection_identity": f"{self.kind}-local",
            "launch_identity_hash": self.launch_identity_hash,
            "connection_status": self.status,
            "inventory_generation": self.inventory_generation,
            "name": tool,
            "qualified_name": f"mcp__{self.kind}__{tool}",
            "description": "read-only fixture",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path" if self.kind == "kordoc" else (
                        "query" if tool.startswith("search_") else "mst" if tool == "get_law_text" else "id"
                    ): {"type": "string"},
                },
                "x-version": self.schema_version,
            },
            "annotations": {"readOnlyHint": True},
            "is_disabled": False,
        } for tool in tools]

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.result, Exception):
            raise self.result
        if self.kind == "korean-law" and self.result == {"stdout": "# Parsed fixture", "exit_code": 0}:
            if name.endswith("__search_law"):
                return {
                    "stdout": "검색 결과 (총 1건):\n\n📍 정확매칭 (1건):\n1. 대한민국헌법 [현행]\n   - 법령ID: 001444\n   - MST: 61603\n",
                    "exit_code": 0,
                }
            if name.endswith("__get_law_text"):
                return {"stdout": "법령명: 대한민국헌법\n제1조 대한민국은 민주공화국이다.", "exit_code": 0}
            if name.endswith("__search_decisions"):
                return {
                    "stdout": "판례 검색 결과 (총 1건, 1페이지):\n\n[12345] 손해배상\n  사건번호: 2020다12345\n  법원: 대법원\n",
                    "exit_code": 0,
                }
            if name.endswith("__get_decision_text"):
                return {"stdout": "=== 손해배상 ===\n\n기본 정보:\n  사건번호: 2020다12345\n판결요지:\n검증된 판례", "exit_code": 0}
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
async def test_kordoc_inventory_allowlist_timeout_and_parser_failures(contract_workspace, monkeypatch):
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

    wrong_version = FakeMcpManager()
    wrong_version.launch_identity_hash = stdio_launch_identity_hash("npx", ["-y", "kordoc@4.5.0", "mcp"])
    monkeypatch.setenv("ODYSSEUS_CONTRACT_REVIEW_ALLOW_TEST_FIXTURES", "1")
    with pytest.raises(ContractReviewError) as exc:
        KordocAdapter(wrong_version).admit(
            owner="alice", server_id="kordoc", tool="parse_document",
            workspace=str(workspace), relative_path="documents/contract.hwp", arguments={},
        )
    assert exc.value.code == "kordoc_server_forbidden"

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
    assert manager.calls[0][1]["ocr"] is False
    assert str(workspace) not in json.dumps(result)


def test_kordoc_arguments_match_the_pinned_read_only_4_2_5_schemas(contract_workspace):
    workspace, _vault = contract_workspace
    doc = workspace / "documents" / "contract.pdf"
    doc.parent.mkdir()
    doc.write_bytes(b"fixture")
    adapter = KordocAdapter(FakeMcpManager())

    for tool, arguments, expected in (
        ("parse_document", {"ocr": "yes"}, "invalid_request"),
        ("parse_document", {"url": "https://example.invalid"}, "kordoc_argument_forbidden"),
        ("detect_format", {"ocr": False}, "kordoc_argument_forbidden"),
        ("parse_pages", {"pages": "1;2"}, "invalid_request"),
        ("parse_table", {"table_index": -1}, "invalid_request"),
        ("parse_chunks", {"granularity": "document"}, "invalid_request"),
        ("parse_form", {"fields": []}, "kordoc_argument_forbidden"),
    ):
        with pytest.raises(ContractReviewError) as exc:
            adapter.admit(
                owner="alice",
                server_id="kordoc",
                tool=tool,
                workspace=str(workspace),
                relative_path="documents/contract.pdf",
                arguments=arguments,
            )
        assert exc.value.code == expected


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
    )
    evidence = await KoreanLawAdapter(ok, timeout=1).call(
        owner="alice", server_id="korean-law", tool="search_law",
        arguments={"query": "대한민국헌법", "display": 1},
    )
    assert evidence["state"] == "completed"
    assert evidence["evidence_type"] == "official_legal"
    assert evidence["source"] == "law.go.kr"
    assert evidence["tool"] == "get_law_text"
    assert evidence["discovery_tool"] == "search_law"
    assert evidence["citation_id"] == "law.go.kr · 대한민국헌법 · MST 61603"
    assert "대한민국헌법" in evidence["output"]
    assert ok.calls == [
        ("mcp__korean-law__search_law", {"query": "대한민국헌법", "display": 1}),
        ("mcp__korean-law__get_law_text", {"mst": "61603"}),
    ]

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
async def test_korean_law_rejects_partial_candidates_and_identity_swaps():
    partial = FakeMcpManager(
        kind="korean-law",
        result={"stdout": "검색 결과 (총 1건):\n\n📂 부분매칭 (1건 중 1건 표시):\n1. 대한민국헌법재판소법 [현행]\n   - MST: 999999\n", "exit_code": 0},
    )
    with pytest.raises(ContractReviewError) as exc:
        await KoreanLawAdapter(partial, timeout=1).call(
            owner="alice", server_id="korean-law", tool="search_law",
            arguments={"query": "대한민국헌법"},
        )
    assert exc.value.code == "law_exact_match_required"
    assert len(partial.calls) == 1

    swapped = FakeMcpManager(kind="korean-law")
    original_call = swapped.call_tool

    async def mutate_after_search(name, arguments):
        result = await original_call(name, arguments)
        if name.endswith("__search_law"):
            swapped.schema_version += 1
        return result

    swapped.call_tool = mutate_after_search
    with pytest.raises(ContractReviewError) as exc:
        await KoreanLawAdapter(swapped, timeout=1).call(
            owner="alice", server_id="korean-law", tool="search_law",
            arguments={"query": "대한민국헌법"},
        )
    assert exc.value.code == "mcp_identity_changed"


@pytest.mark.asyncio
async def test_korean_law_verifies_precedent_search_with_decision_text():
    manager = FakeMcpManager(kind="korean-law")
    evidence = await KoreanLawAdapter(manager, timeout=1).call(
        owner="alice", server_id="korean-law", tool="search_decisions",
        arguments={"domain": "precedent", "query": "손해배상", "display": 5},
    )

    assert evidence["tool"] == "get_decision_text"
    assert evidence["discovery_tool"] == "search_decisions"
    assert evidence["citation_id"] == "law.go.kr · 2020다12345 · ID 12345"
    assert manager.calls[-1] == (
        "mcp__korean-law__get_decision_text",
        {"domain": "precedent", "id": "12345"},
    )


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
