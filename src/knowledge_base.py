"""Local knowledge source helpers for Deep Research.

The public surface is intentionally narrow: callers can only read/index files
under the configured Obsidian vault root or user-added local knowledge roots.
Hidden/system folders and sensitive auth/config filenames are skipped.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, unquote, urlparse

from src.constants import DEEP_RESEARCH_DIR
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
SENSITIVE_FILENAMES = {
    ".env", ".env.local", ".env.production", "auth.json", "sessions.json",
    "credentials.json", "token.json", "tokens.json", "secrets.json",
}
SENSITIVE_NAME_RE = re.compile(
    r"(^|[._-])(auth|credential|credentials|secret|secrets|token|tokens|"
    r"api[._-]?key|private[._-]?key|oauth)([._-]|$)",
    re.IGNORECASE,
)
SENSITIVE_CONTENT_RE = re.compile(
    r"""(?im)(?<![A-Z0-9_-])(["']?(?:proxy[_-]?authorization|authorization|"""
    r"""x[_-]?api[_-]?key|api[_-]?key|access[_-]?token|refresh[_-]?token|"""
    r"""provider[_-]?token|client[_-]?secret|password)["']?\s*[:=]\s*)"""
    r"""(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\r\n,;}]+)"""
)
PROVIDER_TOKEN_RE = re.compile(
    r"""(?ix)(?<![A-Z0-9_-])(?:"""
    r"""sk-[A-Z0-9_-]{8,}|"""
    r"""gh[pousr]_[A-Z0-9]{8,}|"""
    r"""xox[baprs]-[A-Z0-9-]{8,}|"""
    r"""hf_[A-Z0-9_-]{8,}|"""
    r"""AIza[A-Z0-9_-]{16,}|"""
    r"""glpat-[A-Z0-9_-]{8,}|"""
    r"""npm_[A-Z0-9]{8,}"""
    r""")(?![A-Z0-9_-])"""
)
LOCAL_FOLDER_TOKEN_PREFIX = "local:"
OBSIDIAN_FOLDER_TOKEN_PREFIX = "obsidian:"
OBSIDIAN_ROOT_TOKEN = "obsidian:"
MAX_FILE_TEXT_CHARS = 500_000
MAX_STRUCTURED_FILE_BYTES = 2_000_000
MAX_STRUCTURED_ROWS = 500
MAX_STRUCTURED_SCALARS = 2000
MAX_NOTE_IMAGES = 12
KNOWLEDGE_INDEX_STATE_PATH = Path(DEEP_RESEARCH_DIR) / "knowledge-index-state.json"

_INDEX_STATE_LOCK = threading.RLock()
_INDEX_OWNER_LOCKS: Dict[str, threading.RLock] = {}

_OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)


class KnowledgeBaseError(ValueError):
    """Raised for invalid or unavailable knowledge-base configuration."""


@dataclass(frozen=True)
class KnowledgeSourceRoot:
    path: Path
    source_kind: str
    token: str
    label: str
    display_root: Path
    relative_path: str = ""


def normalize_source_mode(value: Optional[str]) -> str:
    mode = (value or "").strip().lower()
    if mode in {
        "hybrid", "mixed", "web+knowledge", "web_knowledge", "web_all",
        "web+all", "web_obsidian_local", "web+obsidian+local",
        "web_local", "web+local", "web_obsidian", "web+obsidian",
    }:
        return "hybrid"
    if mode in {"knowledge", "local", "local_only", "local-knowledge", "obsidian", "obsidian_only", "vault"}:
        return "knowledge"
    return "web"


def knowledge_scope_for_source_mode(value: Optional[str]) -> str:
    mode = (value or "").strip().lower()
    if mode in {"local", "local_only", "local-knowledge", "web_local", "web+local"}:
        return "local"
    if mode in {"obsidian", "obsidian_only", "vault", "web_obsidian", "web+obsidian"}:
        return "obsidian"
    if mode in {
        "knowledge", "hybrid", "mixed", "web+knowledge", "web_knowledge",
        "web_all", "web+all", "web_obsidian_local", "web+obsidian+local",
    }:
        return "all"
    return "none"


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
    for part in rel_parts[:-1]:
        if part in excluded or part.startswith("."):
            return True
    return False


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _resolve_under_root(root: Path, rel_path: str = "") -> Path:
    rel = str(rel_path or "").strip().strip("/")
    if rel in {"", ".", "./"}:
        return root
    if rel.startswith("..") or Path(rel).is_absolute():
        raise KnowledgeBaseError("Folder must be relative to the configured root.")
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise KnowledgeBaseError("Folder escapes the configured root.") from exc
    if not target.exists() or not target.is_dir():
        raise KnowledgeBaseError(f"Folder does not exist under the configured root: {rel}")
    return target


def _local_root_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]


def _validate_local_root(path: str | Path) -> Path:
    raw = str(path or "").strip()
    if not raw:
        raise KnowledgeBaseError("Folder path is required.")
    root = Path(os.path.expanduser(raw)).resolve()
    if not root.exists() or not root.is_dir():
        raise KnowledgeBaseError("Folder does not exist or is not a directory.")
    if root == Path(root.anchor).resolve():
        raise KnowledgeBaseError("Filesystem root cannot be used as a knowledge source.")
    try:
        if root == Path.home().resolve():
            raise KnowledgeBaseError("Choose a specific subfolder, not the whole home folder.")
    except Exception:
        pass
    if _is_excluded_dir(root, excluded_dirs()):
        raise KnowledgeBaseError("Hidden/system folders cannot be used as knowledge sources.")
    return root


def _local_folder_token(root_id: str, rel_path: str = "") -> str:
    token = f"{LOCAL_FOLDER_TOKEN_PREFIX}{root_id}"
    rel = str(rel_path or "").strip().strip("/")
    if rel:
        token += f":{quote(rel, safe='/')}"
    return token


def _obsidian_folder_token(rel_path: str = "") -> str:
    rel = str(rel_path or "").strip().strip("/")
    if not rel:
        return OBSIDIAN_ROOT_TOKEN
    return f"{OBSIDIAN_FOLDER_TOKEN_PREFIX}{quote(rel, safe='/')}"


def _normalize_local_root_config(item: Any) -> Optional[Dict[str, str]]:
    if isinstance(item, str):
        raw_path, raw_label, raw_id = item, "", ""
    elif isinstance(item, dict):
        raw_path, raw_label, raw_id = item.get("path") or "", item.get("label") or "", item.get("id") or ""
    else:
        return None
    try:
        path = _validate_local_root(raw_path)
    except KnowledgeBaseError:
        return None
    root_id = str(raw_id or _local_root_id(path)).strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{6,64}", root_id):
        root_id = _local_root_id(path)
    label = str(raw_label or path.name or str(path)).strip()
    return {
        "id": root_id,
        "label": label,
        "path": str(path),
        "token": _local_folder_token(root_id),
        "source_kind": "local",
    }


def configured_local_roots() -> List[Dict[str, str]]:
    configured = get_setting("knowledge_local_roots", [])
    if not isinstance(configured, list):
        return []
    roots: List[Dict[str, str]] = []
    seen_paths = set()
    seen_ids = set()
    for item in configured:
        root = _normalize_local_root_config(item)
        if not root:
            continue
        if root["path"] in seen_paths or root["id"] in seen_ids:
            continue
        roots.append(root)
        seen_paths.add(root["path"])
        seen_ids.add(root["id"])
    return roots


def add_local_knowledge_root(path: str, label: str = "") -> Dict[str, str]:
    """Persist a user-selected local folder as a selectable knowledge source."""
    from src.settings import load_settings, save_settings

    root_path = _validate_local_root(path)
    settings = load_settings()
    roots = configured_local_roots()
    root_id = _local_root_id(root_path)
    normalized = {
        "id": root_id,
        "label": str(label or root_path.name or str(root_path)).strip(),
        "path": str(root_path),
        "token": _local_folder_token(root_id),
        "source_kind": "local",
    }
    for i, root in enumerate(roots):
        if root["path"] == normalized["path"] or root["id"] == normalized["id"]:
            roots[i] = {**root, **normalized}
            break
    else:
        roots.append(normalized)
    settings["knowledge_local_roots"] = [
        {"id": root["id"], "label": root["label"], "path": root["path"]}
        for root in roots
    ]
    save_settings(settings)
    return normalized


def remove_local_knowledge_root(root_id: str) -> bool:
    from src.settings import load_settings, save_settings

    root_id = str(root_id or "").strip()
    if not root_id:
        return False
    settings = load_settings()
    roots = configured_local_roots()
    kept = [root for root in roots if root["id"] != root_id]
    if len(kept) == len(roots):
        return False
    settings["knowledge_local_roots"] = [
        {"id": root["id"], "label": root["label"], "path": root["path"]}
        for root in kept
    ]
    save_settings(settings)
    return True


def _split_local_folder_token(token: str) -> tuple[str, str]:
    value = str(token or "").strip()
    if not value.startswith(LOCAL_FOLDER_TOKEN_PREFIX):
        raise KnowledgeBaseError("Invalid local knowledge-source token.")
    root_id, sep, rel = value[len(LOCAL_FOLDER_TOKEN_PREFIX):].partition(":")
    if not root_id:
        raise KnowledgeBaseError("Invalid local knowledge-source token.")
    return root_id, unquote(rel) if sep else ""


def _split_obsidian_folder_token(token: str) -> str:
    value = str(token or "").strip()
    if not value.startswith(OBSIDIAN_FOLDER_TOKEN_PREFIX):
        raise KnowledgeBaseError("Invalid Obsidian knowledge-source token.")
    return unquote(value[len(OBSIDIAN_FOLDER_TOKEN_PREFIX):])


def _local_source_from_token(token: str, local_roots: List[Dict[str, str]]) -> KnowledgeSourceRoot:
    root_id, rel = _split_local_folder_token(token)
    root = next((item for item in local_roots if item["id"] == root_id), None)
    if not root:
        raise KnowledgeBaseError("Local knowledge folder is not configured.")
    base = Path(root["path"]).resolve()
    path = _resolve_under_root(base, rel)
    rel_path = _relative(base, path) if path != base else ""
    return KnowledgeSourceRoot(path, "local", _local_folder_token(root_id, rel_path), root["label"], base, rel_path)


def _obsidian_source(root: Path, rel: str = "") -> KnowledgeSourceRoot:
    path = _resolve_under_root(root, rel)
    rel_path = _relative(root, path) if path != root else ""
    return KnowledgeSourceRoot(path, "obsidian", _obsidian_folder_token(rel_path), "Obsidian", root, rel_path)


def knowledge_folders_for_source_mode(source_mode: Optional[str], folders: Optional[Iterable[str]]) -> List[str]:
    """Filter/default selected folder tokens for the chosen source dropdown mode."""
    scope = knowledge_scope_for_source_mode(source_mode)
    selected = [str(f or "").strip() for f in (folders or []) if str(f or "").strip()]
    if scope == "none":
        return []
    if scope == "all":
        return selected
    if scope == "local":
        local_selected = [token for token in selected if token.startswith(LOCAL_FOLDER_TOKEN_PREFIX)]
        if local_selected:
            return local_selected
        local_roots = configured_local_roots()
        if not local_roots:
            raise KnowledgeBaseError("Local knowledge folder is not configured.")
        return [root["token"] for root in local_roots]
    if scope == "obsidian":
        obsidian_selected = [token for token in selected if not token.startswith(LOCAL_FOLDER_TOKEN_PREFIX)]
        if obsidian_selected:
            return obsidian_selected
        if configured_vault_root() is None:
            raise KnowledgeBaseError("Knowledge vault root is not configured or does not exist.")
        return [OBSIDIAN_ROOT_TOKEN]
    return selected


def _resolve_selected_sources(folders: Optional[Iterable[str]]) -> List[KnowledgeSourceRoot]:
    vault_root = configured_vault_root()
    local_roots = configured_local_roots()
    requested = [str(f or "").strip() for f in (folders or []) if str(f or "").strip()]
    if not requested:
        resolved: List[KnowledgeSourceRoot] = []
        if vault_root is not None:
            resolved.append(_obsidian_source(vault_root))
        resolved.extend(
            KnowledgeSourceRoot(
                Path(root["path"]).resolve(), "local", root["token"], root["label"], Path(root["path"]).resolve()
            )
            for root in local_roots
        )
        if resolved:
            return resolved
        raise KnowledgeBaseError("Knowledge source root is not configured or does not exist.")

    resolved = []
    seen = set()
    for token in requested:
        if token.startswith(LOCAL_FOLDER_TOKEN_PREFIX):
            source = _local_source_from_token(token, local_roots)
        elif token.startswith(OBSIDIAN_FOLDER_TOKEN_PREFIX):
            if vault_root is None:
                raise KnowledgeBaseError("Knowledge vault root is not configured or does not exist.")
            source = _obsidian_source(vault_root, _split_obsidian_folder_token(token))
        else:
            if vault_root is None:
                raise KnowledgeBaseError("Knowledge vault root is not configured or does not exist.")
            source = _obsidian_source(vault_root, token)
        key = f"{source.source_kind}:{source.path}"
        if key not in seen:
            resolved.append(source)
            seen.add(key)
    return resolved


def resolve_selected_folders(folders: Optional[Iterable[str]]) -> List[Path]:
    return [source.path for source in _resolve_selected_sources(folders)]


def list_vault_folders(
    parent: str = "",
    *,
    recursive: bool = False,
    max_depth: int = 3,
    max_items: int = 500,
) -> Dict[str, Any]:
    root = configured_vault_root()
    if root is None:
        return {"configured": False, "root": "", "folders": [], "message": "Knowledge vault root is not configured or does not exist."}
    excluded = excluded_dirs()
    base = _resolve_under_root(root, parent)
    max_depth = max(1, min(int(max_depth or 1), 6))
    max_items = max(1, min(int(max_items or 500), 5000))
    folders: List[Dict[str, Any]] = []

    def has_allowed_child(path: Path) -> bool:
        try:
            return any(child.is_dir() and not _is_excluded_dir(child, excluded) for child in path.iterdir())
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
            folders.append({"name": child.name, "path": rel, "depth": len(Path(rel).parts), "has_children": has_allowed_child(child)})
            if recursive and depth + 1 < max_depth:
                walk(child, depth + 1)

    walk(base, 0)
    return {"configured": True, "root": str(root), "parent": _relative(root, base) if base != root else "", "folders": folders, "truncated": len(folders) >= max_items}


def list_knowledge_folders(
    parent: str = "",
    *,
    recursive: bool = False,
    max_depth: int = 3,
    max_items: int = 500,
) -> Dict[str, Any]:
    """List selectable Obsidian and user-added local knowledge folders."""
    vault_root = configured_vault_root()
    local_roots = configured_local_roots()
    folders: List[Dict[str, Any]] = []
    max_items = max(1, min(int(max_items or 500), 5000))

    if vault_root is not None:
        folders.append({
            "name": vault_root.name or "Obsidian",
            "path": OBSIDIAN_ROOT_TOKEN,
            "token": OBSIDIAN_ROOT_TOKEN,
            "depth": 1,
            "has_children": True,
            "source_kind": "obsidian",
            "source_label": "Obsidian",
            "display_path": "Obsidian 전체 Vault",
            "absolute_path": str(vault_root),
        })
        for item in list_vault_folders(parent, recursive=recursive, max_depth=max_depth, max_items=max_items).get("folders", []):
            rel = item.get("path", "")
            token = _obsidian_folder_token(rel)
            folders.append({
                **item,
                "path": token,
                "token": token,
                "source_kind": "obsidian",
                "source_label": "Obsidian",
                "display_path": rel,
                "absolute_path": str((vault_root / rel).resolve()) if rel else str(vault_root),
            })

    if len(folders) < max_items and local_roots:
        excluded = excluded_dirs()

        def has_allowed_child(path: Path) -> bool:
            try:
                return any(child.is_dir() and not _is_excluded_dir(child, excluded) for child in path.iterdir())
            except OSError:
                return False

        def append_local(root: Dict[str, str], path: Path, depth: int) -> None:
            if len(folders) >= max_items:
                return
            base = Path(root["path"]).resolve()
            rel = _relative(base, path) if path != base else ""
            token = _local_folder_token(root["id"], rel)
            display = root["label"] if not rel else f"{root['label']}/{rel}"
            folders.append({
                "name": path.name or root["label"],
                "path": token,
                "token": token,
                "depth": depth,
                "has_children": has_allowed_child(path),
                "source_kind": "local",
                "source_label": root["label"],
                "display_path": display,
                "absolute_path": str(path),
            })

        def walk_local(root: Dict[str, str], path: Path, depth: int) -> None:
            if len(folders) >= max_items or depth >= max_depth:
                return
            try:
                children = sorted((p for p in path.iterdir() if p.is_dir() and not _is_excluded_dir(p, excluded)), key=lambda p: p.name.casefold())
            except OSError:
                return
            for child in children:
                append_local(root, child, depth + 1)
                if recursive:
                    walk_local(root, child, depth + 1)

        for root in local_roots:
            base = Path(root["path"]).resolve()
            append_local(root, base, 1)
            if recursive:
                walk_local(root, base, 1)

    return {
        "configured": bool(vault_root or local_roots),
        "root": str(vault_root) if vault_root else "",
        "local_roots": local_roots,
        "parent": parent,
        "folders": folders[:max_items],
        "truncated": len(folders) >= max_items,
        "message": "" if (vault_root or local_roots) else "Knowledge source root is not configured or does not exist.",
    }


def _truncate_text(text: str, max_chars: int = MAX_FILE_TEXT_CHARS) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + "\n\n[truncated]"


def _read_bounded_text(path: Path, max_bytes: Optional[int] = None) -> tuple[str, bool]:
    """Read at most ``max_bytes`` before structured parsing."""
    max_bytes = int(max_bytes or MAX_STRUCTURED_FILE_BYTES)
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="ignore"), truncated


def _flatten_structured(value: Any, prefix: str = "", rows: Optional[List[str]] = None) -> List[str]:
    rows = rows if rows is not None else []
    if len(rows) >= MAX_STRUCTURED_SCALARS:
        return rows
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten_structured(child, f"{prefix}.{key}" if prefix else str(key), rows)
            if len(rows) >= MAX_STRUCTURED_SCALARS:
                break
    elif isinstance(value, list):
        for i, child in enumerate(value[:MAX_STRUCTURED_ROWS]):
            _flatten_structured(child, f"{prefix}[{i}]" if prefix else f"[{i}]", rows)
            if len(rows) >= MAX_STRUCTURED_SCALARS:
                break
    else:
        rows.append(f"{prefix or 'value'}: {value}")
    return rows


def _read_json_text(path: Path) -> str:
    raw, truncated = _read_bounded_text(path)
    if truncated:
        return _truncate_text(
            f"# JSON data (parse skipped: file exceeds {MAX_STRUCTURED_FILE_BYTES} bytes): {path.name}\n"
            f"{raw}\n[truncated before structured parse]"
        )
    rows = _flatten_structured(json.loads(raw))
    return _truncate_text(f"# JSON data: {path.name}\n" + "\n".join(rows))


def _read_yaml_text(path: Path) -> str:
    raw, truncated = _read_bounded_text(path)
    if truncated:
        return _truncate_text(
            f"# YAML data (parse skipped: file exceeds {MAX_STRUCTURED_FILE_BYTES} bytes): {path.name}\n"
            f"{raw}\n[truncated before structured parse]"
        )
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
    except Exception:
        return _truncate_text(raw)
    return _truncate_text(f"# YAML data: {path.name}\n" + "\n".join(_flatten_structured(data)))


def _read_csv_text(path: Path) -> str:
    sample, byte_truncated = _read_bounded_text(path)
    sample = sample[:MAX_FILE_TEXT_CHARS]
    reader = csv.DictReader(sample.splitlines())
    rows = [f"# CSV data: {path.name}"]
    if reader.fieldnames:
        rows.append("columns: " + ", ".join(reader.fieldnames))
    for i, row in enumerate(reader, start=1):
        if i > MAX_STRUCTURED_ROWS:
            rows.append("[truncated csv rows]")
            break
        rows.append(f"row {i}: " + "; ".join(f"{key}={value}" for key, value in row.items()))
    if byte_truncated:
        rows.append("[truncated before complete csv parse]")
    return _truncate_text("\n".join(rows))


def _read_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from src.personal_docs import extract_pdf_text
        return _redact_sensitive_content(extract_pdf_text(str(path)))
    if suffix == ".json":
        try:
            return _redact_sensitive_content(_read_json_text(path))
        except Exception:
            return _redact_sensitive_content(_truncate_text(path.read_text(encoding="utf-8", errors="ignore")))
    if suffix in {".yaml", ".yml"}:
        return _redact_sensitive_content(_read_yaml_text(path))
    if suffix == ".csv":
        try:
            return _redact_sensitive_content(_read_csv_text(path))
        except Exception:
            return _redact_sensitive_content(_truncate_text(path.read_text(encoding="utf-8", errors="ignore")))
    return _redact_sensitive_content(_truncate_text(path.read_text(encoding="utf-8", errors="ignore")))


def _redact_sensitive_content(text: str) -> str:
    """Redact common credential values before private files enter RAG/export."""
    value = str(text or "")
    value = re.sub(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        value,
        flags=re.DOTALL,
    )
    value = SENSITIVE_CONTENT_RE.sub(r"\1[REDACTED]", value)
    return PROVIDER_TOKEN_RE.sub("[REDACTED]", value)


def _is_sensitive_file(path: Path) -> bool:
    name = path.name.lower()
    return name in SENSITIVE_FILENAMES or bool(SENSITIVE_NAME_RE.search(name))


def _iter_supported_files(directory: Path):
    """Yield supported regular files confined to ``directory``.

    Symlinks are excluded at both directory and file boundaries. The resolved
    containment check is retained as defense in depth for unusual filesystem
    behavior and future iterator changes.
    """
    try:
        confined_root = directory.resolve(strict=True)
    except (OSError, RuntimeError):
        return
    if not confined_root.is_dir():
        return

    excluded = excluded_dirs()
    for root, dirs, files in os.walk(confined_root, followlinks=False):
        root_path = Path(root)
        safe_dirs = []
        for dirname in dirs:
            candidate = root_path / dirname
            if candidate.is_symlink() or _is_excluded_dir(candidate, excluded):
                continue
            try:
                candidate.resolve(strict=True).relative_to(confined_root)
            except (OSError, RuntimeError, ValueError):
                continue
            safe_dirs.append(dirname)
        dirs[:] = safe_dirs

        for fname in files:
            path = root_path / fname
            if path.is_symlink():
                continue
            if _is_sensitive_file(path):
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(confined_root)
            except (OSError, RuntimeError, ValueError):
                continue
            if resolved.is_file():
                yield resolved


def _index_owner_key(owner: str) -> str:
    return hashlib.sha256(str(owner or "").encode("utf-8")).hexdigest()


def _owner_index_lock(owner: str) -> threading.RLock:
    return _owner_index_lock_for_key(_index_owner_key(owner))


def _owner_index_lock_for_key(owner_key: str) -> threading.RLock:
    with _INDEX_STATE_LOCK:
        return _INDEX_OWNER_LOCKS.setdefault(owner_key, threading.RLock())


def _load_index_state() -> Dict[str, Any]:
    path = Path(KNOWLEDGE_INDEX_STATE_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("owners"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "owners": {}}


def _save_index_state(state: Dict[str, Any]) -> None:
    path = Path(KNOWLEDGE_INDEX_STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _delete_rag_source(rag, source: str, owner: str) -> int:
    deleter = getattr(rag, "delete_by_source", None)
    if not callable(deleter):
        vector_rag = getattr(rag, "vector_rag", None)
        deleter = getattr(vector_rag, "delete_by_source", None)
    if not callable(deleter):
        return 0
    try:
        return int(deleter(source, owner=owner or None) or 0)
    except TypeError:
        # Backward compatibility for small test/custom RAG shims. Production
        # VectorRAG accepts owner and never crosses account boundaries.
        return int(deleter(source) or 0)


def _entry_belongs_to_selected_root(entry: Dict[str, Any], roots: List[Path]) -> bool:
    return _path_is_under_any(str(entry.get("source") or ""), roots)


def _entry_source_is_configured(entry: Dict[str, Any]) -> bool:
    kind = entry.get("source_kind")
    if kind == "obsidian":
        root = configured_vault_root()
        return root is not None and _path_is_under_any(str(entry.get("source") or ""), [root])
    if kind == "local":
        root_id = str(entry.get("root_id") or "")
        for root in configured_local_roots():
            if root["id"] == root_id:
                return _path_is_under_any(str(entry.get("source") or ""), [Path(root["path"])])
        return False
    return False


def index_knowledge_folders(rag, folders: Optional[Iterable[str]], owner: str = "") -> Dict[str, Any]:
    """Incrementally synchronize selected private sources into the vector index.

    The manifest prevents unchanged files from being re-embedded and gives
    modified/deleted files an explicit lifecycle. It is local app data only and
    is owner-hashed at the top level; report exports never include it.
    """
    owner_key = _index_owner_key(owner)

    with _owner_index_lock(owner):
        # Resolve configuration only after entering the owner barrier. A root
        # removed while this call was waiting must not be re-indexed from a
        # stale pre-lock source snapshot.
        sources = _resolve_selected_sources(folders)
        vault_root = configured_vault_root()
        roots = [source.path for source in sources]
        with _INDEX_STATE_LOCK:
            state = _load_index_state()
            owner_entries = dict((state.get("owners") or {}).get(owner_key) or {})

        current_files: Dict[str, KnowledgeSourceRoot] = {}
        for source_root in sources:
            for path in _iter_supported_files(source_root.path):
                current_files[str(path)] = source_root

        indexed = 0
        failed = 0
        unchanged = 0
        replaced = 0
        removed = 0

        # Remove deleted files in the selected scope and entries whose configured
        # root has itself been removed. Deselecting a still-configured root does
        # not erase it, but it is excluded at query time by metadata filtering.
        for entry_key, entry in list(owner_entries.items()):
            source = str(entry.get("source") or "")
            selected_and_missing = (
                _entry_belongs_to_selected_root(entry, roots)
                and source not in current_files
            )
            root_removed = not _entry_source_is_configured(entry)
            if selected_and_missing or root_removed:
                _delete_rag_source(rag, source, owner)
                owner_entries.pop(entry_key, None)
                removed += 1

        for source, source_root in sorted(current_files.items()):
            path = Path(source)
            entry_key = hashlib.sha256(source.encode("utf-8")).hexdigest()
            stored = owner_entries.get(entry_key) or {}
            try:
                stat = path.stat()
            except OSError:
                failed += 1
                continue

            signature_matches = (
                stored.get("mtime_ns") == stat.st_mtime_ns
                and stored.get("size") == stat.st_size
                and stored.get("knowledge_source_token") == source_root.token
                and stored.get("source_kind") == source_root.source_kind
            )
            if signature_matches:
                unchanged += 1
                continue

            try:
                content = _read_file_text(path)
            except Exception:
                failed += 1
                continue
            if not content.strip():
                if stored:
                    _delete_rag_source(rag, source, owner)
                    owner_entries.pop(entry_key, None)
                    removed += 1
                continue

            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            metadata_changed = (
                stored.get("knowledge_source_token") != source_root.token
                or stored.get("source_kind") != source_root.source_kind
            )
            if stored and stored.get("content_hash") == content_hash and not metadata_changed:
                stored.update({"mtime_ns": stat.st_mtime_ns, "size": stat.st_size})
                owner_entries[entry_key] = stored
                unchanged += 1
                continue

            # First synchronization also removes possible legacy text-only IDs,
            # so the new source-aware IDs do not coexist with stale chunks.
            _delete_rag_source(rag, source, owner)
            if stored:
                replaced += 1

            rel = _relative(source_root.display_root, path)
            root_id = ""
            if source_root.source_kind == "local":
                root_id, _ = _split_local_folder_token(source_root.token)
            meta = {
                "source": source,
                "filename": path.name,
                "directory": str(path.parent),
                "vault_relative_path": rel,
                "knowledge_relative_path": rel,
                "knowledge_source_label": source_root.label,
                "knowledge_source_token": source_root.token,
                "type": path.suffix.lower(),
                "source_kind": source_root.source_kind,
            }
            if vault_root is not None and source_root.source_kind == "obsidian":
                meta["vault_relative_path"] = rel
            if owner:
                meta["owner"] = owner
            try:
                chunks = rag._split_into_chunks(content)
            except Exception:
                chunks = [content]

            file_failed = False
            for i, chunk in enumerate(chunks):
                document_key = f"knowledge:{source}:{content_hash}:{i}"
                try:
                    ok = rag.add_document(
                        chunk,
                        {
                            **meta,
                            "chunk_id": i,
                            "document_key": document_key,
                        },
                    )
                except Exception:
                    ok = False
                indexed += 1 if ok else 0
                failed += 0 if ok else 1
                file_failed = file_failed or not ok

            if file_failed:
                _delete_rag_source(rag, source, owner)
                owner_entries.pop(entry_key, None)
                continue
            owner_entries[entry_key] = {
                "source": source,
                "owner": owner,
                "source_kind": source_root.source_kind,
                "root_id": root_id,
                "knowledge_source_token": source_root.token,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "content_hash": content_hash,
                "chunk_count": len(chunks),
            }

        with _INDEX_STATE_LOCK:
            latest = _load_index_state()
            latest.setdefault("owners", {})[owner_key] = owner_entries
            _save_index_state(latest)

    return {
        "success": failed == 0,
        "folders": [source.token for source in sources],
        "files_seen": len(current_files),
        "indexed_count": indexed,
        "unchanged_count": unchanged,
        "replaced_count": replaced,
        "removed_count": removed,
        "failed_count": failed,
    }


def prune_removed_knowledge_roots(rag) -> int:
    """Delete indexed chunks whose configured root no longer exists."""
    removed = 0
    with _INDEX_STATE_LOCK:
        owner_keys = list((_load_index_state().get("owners") or {}).keys())

    for owner_key in owner_keys:
        with _owner_index_lock_for_key(owner_key):
            with _INDEX_STATE_LOCK:
                state = _load_index_state()
                owner_entries = dict(
                    (state.setdefault("owners", {}).get(owner_key) or {})
                )
            next_entries = dict(owner_entries or {})
            for entry_key, entry in list(next_entries.items()):
                if _entry_source_is_configured(entry):
                    continue
                _delete_rag_source(
                    rag,
                    str(entry.get("source") or ""),
                    str(entry.get("owner") or ""),
                )
                next_entries.pop(entry_key, None)
                removed += 1
            with _INDEX_STATE_LOCK:
                latest = _load_index_state()
                latest.setdefault("owners", {})[owner_key] = next_entries
                _save_index_state(latest)
    return removed


def _path_is_under_any(path: str, roots: List[Path]) -> bool:
    try:
        resolved = Path(path).resolve()
    except Exception:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _clean_image_ref(ref: str) -> str:
    value = unquote(str(ref or "").strip().strip("<>").strip())
    return value.split("|", 1)[0].split("#", 1)[0].strip()


def _is_local_image_ref(ref: str) -> bool:
    ref = _clean_image_ref(ref)
    if not ref:
        return False
    parsed = urlparse(ref)
    if parsed.scheme and parsed.scheme.lower() != "file":
        return False
    return Path(parsed.path or ref).suffix.lower() in IMAGE_EXTENSIONS


def _iter_markdown_image_refs(text: str) -> Iterable[str]:
    if not isinstance(text, str) or ("!" not in text and "<img" not in text.lower()):
        return []
    refs: List[str] = []
    refs.extend(m.group(1) for m in _OBSIDIAN_IMAGE_RE.finditer(text))
    refs.extend(m.group(1) for m in _MARKDOWN_IMAGE_RE.finditer(text))
    refs.extend(m.group(1) for m in _HTML_IMAGE_RE.finditer(text))
    return refs


def collect_note_images(
    note_path: Path,
    *,
    roots: Optional[Iterable[Path]] = None,
    markdown_text: Optional[str] = None,
    max_images: int = MAX_NOTE_IMAGES,
) -> List[Dict[str, str]]:
    """Resolve local Obsidian image embeds into vault-image URLs."""
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

    resolved_roots = []
    for root in roots or []:
        try:
            candidate = Path(root).resolve()
            candidate.relative_to(vault_root.resolve())
            resolved_roots.append(candidate)
        except Exception:
            continue

    images: List[Dict[str, str]] = []
    seen = set()
    excluded = excluded_dirs()
    for ref in _iter_markdown_image_refs(markdown_text):
        ref = _clean_image_ref(ref)
        if not _is_local_image_ref(ref):
            continue
        parsed = urlparse(ref)
        ref_path = Path(parsed.path or ref)
        candidates = [ref_path] if ref_path.is_absolute() else [
            note_path.parent / ref_path,
            *(root / ref_path for root in resolved_roots),
            vault_root / ref_path,
            note_path.parent / "assets" / ref_path.name,
            note_path.parent / "attachments" / ref_path.name,
        ]
        valid = None
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(vault_root.resolve())
            except Exception:
                continue
            if resolved.exists() and resolved.is_file() and resolved.suffix.lower() in IMAGE_EXTENSIONS and not _path_has_excluded_dir(resolved, vault_root, excluded):
                valid = resolved
                break
        if valid is None:
            continue
        rel = _relative(vault_root, valid)
        if rel in seen:
            continue
        seen.add(rel)
        images.append({"url": f"vault-image://{quote(rel, safe='/')}", "title": valid.stem.replace("_", " ").replace("-", " "), "source_path": rel})
        if len(images) >= max_images:
            break
    return images


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
    sources = _resolve_selected_sources(folders)
    roots = [source.path for source in sources]
    source_by_root = {str(source.path.resolve()): source for source in sources}
    vault_root = configured_vault_root()
    if auto_index is None:
        auto_index = bool(get_setting("research_knowledge_auto_index", True))
    if auto_index:
        index_knowledge_folders(rag, folders, owner=owner)

    limit = max(1, min(int(limit or 12), 50))
    selected_tokens = [source.token for source in sources]
    metadata_filter = {
        "knowledge_source_token": {"$in": selected_tokens}
    }
    try:
        raw = rag.search(
            query,
            k=max(limit * 8, 40),
            owner=owner or None,
            where=metadata_filter,
        )
    except TypeError:
        # Compatibility for third-party/test RAG shims. The production manager
        # filters inside Chroma before ranking, which preserves selected-root
        # recall even when unrelated roots dominate the global top-k.
        raw = rag.search(query, k=max(limit * 8, 40), owner=owner or None)
    items: List[Dict[str, Any]] = []
    seen = set()
    for result in raw:
        meta = result.get("metadata") or {}
        source = meta.get("source") or ""
        if not source or not _path_is_under_any(source, roots):
            continue
        try:
            if not Path(source).is_file():
                continue
        except OSError:
            continue
        matched_root: Optional[KnowledgeSourceRoot] = None
        try:
            resolved_source = Path(source).resolve()
            for root in roots:
                try:
                    resolved_source.relative_to(root.resolve())
                    matched_root = source_by_root.get(str(root.resolve()))
                    break
                except ValueError:
                    continue
        except Exception:
            pass
        display_root = matched_root.display_root if matched_root else (vault_root or Path(source).parent)
        source_kind = meta.get("source_kind") or (matched_root.source_kind if matched_root else "obsidian")
        source_label = meta.get("knowledge_source_label") or (matched_root.label if matched_root else "Obsidian")
        rel = meta.get("knowledge_relative_path") or meta.get("vault_relative_path") or _relative(display_root, Path(source))
        chunk_id = meta.get("chunk_id", "")
        key = f"{rel}#{chunk_id}"
        if key in seen:
            continue
        seen.add(key)
        document = str(result.get("document") or "")
        title = meta.get("filename") or Path(source).name or rel
        prefix = "Obsidian" if source_kind == "obsidian" else source_label
        url = f"vault://{rel}#chunk-{chunk_id}" if source_kind == "obsidian" else f"local-knowledge://{quote(source_label, safe='')}/{quote(rel, safe='/')}#chunk-{chunk_id}"
        item = {
            "url": url,
            "title": f"{prefix}: {title}",
            "source_path": rel,
            "source_kind": source_kind,
            "source_type": source_kind,
            "source_label": source_label,
            "summary": document[:1200],
            "evidence": document[:3000],
            "similarity": result.get("similarity"),
        }
        images = collect_note_images(Path(source), roots=roots) if source_kind == "obsidian" else []
        if images:
            item["images"] = images
        items.append(item)
        if len(items) >= limit:
            break
    return items
