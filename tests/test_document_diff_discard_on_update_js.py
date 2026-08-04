"""Regression guard for issue #2467 — cross-document overwrite via a stale AI-edit diff.

document.js keeps the AI-edit diff state (``_diffModeActive`` / ``_diffOldContent`` /
``_diffNewContent`` / ``_diffChunks``) as a module-global singleton bound to whatever
document was active when the diff opened. ``handleDocUpdate()`` switches the active
document (``activeDocId``) whenever an AI update targets a different doc. If a pending
diff is not discarded first, a later tab switch (``switchToDoc`` → ``exitDiffMode(true)``)
or Accept/Reject-All flushes the stale diff's content into the now-active document and
silently overwrites it.

The fix discards any pending diff while ``activeDocId`` still points at the
previously-active doc, mirroring the guard ``switchToDoc()`` and ``enterDiffMode()``
already use. It must run in BOTH places that switch the active document for an AI
update: ``handleDocUpdate()`` and ``streamDocOpen()``. The streamed path matters most —
when the AI creates a NEW document (the issue's own repro), ``streamDocOpen`` reassigns
``activeDocId`` first, so a guard only in ``handleDocUpdate`` would fire too late and
still overwrite the new doc. Kept as a static source check because document.js is
browser-coupled and not importable in pytest.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_JS = (ROOT / "static/js/document.js").read_text()
DOC_CACHE_KEY = "20260804webcontext2"

AUTHORITATIVE_UPDATE_GUARD = "if (_diffModeActive) exitDiffMode(true, false);"


def _function_body(src: str, signature: str) -> str:
    """Return the full text of a JS function, brace-matched from its signature."""
    start = src.index(signature)
    depth = 0
    i = src.index("{", start)
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces after {signature!r}")


HANDLE_DOC_UPDATE = _function_body(DOC_JS, "export function handleDocUpdate(data)")
STREAM_DOC_OPEN = _function_body(DOC_JS, "export function streamDocOpen(title, language)")
_SAVE_DOCUMENT_START = DOC_JS.index("export async function saveDocument(")
_SAVE_DOCUMENT_END = DOC_JS.index("\n  /**", _SAVE_DOCUMENT_START + 1)
SAVE_DOCUMENT = DOC_JS[_SAVE_DOCUMENT_START:_SAVE_DOCUMENT_END]
STALE_SAVE_RECOVERY = _function_body(DOC_JS, "async function _recoverStaleDocumentSave(docId, localContent)")


def test_handle_doc_update_discards_pending_diff():
    # A new AI update on a different document must not leave a stale diff bound
    # to the old doc, or a later tab switch / Accept-All overwrites the wrong doc.
    assert AUTHORITATIVE_UPDATE_GUARD in HANDLE_DOC_UPDATE


def test_diff_discard_runs_before_active_doc_is_switched():
    # The discard must run while activeDocId still points at the previously
    # active doc, and it must not persist the stale body. Any activeDocId
    # reassignment inside handleDocUpdate must come after it.
    guard_at = HANDLE_DOC_UPDATE.index(AUTHORITATIVE_UPDATE_GUARD)
    reassign_at = HANDLE_DOC_UPDATE.index("activeDocId = docId;")
    assert guard_at < reassign_at


def test_stream_doc_open_discards_pending_diff_before_switching():
    # The AI-creates-a-new-document path switches activeDocId inside
    # streamDocOpen (before any doc_update reaches handleDocUpdate), so the guard
    # must be here too — and before streamDocOpen reassigns activeDocId, or the
    # streamed new doc gets overwritten by the stale diff (the issue's own repro).
    assert AUTHORITATIVE_UPDATE_GUARD in STREAM_DOC_OPEN
    assert STREAM_DOC_OPEN.index(AUTHORITATIVE_UPDATE_GUARD) < STREAM_DOC_OPEN.index("activeDocId = docId;")


def test_authoritative_update_discard_never_persists_the_stale_editor_body():
    exit_body = _function_body(DOC_JS, "function exitDiffMode(discard, persist = true)")

    assert "if (persist) saveDocument({ silent: true });" in exit_body
    assert DOC_JS.count(AUTHORITATIVE_UPDATE_GUARD) >= 2


def test_autosave_does_not_persist_unresolved_ai_diff_body():
    guard = "if (_diffModeActive) return;"

    assert guard in SAVE_DOCUMENT
    assert SAVE_DOCUMENT.index(guard) < SAVE_DOCUMENT.index("saveCurrentToMap();")


def test_stale_manual_save_refreshes_latest_version_and_preserves_local_body_for_review():
    assert "res.status === 409" in SAVE_DOCUMENT
    assert "detail.code === 'stale_document_version'" in SAVE_DOCUMENT
    assert "await _recoverStaleDocumentSave(savingDocId, contentToSave);" in SAVE_DOCUMENT

    assert "credentials: 'same-origin'" in STALE_SAVE_RECOVERY
    assert "tracked.version = latest.version_count" in STALE_SAVE_RECOVERY
    assert "enterDiffMode(latestContent, localContent);" in STALE_SAVE_RECOVERY
    assert STALE_SAVE_RECOVERY.index("tracked.version = latest.version_count") < STALE_SAVE_RECOVERY.index(
        "enterDiffMode(latestContent, localContent);"
    )


def test_stale_save_tab_switch_does_not_replace_unreviewed_local_content_offscreen():
    guard = "if (activeDocId !== docId) return false;"

    assert guard in STALE_SAVE_RECOVERY
    assert STALE_SAVE_RECOVERY.index(guard) < STALE_SAVE_RECOVERY.index("tracked.content = latestContent;")


def test_document_module_cache_key_is_bumped_consistently():
    references = [
        ROOT / "static/index.html",
        ROOT / "static/app.js",
        ROOT / "static/js/chat.js",
        ROOT / "static/js/chatStream.js",
        ROOT / "static/js/slashCommands.js",
        ROOT / "static/js/chatRenderer.js",
        ROOT / "static/js/emailLibrary.js",
    ]

    for path in references:
        source = path.read_text()
        assert f"document.js?v={DOC_CACHE_KEY}" in source, path
