from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_editorial_workflow_and_designed_artifact_are_persisted_in_ui_contract():
    panel = (ROOT / "static/js/research/panel.js").read_text(encoding="utf-8")
    jobs = (ROOT / "static/js/research/jobs.js").read_text(encoding="utf-8")

    assert 'id="research-mode"' in panel
    assert 'value="editorial"' in panel
    assert "research_mode: researchMode" in panel
    assert "document.getElementById('research-mode')?.value" in panel
    assert 'name="research-html-renderer"' in panel
    assert 'value="document"' in panel
    assert 'value="editorial"' in panel
    assert 'value="scroll_story"' in panel
    assert "_rendererArtifactUrl(job.id, renderer" in panel
    assert "Document HTML" in panel
    assert "Editorial HTML" in panel
    assert "Scroll Story HTML" in panel
    assert 'id="research-design-image-mode"' in panel
    assert '<option value="none" selected>없음 (기본)</option>' in panel
    assert '<option value="cover">표지·배경만</option>' in panel
    assert '<option value="editorial">표지 + 섹션 일러스트</option>' in panel
    assert "design_image_mode: _normalizeDesignImageMode(" in panel
    assert "_syncDesignImageControls();" in panel
    assert "research-renderer-scroll-story')?.checked" in panel
    assert "['editorial', 'scroll_story'].includes(renderer)" in panel
    assert "research_mode: settings?.research_mode || 'research'" in jobs
    assert "if (data.research_mode) job.research_mode = data.research_mode" in jobs
    assert "design_image_mode: settings?.design_image_mode || 'none'" in jobs
    assert "if (data.design_image_mode) job.design_image_mode = data.design_image_mode" in jobs
    assert "html_renderers: settings?.html_renderers || ['document']" in jobs
    assert "if (data.html_renderers) job.html_renderers = data.html_renderers" in jobs


def test_editorial_ui_requires_explicit_local_selection():
    panel = (ROOT / "static/js/research/panel.js").read_text(encoding="utf-8")

    assert "function _validateResearchWorkflow(settings)" in panel
    assert "!['local', 'obsidian'].includes(settings.source_mode || '')" in panel
    assert "settings.knowledge_folders.length === 0" in panel
    assert "providerSel.disabled = true" in panel
