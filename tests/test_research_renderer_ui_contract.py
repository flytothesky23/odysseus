from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ui_separates_artifact_formats_from_html_renderer_multiselect():
    panel = (ROOT / "static/js/research/panel.js").read_text(encoding="utf-8")
    jobs = (ROOT / "static/js/research/jobs.js").read_text(encoding="utf-8")

    assert 'name="research-output-format"' in panel
    assert 'value="html"' in panel
    assert 'name="research-html-renderer"' in panel
    assert 'value="auto"' in panel
    assert 'value="document"' in panel
    assert 'value="editorial"' in panel
    assert 'value="scroll_story"' in panel
    assert "html_renderers: _selectedHtmlRenderers()" in panel
    assert "html_renderers: settings?.html_renderers || ['document']" in jobs
    assert "if (data.html_renderers) job.html_renderers = data.html_renderers" in jobs
    assert "renderer_recommendation" in panel


def test_ui_has_independent_open_and_download_actions_for_each_renderer():
    panel = (ROOT / "static/js/research/panel.js").read_text(encoding="utf-8")

    assert "renderer/${renderer}" in panel
    assert "Document HTML" in panel
    assert "Editorial HTML" in panel
    assert "Scroll Story HTML" in panel
    assert "download=1" in panel
