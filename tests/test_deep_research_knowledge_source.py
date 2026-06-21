import pytest

from src.deep_research import DeepResearcher
from src.knowledge_base import (
    KnowledgeBaseError,
    collect_note_images,
    list_vault_folders,
    resolve_selected_folders,
)


def test_knowledge_folders_stay_under_configured_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    allowed = vault / "21_notes"
    allowed.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr("src.knowledge_base.get_setting", lambda key, default=None: str(vault) if key == "knowledge_vault_root" else default)

    assert resolve_selected_folders(["21_notes"]) == [allowed.resolve()]

    with pytest.raises(KnowledgeBaseError):
        resolve_selected_folders(["../outside"])


def test_list_vault_folders_excludes_hidden_and_system_dirs(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "20_actions").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / ".git").mkdir()
    (vault / "21_notes" / "project").mkdir(parents=True)

    def fake_get_setting(key, default=None):
        if key == "knowledge_vault_root":
            return str(vault)
        if key == "knowledge_excluded_dirs":
            return [".obsidian", ".git"]
        return default

    monkeypatch.setattr("src.knowledge_base.get_setting", fake_get_setting)

    data = list_vault_folders(recursive=True, max_depth=3)
    paths = {item["path"] for item in data["folders"]}

    assert data["configured"] is True
    assert "20_actions" in paths
    assert "21_notes" in paths
    assert "21_notes/project" in paths
    assert ".obsidian" not in paths
    assert ".git" not in paths


def test_collect_note_images_resolves_obsidian_and_markdown_refs(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    project = vault / "21_notes" / "project"
    assets = project / "assets"
    attachments = project / "attachments" / "codexian"
    assets.mkdir(parents=True)
    attachments.mkdir(parents=True)
    (assets / "screen.png").write_bytes(b"png")
    (attachments / "flow.jpg").write_bytes(b"jpg")
    note = project / "overview.md"
    note.write_text(
        "\n".join([
            "![[assets/screen.png|600]]",
            "![flow](attachments/codexian/flow.jpg)",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.knowledge_base.get_setting", lambda key, default=None: str(vault) if key == "knowledge_vault_root" else default)

    images = collect_note_images(note, roots=[project])
    urls = [img["url"] for img in images]

    assert urls == [
        "vault-image://21_notes/project/assets/screen.png",
        "vault-image://21_notes/project/attachments/codexian/flow.jpg",
    ]


@pytest.mark.asyncio
async def test_knowledge_only_research_does_not_call_web_search():
    calls = {"web": 0, "knowledge": 0}

    async def fake_knowledge_search(_query):
        calls["knowledge"] += 1
        return [{
            "url": "vault://21_notes/project.md#chunk-0",
            "title": "Obsidian: project.md",
            "summary": "Internal note summary",
            "evidence": "Internal note evidence",
            "source_path": "21_notes/project.md",
        }]

    researcher = DeepResearcher(
        llm_endpoint="http://example.invalid/v1/chat/completions",
        llm_model="test-model",
        source_mode="knowledge",
        knowledge_searcher=fake_knowledge_search,
    )

    async def fail_web_search(_query):
        calls["web"] += 1
        raise AssertionError("web search should not be called in knowledge-only mode")

    researcher._search = fail_web_search

    findings = await researcher._search_and_extract(["project context"], "question")

    assert calls == {"web": 0, "knowledge": 1}
    assert findings[0]["source_type"] == "obsidian"
    assert findings[0]["url"].startswith("vault://")
