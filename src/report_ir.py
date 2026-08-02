"""Evidence-locked intermediate representation shared by report renderers.

The research/writer stage owns wording and citations. Presentation code only
consumes this immutable, serializable model and may not rewrite claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
import re
from typing import Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_CONFLICT_WORDS = ("상충", "충돌", "변경", "반대", "conflict", "contradict")
_LIMIT_WORDS = ("한계", "불확실", "답할 수 없", "근거 부족", "limitation", "uncertain")
_DECISION_WORDS = ("결정", "승인", "선택", "decision")


def _digest(prefix: str, payload: object, length: int = 16) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:length]}"


def _plain_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_label(source: Mapping[str, object], index: int) -> str:
    title = _plain_text(source.get("title"))
    if title:
        normalized_title = title.replace("\\", "/")
        lowered_title = normalized_title.lower()
        if (
            normalized_title.startswith(("/", "~/"))
            or re.match(r"^[a-zA-Z]:/", normalized_title)
            or lowered_title.startswith("file://")
        ):
            parsed_title = urlsplit(normalized_title)
            path_title = parsed_title.path if parsed_title.scheme == "file" else normalized_title
            return (os.path.basename(path_title.rstrip("/")) or f"Source {index}")[:160]
        return title[:160]
    path = str(source.get("source_path") or "")
    if path:
        return os.path.basename(path.rstrip("/"))[:160]
    target = str(source.get("url") or "")
    if target:
        parsed = urlsplit(target)
        return (os.path.basename(parsed.path.rstrip("/")) or parsed.netloc or f"Source {index}")[:160]
    return f"Source {index}"


def _safe_target(value: object) -> str:
    target = str(value or "").strip()
    lowered = target.lower()
    if not target or lowered.startswith(("javascript:", "data:", "file:")):
        return ""
    if re.search(r"(?:^|/)(?:users|home)/[^/]+/", lowered):
        return ""
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https", "vault"}:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _section_slug(title: str, index: int) -> str:
    lowered = _plain_text(title).lower()
    if any(word in lowered for word in ("집행 요약", "경영 요약", "executive summary")):
        base = "executive-summary"
    elif any(word in lowered for word in _CONFLICT_WORDS):
        base = "conflict-history"
    elif any(word in lowered for word in _LIMIT_WORDS):
        base = "limitations"
    elif any(word in lowered for word in ("결론", "conclusion")):
        base = "conclusion"
    else:
        ascii_slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
        base = ascii_slug[:64] or f"section-{index}"
    return f"section-{base}"


def _split_sections(markdown_text: str) -> tuple[str, list[tuple[int, str, str]]]:
    matches = list(_HEADING_RE.finditer(markdown_text))
    if not matches:
        return "", [(2, "보고서", markdown_text.strip())]
    preface = markdown_text[:matches[0].start()].strip()
    sections: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        sections.append((len(match.group(1)), _plain_text(match.group(2)), markdown_text[start:end].strip()))
    return preface, sections


def _split_blocks(body: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [paragraph for paragraph in paragraphs if paragraph]


def _block_type(text: str) -> str:
    lines = text.splitlines()
    lowered = _plain_text(text).lower()
    if lines and all(_TABLE_LINE_RE.match(line) for line in lines if line.strip()):
        return "table"
    if lines and all(_LIST_LINE_RE.match(line) for line in lines if line.strip()):
        return "list"
    if lines and all(line.lstrip().startswith(">") for line in lines if line.strip()):
        return "quote"
    if any(word in lowered for word in _LIMIT_WORDS):
        return "limitation"
    if any(word in lowered for word in _CONFLICT_WORDS):
        return "conflict"
    if any(word in lowered for word in _DECISION_WORDS):
        return "decision"
    return "prose"


@dataclass(frozen=True)
class ReportSource:
    source_id: str
    safe_label: str
    target: str = ""
    source_type: str = ""


@dataclass(frozen=True)
class ReportCitation:
    citation_id: str
    label: str
    target: str
    source_id: str = ""


@dataclass(frozen=True)
class ReportClaim:
    claim_id: str
    claim_type: str
    text: str
    citation_ids: tuple[str, ...]
    section_id: str
    block_id: str


@dataclass(frozen=True)
class ReportBlock:
    block_id: str
    block_type: str
    markdown: str
    claim_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReportSection:
    section_id: str
    level: int
    title: str
    blocks: tuple[ReportBlock, ...]


@dataclass(frozen=True)
class ReportIR:
    version: str
    title: str
    question: str
    category: str
    preface_markdown: str
    sections: tuple[ReportSection, ...]
    claims: tuple[ReportClaim, ...]
    citations: tuple[ReportCitation, ...]
    sources: tuple[ReportSource, ...]
    mapping_hash: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_markdown(self) -> str:
        parts = [self.preface_markdown.strip()] if self.preface_markdown.strip() else []
        for section in self.sections:
            parts.append(f"{'#' * section.level} {section.title}")
            parts.extend(block.markdown for block in section.blocks)
        return "\n\n".join(part for part in parts if part).strip()


def _claim_type(block_type: str, text: str) -> str:
    if block_type == "conflict":
        return "conflict"
    if block_type == "limitation":
        return "uncertainty"
    if block_type == "decision":
        return "decision"
    lowered = text.lower()
    if any(word in lowered for word in ("개인 의견", "내 생각", "의견", "opinion")):
        return "opinion"
    if any(word in lowered for word in ("추론", "가능성", "inference", "may ", "might ")):
        return "inference"
    return "fact"


def build_report_ir(
    *,
    question: str,
    report_markdown: str,
    sources: Iterable[Mapping[str, object]] | None = None,
    category: str | None = None,
) -> ReportIR:
    """Parse finalized report Markdown into one deterministic immutable IR."""
    markdown_text = str(report_markdown or "").replace("\r\n", "\n").strip()
    title_match = re.match(r"^\s*#\s+(.+?)\s*(?:\n|$)", markdown_text)
    title = _plain_text(title_match.group(1)) if title_match else _plain_text(question)
    if title_match:
        markdown_text = markdown_text[title_match.end():].lstrip()

    report_sources: list[ReportSource] = []
    source_by_target: dict[str, str] = {}
    for index, source in enumerate(sources or (), start=1):
        if not isinstance(source, Mapping):
            continue
        target = _safe_target(source.get("url"))
        label = _safe_label(source, index)
        source_id = _digest("source", {"label": label, "target": target, "index": index})
        report_source = ReportSource(
            source_id=source_id,
            safe_label=label,
            target=target,
            source_type=_plain_text(source.get("source_type"))[:80],
        )
        report_sources.append(report_source)
        if target:
            source_by_target[target] = source_id

    preface, raw_sections = _split_sections(markdown_text)
    section_ids_seen: dict[str, int] = {}
    report_sections: list[ReportSection] = []
    claims: list[ReportClaim] = []
    citations: list[ReportCitation] = []

    for section_index, (level, section_title, body) in enumerate(raw_sections, start=1):
        base_id = _section_slug(section_title, section_index)
        duplicate_number = section_ids_seen.get(base_id, 0) + 1
        section_ids_seen[base_id] = duplicate_number
        section_id = base_id if duplicate_number == 1 else f"{base_id}-{duplicate_number}"
        blocks: list[ReportBlock] = []
        for block_index, markdown_block in enumerate(_split_blocks(body), start=1):
            block_type = _block_type(markdown_block)
            if block_type == "prose" and section_id.startswith("section-limitations"):
                block_type = "limitation"
            elif block_type == "prose" and section_id.startswith("section-conflict-history"):
                block_type = "conflict"
            block_id = _digest(
                "block",
                {
                    "section": section_id,
                    "index": block_index,
                    "type": block_type,
                    "markdown": markdown_block,
                },
            )
            block_citation_ids: list[str] = []
            for citation_index, match in enumerate(_LINK_RE.finditer(markdown_block), start=1):
                label = _plain_text(match.group(1))[:200]
                target = _safe_target(match.group(2))
                citation_id = _digest(
                    "citation",
                    {
                        "block": block_id,
                        "index": citation_index,
                        "label": label,
                        "target": target,
                    },
                )
                citations.append(ReportCitation(
                    citation_id=citation_id,
                    label=label,
                    target=target,
                    source_id=source_by_target.get(target, ""),
                ))
                block_citation_ids.append(citation_id)
            claim_text = _plain_text(_LINK_RE.sub(r"\1", markdown_block))[:1200]
            claim_id = _digest(
                "claim",
                {
                    "section": section_id,
                    "block": block_id,
                    "type": _claim_type(block_type, claim_text),
                    "text": claim_text,
                    "citations": block_citation_ids,
                },
            )
            claims.append(ReportClaim(
                claim_id=claim_id,
                claim_type=_claim_type(block_type, claim_text),
                text=claim_text,
                citation_ids=tuple(block_citation_ids),
                section_id=section_id,
                block_id=block_id,
            ))
            blocks.append(ReportBlock(
                block_id=block_id,
                block_type=block_type,
                markdown=markdown_block,
                claim_ids=(claim_id,),
                citation_ids=tuple(block_citation_ids),
            ))
        report_sections.append(ReportSection(
            section_id=section_id,
            level=level,
            title=section_title,
            blocks=tuple(blocks),
        ))

    mapping_payload = {
        "version": "report-ir-v1",
        "sections": [
            {
                "section_id": section.section_id,
                "blocks": [
                    {
                        "block_id": block.block_id,
                        "claim_ids": block.claim_ids,
                        "citation_ids": block.citation_ids,
                    }
                    for block in section.blocks
                ],
            }
            for section in report_sections
        ],
        "claims": [asdict(claim) for claim in claims],
        "citations": [asdict(citation) for citation in citations],
        "sources": [asdict(source) for source in report_sources],
    }
    mapping_hash = hashlib.sha256(
        json.dumps(
            mapping_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ReportIR(
        version="report-ir-v1",
        title=title or "Odysseus Research",
        question=_plain_text(question)[:500],
        category=_plain_text(category)[:80],
        preface_markdown=preface,
        sections=tuple(report_sections),
        claims=tuple(claims),
        citations=tuple(citations),
        sources=tuple(report_sources),
        mapping_hash=mapping_hash,
    )
