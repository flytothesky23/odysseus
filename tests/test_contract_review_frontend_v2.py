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
