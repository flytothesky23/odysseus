from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_editorial_workflow_and_designed_artifact_are_persisted_in_ui_contract():
    panel = (ROOT / "static/js/research/panel.js").read_text(encoding="utf-8")
    jobs = (ROOT / "static/js/research/jobs.js").read_text(encoding="utf-8")

    assert 'id="research-mode"' in panel
    assert 'value="editorial"' in panel
    assert "research_mode: researchMode" in panel
    assert "document.getElementById('research-mode')?.value" in panel
    assert 'value="html_designed"' in panel
    assert "kind === 'html_designed' ? 'designed'" in panel
    assert "Legacy HTML" in panel
    assert "Design HTML" in panel
    assert "research_mode: settings?.research_mode || 'research'" in jobs
    assert "if (data.research_mode) job.research_mode = data.research_mode" in jobs


def test_editorial_ui_requires_explicit_local_selection():
    panel = (ROOT / "static/js/research/panel.js").read_text(encoding="utf-8")

    assert "function _validateResearchWorkflow(settings)" in panel
    assert "!['local', 'obsidian'].includes(settings.source_mode || '')" in panel
    assert "settings.knowledge_folders.length === 0" in panel
    assert "providerSel.disabled = true" in panel
