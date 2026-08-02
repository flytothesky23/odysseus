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
