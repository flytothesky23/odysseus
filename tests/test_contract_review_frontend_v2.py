import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _node(script: str):
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_browser_state_persists_identifiers_not_private_content():
    state_url = (ROOT / "static/js/contractReviewState.js").as_uri()
    data = _node(f"""
      import {{ sanitizePersistedState, buildContractReviewChatContext }} from {json.dumps(state_url)};
      const input = {{active: true, snapshot_id: 'snap', vault_id: 'vault', vault_path: 'legal',
        selected_paths: ['Agreement.md', '../escape.md', '/absolute.md'],
        kordoc_job_ids: ['a'.repeat(32)], law_job_ids: ['b'.repeat(32)],
        raw_body: 'private body', absolute_path: '/private/path', prompt: 'private question'}};
      const safe = sanitizePersistedState(input);
      console.log(JSON.stringify({{safe, ctx: buildContractReviewChatContext(safe)}}));
    """)
    serialized = json.dumps(data, ensure_ascii=False)
    assert data["safe"]["selected_paths"] == ["Agreement.md"]
    assert data["safe"]["law_job_ids"] == ["b" * 32]
    for secret in ("private body", "/private/path", "private question"):
        assert secret not in serialized


def test_note_selection_survives_metadata_search_result_changes():
    state_url = (ROOT / "static/js/contractReviewState.js").as_uri()
    data = _node(f"""
      import {{ updateSelectedPathSelection }} from {json.dumps(state_url)};
      let selected = updateSelectedPathSelection([], 'Agreement.md', true);
      selected = updateSelectedPathSelection(selected, 'amendments/Liability.md', true);
      const deselected = updateSelectedPathSelection(selected, 'Agreement.md', false);
      console.log(JSON.stringify({{selected, deselected}}));
    """)
    assert data["selected"] == ["Agreement.md", "amendments/Liability.md"]
    assert data["deselected"] == ["amendments/Liability.md"]


def test_vault_explorer_builds_nested_tree_and_searches_all_safe_metadata_fields():
    explorer_url = (ROOT / "static/js/contractReviewExplorerState.js").as_uri()
    data = _node(f"""
      import {{ buildVaultTree, filterVaultNotes }} from {json.dumps(explorer_url)};
      const notes = [
        {{path: '10_업무체계/계약/2026 계약.md', filename: '2026 계약.md', title: '공사 도급계약', aliases: ['지수공장']}},
        {{path: '00_System/안내.md', filename: '안내.md', title: 'Vault 안내', aliases: []}},
        {{path: '10_업무체계/계약/2025 계약.md', filename: '2025 계약.md', title: '이전 계약', aliases: []}},
      ];
      const tree = buildVaultTree(notes);
      console.log(JSON.stringify({{
        rootFolders: tree.folders.map(folder => folder.name),
        contractNotes: tree.folders[1].folders[0].notes.map(note => note.filename),
        filename: filterVaultNotes(notes, '2026 계약.md').map(note => note.path),
        title: filterVaultNotes(notes, '공사 도급계약').map(note => note.path),
        korean: filterVaultNotes(notes, '지수공장').map(note => note.path),
        path: filterVaultNotes(notes, '10_업무체계').map(note => note.path),
      }}));
    """)
    assert data["rootFolders"] == ["00_System", "10_업무체계"]
    assert data["contractNotes"] == ["2025 계약.md", "2026 계약.md"]
    assert data["filename"] == ["10_업무체계/계약/2026 계약.md"]
    assert data["title"] == ["10_업무체계/계약/2026 계약.md"]
    assert data["korean"] == ["10_업무체계/계약/2026 계약.md"]
    assert data["path"] == [
        "10_업무체계/계약/2025 계약.md",
        "10_업무체계/계약/2026 계약.md",
    ]


def test_vault_explorer_folder_selection_is_tri_state_and_never_silently_exceeds_chat_cap():
    explorer_url = (ROOT / "static/js/contractReviewExplorerState.js").as_uri()
    data = _node(f"""
      import {{ folderSelectionState, updateBoundedSelection }} from {json.dumps(explorer_url)};
      const paths = Array.from({{length: 10}}, (_, i) => `Folder/note-${{i}}.md`);
      const added = updateBoundedSelection([], paths, true, 8);
      const mixed = folderSelectionState(paths, added.selected_paths);
      const cleared = updateBoundedSelection(added.selected_paths, paths, false, 8);
      console.log(JSON.stringify({{added, mixed, cleared}}));
    """)
    assert len(data["added"]["selected_paths"]) == 8
    assert data["added"]["rejected_count"] == 2
    assert data["mixed"] == {"state": "mixed", "selected": 8, "total": 10}
    assert data["cleared"] == {"selected_paths": [], "rejected_count": 0}


def test_vault_explorer_is_a_sidebar_tool_opening_a_notes_style_right_panel():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    app = (ROOT / "static/app.js").read_text(encoding="utf-8")
    explorer = (ROOT / "static/js/contractReviewExplorer.js").read_text(encoding="utf-8")
    manager = (ROOT / "static/js/modalManager.js").read_text(encoding="utf-8")
    assert 'id="tool-vault-explorer-btn"' in html
    assert 'id="rail-vault-explorer"' in html
    assert "import contractReviewExplorerModule from './js/contractReviewExplorer.js'" in app
    assert "'rail-vault-explorer': 'tool-vault-explorer-btn'" in app
    assert "contractReviewExplorerModule.togglePanel()" in app
    assert "notes-pane vault-explorer-pane" in explorer
    assert "applyEdgeDock(pane, 'right')" in explorer
    assert "vault-explorer-panel" in manager


def test_vault_explorer_exposes_an_obvious_vault_picker_and_index_action():
    explorer = (ROOT / "static/js/contractReviewExplorer.js").read_text(encoding="utf-8")
    workspace = (ROOT / "static/js/workspace.js").read_text(encoding="utf-8")
    assert "Vault 폴더 선택" in explorer
    assert "Metadata 색인" in explorer
    assert 'id="vault-explorer-empty-select"' in explorer
    assert "workspace-selected" in workspace
    assert "preserveSelection: true" in explorer
    assert "체크박스 = metadata 검색·분석 범위" in explorer
    assert "검색 결과를 본문 후보로" in explorer
    assert "현재 후보로 채팅" in explorer


def test_vault_explorer_closes_before_opening_the_mcp_workspace_modal():
    explorer = (ROOT / "static/js/contractReviewExplorer.js").read_text(encoding="utf-8")
    assert "closePanel();\n    contractReviewModule.openContractReview();" in explorer


def test_contract_review_refreshes_mcp_inventory_each_time_the_workspace_opens():
    workspace = (ROOT / "static/js/contractReview.js").read_text(encoding="utf-8")
    assert "if (profileLoaded) return" not in workspace
    assert "let profileLoaded" not in workspace
    assert "clearProfileServers();\n  const profile = await api('/profile');" in workspace
    assert "catch (error) { clearProfileServers();" in workspace


def test_contract_review_indicator_tracks_explorer_state_changes():
    workspace = (ROOT / "static/js/contractReview.js").read_text(encoding="utf-8")
    assert "document.addEventListener('contract-review-state-change', event => {" in workspace
    assert "syncIndicator(event.detail);" in workspace


def test_explicit_report_save_has_one_request_method_definition():
    workspace = (ROOT / "static/js/contractReview.js").read_text(encoding="utf-8")
    duplicate = "method: 'POST', body: JSON.stringify({ session_id: sessionId, title, result }),\n    method: 'POST'"
    assert duplicate not in workspace


def test_vault_explorer_revalidates_persisted_selection_against_the_new_manifest():
    explorer_url = (ROOT / "static/js/contractReviewExplorerState.js").as_uri()
    data = _node(f"""
      import {{ reconcileSelectedPaths }} from {json.dumps(explorer_url)};
      const notes = [
        {{path: '계약/유효.md'}},
        {{path: '계약/신규.md'}},
        {{path: '../escape.md'}},
      ];
      console.log(JSON.stringify({{
        kept: reconcileSelectedPaths(['계약/유효.md', '삭제됨.md', '/절대.md'], notes, 8),
        capped: reconcileSelectedPaths(
          Array.from({{length: 12}}, (_, i) => `범위/${{i}}.md`),
          Array.from({{length: 12}}, (_, i) => ({{path: `범위/${{i}}.md`}})),
          8,
        ),
      }}));
    """)
    assert data["kept"] == ["계약/유효.md"]
    assert data["capped"] == [f"범위/{i}.md" for i in range(8)]


def test_vault_explorer_uses_compact_longest_match_scope_rules_for_folders_and_notes():
    explorer_url = (ROOT / "static/js/contractReviewExplorerState.js").as_uri()
    data = _node(f"""
      import {{ isPathIncludedByScope, updateScopeSelection }} from {json.dumps(explorer_url)};
      let scope = {{default_included: true, rules: []}};
      scope = updateScopeSelection(scope, '10_업무체계/계약', false);
      scope = updateScopeSelection(scope, '10_업무체계/계약/대한제강', true);
      scope = updateScopeSelection(scope, '10_업무체계/계약/대한제강/제외.md', false);
      console.log(JSON.stringify({{
        scope,
        excluded: isPathIncludedByScope('10_업무체계/계약/다른회사.md', scope),
        included: isPathIncludedByScope('10_업무체계/계약/대한제강/2026.md', scope),
        exact: isPathIncludedByScope('10_업무체계/계약/대한제강/제외.md', scope),
        outside: isPathIncludedByScope('20_법률/민법.md', scope),
      }}));
    """)
    assert data["excluded"] is False
    assert data["included"] is True
    assert data["exact"] is False
    assert data["outside"] is True
    assert data["scope"]["rules"] == [
        {"path": "10_업무체계/계약", "included": False},
        {"path": "10_업무체계/계약/대한제강", "included": True},
        {"path": "10_업무체계/계약/대한제강/제외.md", "included": False},
    ]


def test_browser_state_persists_only_safe_compact_scope_rules():
    state_url = (ROOT / "static/js/contractReviewState.js").as_uri()
    data = _node(f"""
      import {{ sanitizePersistedState, buildContractReviewChatContext }} from {json.dumps(state_url)};
      const safe = sanitizePersistedState({{
        active: true, snapshot_id: 'snap', vault_id: 'vault',
        note_scope: {{default_included: false, rules: [
          {{path: String.raw`10_업무체계\\계약`, included: true}},
          {{path: '../escape', included: true}},
          {{path: '/absolute', included: true}},
          {{path: '20_법률', included: 'yes'}},
        ]}},
      }});
      console.log(JSON.stringify({{safe, context: buildContractReviewChatContext(safe)}}));
    """)
    assert data["safe"]["note_scope"] == {
        "default_included": False,
        "rules": [{"path": "10_업무체계/계약", "included": True}],
    }
    assert data["context"]["note_scope"] == data["safe"]["note_scope"]


def test_precedent_search_is_scoped_to_the_verified_precedent_domain():
    source = (ROOT / "static/js/contractReview.js").read_text(encoding="utf-8")
    assert "{ domain: 'precedent', query, display: 5 }" in source


def test_renderer_requires_v2_schema_and_labels_estimated_usage():
    renderer_url = (ROOT / "static/js/contractReviewRenderer.js").as_uri()
    payload = {
        "schema_version": "contract-review.v2", "generated_at": "2026-08-02T17:00:00+09:00",
        "usage": {"source": "estimated", "input_tokens": 12, "output_tokens": 5},
        "blocks": {
            "review_summary": {"text": "Summary"}, "local_document_evidence": [],
            "vault_note_evidence": [], "official_legal_evidence": [],
            "model_interpretation": {"text": "Interpretation", "evidence_ids": []},
            "uncertainty_and_follow_up": ["Check"],
        },
    }
    data = _node(f"""
      import {{ renderContractReviewResult }} from {json.dumps(renderer_url)};
      const html = renderContractReviewResult({json.dumps(payload, ensure_ascii=False)});
      console.log(JSON.stringify({{html}}));
    """)
    html = data["html"]
    assert "contract-review-result" in html
    assert "Estimated" in html
    assert "Official legal evidence" in html


def test_renderer_handles_actual_codex_interpretation_and_follow_up_objects():
    renderer_url = (ROOT / "static/js/contractReviewRenderer.js").as_uri()
    payload = {
        "schema_version": "contract-review.v2", "generated_at": "2026-08-02T17:00:00+09:00",
        "usage": {"source": "actual", "input_tokens": 2180, "output_tokens": 1139},
        "blocks": {
            "review_summary": {"content": "두 가지 위험이 확인되었습니다."},
            "local_document_evidence": [], "vault_note_evidence": [],
            "official_legal_evidence": [],
            "model_interpretation": {
                "items": [{"risk": "검수 완료 시점 불명확", "analysis": "기산점 분쟁 위험"}],
                "evidence_ids": [],
            },
            "uncertainty_and_follow_up": [{
                "issue": "직접 적용 법령 미확인",
                "detail": "공식 근거의 직접성이 제한됨",
                "follow_up": "현행 조문 추가 확인",
            }],
        },
    }
    data = _node(f"""
      import {{ renderContractReviewResult }} from {json.dumps(renderer_url)};
      const html = renderContractReviewResult({json.dumps(payload, ensure_ascii=False)});
      console.log(JSON.stringify({{html}}));
    """)
    html = data["html"]
    assert "검수 완료 시점 불명확" in html
    assert "기산점 분쟁 위험" in html
    assert "현행 조문 추가 확인" in html
    assert "[object Object]" not in html


def test_contract_review_chat_progress_does_not_claim_web_search():
    source = (ROOT / "static/js/chat.js").read_text(encoding="utf-8")
    assert "const hasContractReviewContext = !!contractReviewContext;" in source
    assert "el('web-toggle').checked && !_isAgent && !hasContractReviewContext" in source


def test_chat_renderer_and_live_chat_reference_contract_renderer():
    renderer = (ROOT / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    chat = (ROOT / "static/js/chat.js").read_text(encoding="utf-8")
    assert "renderContractReviewResult" in renderer
    assert "contract_review_result" in renderer
    assert "contract_review_result" in chat
    assert "contract_review_error" in renderer
    assert "contract-review-result-error" in chat


def test_contract_review_has_native_workspace_picker_in_chat_mode():
    source = (ROOT / "static/js/contractReview.js").read_text(encoding="utf-8")
    assert "contract-review-workspace-select" in source
    assert "workspaceModule.openWorkspaceBrowser" in source
    assert "workspaceModule.getWorkspace" in source
    assert "finally" in source
    assert "activeJobId = null" in source
    assert "import sessionModule from './sessions.js'" in source
    assert "window.sessionModule" not in source
    app = (ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "from './js/sessions.js';" in app
    assert "sessions.js?v=" not in app.splitlines()[20]
