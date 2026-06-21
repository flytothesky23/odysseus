"""Obsidian-vault knowledge source helpers for Deep Research.

The public surface is intentionally narrow: callers can only read/index files
under the configured ``knowledge_vault_root`` setting, and hidden/system
folders are skipped by default.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, unquote, urlparse

from src.settings import get_setting


DEFAULT_EXCLUDED_DIRS = {
    ".obsidian",
    ".trash",
    ".git",
    ".omx",
    ".codexian",
    "node_modules",
    "__pycache__",
}

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".csv",
    ".html", ".css", ".js", ".py", ".pdf",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_NOTE_IMAGES = 12

_OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)


class KnowledgeBaseError(ValueError):
    """Raised for invalid or unavailable knowledge-base configuration."""


def normalize_source_mode(value: Optional[str]) -> str:
    mode = (value or "").strip().lower()
    if mode in {"hybrid", "mixed", "web+knowledge", "web_knowledge"}:
        return "hybrid"
    if mode in {"knowledge", "local", "obsidian", "vault"}:
        return "knowledge"
    return "web"


def configured_vault_root() -> Optional[Path]:
    raw = str(get_setting("knowledge_vault_root", "") or "").strip()
    if not raw:
        return None
    root = Path(os.path.expanduser(raw)).resolve()
    if not root.exists() or not root.is_dir():
        return None
    return root


def excluded_dirs() -> set[str]:
    configured = get_setting("knowledge_excluded_dirs", None)
    if isinstance(configured, list):
        values = {str(item).strip() for item in configured if str(item).strip()}
        return values or set(DEFAULT_EXCLUDED_DIRS)
    return set(DEFAULT_EXCLUDED_DIRS)


def _is_excluded_dir(path: Path, excluded: set[str]) -> bool:
    name = path.name
    return name in excluded or name.startswith(".")


def _path_has_excluded_dir(path: Path, root: Path, excluded: set[str]) -> bool:
    try:
        rel_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    # Ignore the file basename; only directory components can be excluded.
    for part in rel_parts[:-1]:
        if part in excluded or part.startswith("."):
            return True
    return False


def _resolve_under_root(root: Path, rel_path: str = "") -> Path:
    rel = str(rel_path or "").strip().strip("/")
    if rel in {"", ".", "./"}:
        return root
    if rel.startswith("..") or Path(rel).is_absolute():
        raise KnowledgeBaseError("Folder must be relative to the configured vault root.")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise KnowledgeBaseError("Folder escapes the configured vault root.") from exc
    if not target.exists() or not target.is_dir():
        raise KnowledgeBaseError(f"Folder does not exist under the vault root: {rel}")
    return target


def resolve_selected_folders(folders: Optional[Iterable[str]]) -> List[Path]:
    root = configured_vault_root()
    if root is None:
        raise KnowledgeBaseError("Knowledge vault root is not configured or does not exist.")

    requested = [str(f or "").strip() for f in (folders or []) if str(f or "").strip()]
    if not requested:
        return [root]

    resolved: List[Path] = []
    seen = set()
    for rel in requested:
        path = _resolve_under_root(root, rel)
        key = str(path)
        if key not in seen:
            resolved.append(path)
            seen.add(key)
    return resolved


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _clean_image_ref(ref: str) -> str:
    value = unquote(str(ref or "").strip().strip("<>").strip())
    # Obsidian embeds can include aliases/sizes: ![[image.png|600]]
    value = value.split("|", 1)[0].split("#", 1)[0].strip()
    # Markdown image URLs can include a quoted title after the path.
    value = re.sub(r"\s+[\"'][^\"']*[\"']\s*$", "", value).strip()
    return value


def _iter_markdown_image_refs(text: str) -> Iterable[str]:
    if not isinstance(text, str) or "!" not in text and "<img" not in text.lower():
        return []
    refs: List[str] = []
    refs.extend(m.group(1) for m in _OBSIDIAN_IMAGE_RE.finditer(text))
    refs.extend(m.group(1) for m in _MARKDOWN_IMAGE_RE.finditer(text))
    refs.extend(m.group(1) for m in _HTML_IMAGE_RE.finditer(text))
    return refs


def _is_local_image_ref(ref: str) -> bool:
    ref = _clean_image_ref(ref)
    if not ref:
        return False
    parsed = urlparse(ref)
    if parsed.scheme and parsed.scheme.lower() not in {"file"}:
        return False
    path_part = parsed.path or ref
    return Path(path_part).suffix.lower() in IMAGE_EXTENSIONS


def _valid_vault_image(path: Path, vault_root: Path, excluded: set[str]) -> Optional[Path]:
    try:
        resolved = path.expanduser().resolve()
        resolved.relative_to(vault_root.resolve())
    except Exception:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    if resolved.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    if _path_has_excluded_dir(resolved, vault_root, excluded):
        return None
    return resolved


def _resolve_image_reference(
    vault_root: Path,
    note_path: Path,
    ref: str,
    *,
    roots: Optional[Iterable[Path]] = None,
) -> Optional[Path]:
    ref = _clean_image_ref(ref)
    if not _is_local_image_ref(ref):
        return None
    parsed = urlparse(ref)
    ref_path = Path(parsed.path or ref)
    excluded = excluded_dirs()
    resolved_roots: List[Path] = []
    for root in roots or []:
        try:
            candidate_root = root.resolve()
            candidate_root.relative_to(vault_root.resolve())
            if candidate_root not in resolved_roots:
                resolved_roots.append(candidate_root)
        except Exception:
            continue

    candidates: List[Path] = []
    if ref_path.is_absolute():
        candidates.append(ref_path)
    else:
        candidates.append(note_path.parent / ref_path)
        candidates.extend(root / ref_path for root in resolved_roots)
        candidates.append(vault_root / ref_path)
        # Common Obsidian attachment conventions for bare filenames.
        name = ref_path.name
        if name:
            candidates.extend([
                note_path.parent / "assets" / name,
                note_path.parent / "attachments" / name,
            ])
            for root in resolved_roots:
                candidates.extend([root / "assets" / name, root / "attachments" / name])
            candidates.extend([vault_root / "assets" / name, vault_root / "attachments" / name])

    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        valid = _valid_vault_image(candidate, vault_root, excluded)
        if valid is not None:
            return valid

    # Last resort for Obsidian-style bare embeds: locate by basename inside the
    # selected roots before widening to the whole vault.
    if ref_path.name and not any(part in ref for part in ("/", "\\")):
        search_roots = [note_path.parent, *resolved_roots, vault_root]
        searched = set()
        for root in search_roots:
            try:
                root = root.resolve()
            except Exception:
                continue
            if str(root) in searched or not root.exists():
                continue
            searched.add(str(root))
            try:
                for candidate in root.rglob(ref_path.name):
                    valid = _valid_vault_image(candidate, vault_root, excluded)
                    if valid is not None:
                        return valid
            except OSError:
                continue
    return None


def collect_note_images(
    note_path: Path,
    *,
    roots: Optional[Iterable[Path]] = None,
    markdown_text: Optional[str] = None,
    max_images: int = MAX_NOTE_IMAGES,
) -> List[Dict[str, str]]:
    """Resolve local Obsidian image embeds from a markdown note.

    Returns compact image descriptors using ``vault-image://`` URLs. The visual
    report renderer later validates these URLs against the configured vault root
    and embeds the bytes as data URLs, so raw local filesystem paths never reach
    the browser.
    """
    vault_root = configured_vault_root()
    if vault_root is None:
        return []
    try:
        note_path = note_path.resolve()
        note_path.relative_to(vault_root.resolve())
    except Exception:
        return []
    if note_path.suffix.lower() not in {".md", ".markdown"}:
        return []
    if markdown_text is None:
        try:
            markdown_text = note_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

    images: List[Dict[str, str]] = []
    seen = set()
    max_images = max(1, min(int(max_images or MAX_NOTE_IMAGES), 40))
    for ref in _iter_markdown_image_refs(markdown_text):
        path = _resolve_image_reference(vault_root, note_path, ref, roots=roots)
        if path is None:
            continue
        rel = _relative(vault_root, path)
        if rel in seen:
            continue
        seen.add(rel)
        images.append({
            "url": f"vault-image://{quote(rel, safe='/')}",
            "title": path.stem.replace("_", " ").replace("-", " "),
            "source_path": rel,
        })
        if len(images) >= max_images:
            break
    return images


def list_vault_folders(
    parent: str = "",
    *,
    recursive: bool = False,
    max_depth: int = 3,
    max_items: int = 500,
) -> Dict[str, Any]:
    root = configured_vault_root()
    if root is None:
        return {
            "configured": False,
            "root": "",
            "folders": [],
            "message": "Knowledge vault root is not configured or does not exist.",
        }

    excluded = excluded_dirs()
    base = _resolve_under_root(root, parent)
    max_depth = max(1, min(int(max_depth or 1), 6))
    max_items = max(1, min(int(max_items or 500), 5000))
    folders: List[Dict[str, Any]] = []

    def has_allowed_child(path: Path) -> bool:
        try:
            return any(
                child.is_dir() and not _is_excluded_dir(child, excluded)
                for child in path.iterdir()
            )
        except OSError:
            return False

    def walk(path: Path, depth: int) -> None:
        if len(folders) >= max_items:
            return
        try:
            children = sorted(
                (p for p in path.iterdir() if p.is_dir() and not _is_excluded_dir(p, excluded)),
                key=lambda p: p.name.casefold(),
            )
        except OSError:
            return
        for child in children:
            if len(folders) >= max_items:
                return
            rel = _relative(root, child)
            folders.append({
                "name": child.name,
                "path": rel,
                "depth": len(Path(rel).parts),
                "has_children": has_allowed_child(child),
            })
            if recursive and depth + 1 < max_depth:
                walk(child, depth + 1)

    walk(base, 0)
    return {
        "configured": True,
        "root": str(root),
        "parent": _relative(root, base) if base != root else "",
        "folders": folders,
        "truncated": len(folders) >= max_items,
    }


def _iter_supported_files(directory: Path):
    excluded = excluded_dirs()
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            d for d in dirs
            if not _is_excluded_dir(Path(root) / d, excluded)
        ]
        for fname in files:
            path = Path(root) / fname
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield path


def _read_file_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from src.personal_docs import extract_pdf_text

        return extract_pdf_text(str(path))
    return path.read_text(encoding="utf-8", errors="ignore")


def index_knowledge_folders(rag, folders: Optional[Iterable[str]], owner: str = "") -> Dict[str, Any]:
    roots = resolve_selected_folders(folders)
    vault_root = configured_vault_root()
    if vault_root is None:
        raise KnowledgeBaseError("Knowledge vault root is not configured or does not exist.")
    indexed = 0
    failed = 0
    files_seen = 0

    for folder in roots:
        for path in _iter_supported_files(folder):
            files_seen += 1
            try:
                content = _read_file_text(path)
            except Exception:
                failed += 1
                continue
            if not content or not content.strip():
                continue
            rel = _relative(vault_root, path)
            meta = {
                "source": str(path),
                "filename": path.name,
                "directory": str(path.parent),
                "vault_relative_path": rel,
                "type": path.suffix.lower(),
                "source_kind": "obsidian",
            }
            if owner:
                meta["owner"] = owner
            try:
                chunks = rag._split_into_chunks(content)
            except Exception:
                chunks = [content]
            for i, chunk in enumerate(chunks):
                if rag.add_document(chunk, {**meta, "chunk_id": i}):
                    indexed += 1
                else:
                    failed += 1

    return {
        "success": True,
        "folders": [_relative(vault_root, p) if p != vault_root else "" for p in roots],
        "files_seen": files_seen,
        "indexed_count": indexed,
        "failed_count": failed,
    }


def _path_is_under_any(path: str, roots: List[Path]) -> bool:
    try:
        resolved = Path(path).resolve()
    except Exception:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def search_knowledge_sources(
    query: str,
    *,
    owner: str = "",
    folders: Optional[Iterable[str]] = None,
    limit: int = 12,
    auto_index: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    from src.rag_singleton import get_rag_manager

    rag = get_rag_manager()
    if rag is None:
        raise KnowledgeBaseError("Knowledge vector index is unavailable.")
    roots = resolve_selected_folders(folders)
    vault_root = configured_vault_root()
    if vault_root is None:
        raise KnowledgeBaseError("Knowledge vault root is not configured or does not exist.")

    if auto_index is None:
        auto_index = bool(get_setting("research_knowledge_auto_index", True))
    if auto_index:
        index_knowledge_folders(rag, folders, owner=owner)

    limit = max(1, min(int(limit or 12), 50))
    raw = rag.search(query, k=max(limit * 8, 40), owner=owner or None)
    items: List[Dict[str, Any]] = []
    seen = set()
    for result in raw:
        meta = result.get("metadata") or {}
        source = meta.get("source") or ""
        if not source or not _path_is_under_any(source, roots):
            continue
        rel = meta.get("vault_relative_path") or _relative(vault_root, Path(source))
        chunk_id = meta.get("chunk_id", "")
        key = f"{rel}#{chunk_id}"
        if key in seen:
            continue
        seen.add(key)
        document = str(result.get("document") or "")
        title = meta.get("filename") or Path(source).name or rel
        item = {
            "url": f"vault://{rel}#chunk-{chunk_id}",
            "title": f"Obsidian: {title}",
            "source_path": rel,
            "source_kind": "obsidian",
            "summary": document[:1200],
            "evidence": document[:3000],
            "similarity": result.get("similarity"),
        }
        images = collect_note_images(Path(source), roots=roots)
        if images:
            item["images"] = images
        items.append(item)
        if len(items) >= limit:
            break
    return items
