import asyncio
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import Document, DocumentVersion
from core.database import Session as DbSession
from src.agent_tools.document_tools import upsert_web_knowledge_artifact
from src.agent_tools.document_tools import _append_web_artifact_update
from src.agent_tools.document_tools import _web_artifact_title


def test_web_artifact_update_heals_duplicate_frontmatter_fields():
    existing = """---
odysseus_artifact: web-knowledge
artifact_status: evolving
updated_at: 2026-08-04T13:30:13+09:00
updated_at: 2026-08-04T13:29:29+09:00
source_count: 2
source_count: 1
---

# Codex 비교

기존 내용
"""

    updated = _append_web_artifact_update(
        existing,
        answer="새 근거를 반영했습니다.",
        sources=[{
            "url": "https://example.test/new",
            "title": "New source",
        }],
        updated_at="2026-08-04T13:32:08+09:00",
        delta=True,
        repair=False,
    )

    frontmatter = updated.split("---", 2)[1]
    assert frontmatter.count("updated_at:") == 1
    assert "updated_at: 2026-08-04T13:32:08+09:00" in frontmatter
    assert frontmatter.count("source_count:") == 1


def test_web_artifact_source_count_deduplicates_github_readme_url_variants():
    existing = """---
odysseus_artifact: web-knowledge
artifact_status: evolving
updated_at: 2026-08-04T13:46:46+09:00
source_count: 2
---

- [OpenAI](https://openai.com/index/introducing-the-codex-app)
- [README](https://github.com/openai/codex/blob/main/README.md?plain=1)
"""

    updated = _append_web_artifact_update(
        existing,
        answer="최신 업데이트를 추가했습니다.",
        sources=[
            {"url": "https://github.com/openai/codex/blob/main/README.md", "title": "README"},
            {"url": "https://openai.com/index/introducing-upgrades-to-codex", "title": "Update"},
        ],
        updated_at="2026-08-04T13:50:00+09:00",
        delta=True,
        repair=False,
    )

    frontmatter = updated.split("---", 2)[1]
    assert "source_count: 3" in frontmatter
    assert "[README](https://github.com/openai/codex/blob/main/README.md)" not in updated


def test_web_artifact_source_count_ignores_raw_url_in_query_title():
    existing = """---
odysseus_artifact: web-knowledge
artifact_status: evolving
updated_at: 2026-08-04T14:15:01+09:00
source_count: 2
---

# WEB-E2E-20260804-1415: OpenAI 소개 https://openai.co…

- [OpenAI](https://openai.com/index/introducing-the-codex-app)
- [README](https://github.com/openai/codex/blob/main/README.md?plain=1)
"""

    updated = _append_web_artifact_update(
        existing,
        answer="동일한 두 근거를 재사용했습니다.",
        sources=[
            {
                "url": "https://openai.com/index/introducing-the-codex-app",
                "title": "OpenAI",
            },
            {
                "url": "https://github.com/openai/codex/blob/main/README.md?plain=1",
                "title": "README",
            },
        ],
        updated_at="2026-08-04T14:16:00+09:00",
        delta=False,
        repair=False,
    )

    frontmatter = updated.split("---", 2)[1]
    assert "source_count: 2" in frontmatter


def test_web_artifact_title_drops_e2e_marker_and_raw_urls():
    title = _web_artifact_title(
        "WEB-E2E-20260804-1415: OpenAI 공식 Codex 앱 소개 "
        "https://openai.com/index/introducing-the-codex-app 와 GitHub README "
        "https://github.com/openai/codex/blob/main/README.md?plain=1 비교"
    )

    assert title == "웹 지식 · OpenAI 공식 Codex 앱 소개 와 GitHub README 비교"
    assert "WEB-E2E" not in title
    assert "http" not in title


def test_web_knowledge_artifact_creates_then_versions_same_session_document(
    monkeypatch, tmp_path
):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'artifact.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", testing_session)

    session_id = "session-" + uuid.uuid4().hex
    db = testing_session()
    try:
        db.add(DbSession(
            id=session_id,
            owner="alice",
            name="Vault 운영 연구",
            model="gpt-test",
            endpoint_url="http://test",
        ))
        db.commit()
    finally:
        db.close()

    initial_sources = [
        {
            "url": "https://example.test/one",
            "title": "First source",
            "fetched": True,
            "usable": True,
            "evidence_status": "fetched",
        },
        {
            "url": "https://example.test/two",
            "title": "Second source",
            "fetched": True,
            "usable": True,
            "evidence_status": "fetched",
        },
    ]
    created = asyncio.run(upsert_web_knowledge_artifact(
        session_id=session_id,
        owner="alice",
        query="원본 Vault와 Wiki Vault를 분리 운영하는 방안을 조사해줘.",
        answer="# 운영 원칙\n\n원본과 검토된 지식을 분리합니다 [출처 1].",
        sources=initial_sources,
        continuation=False,
        delta=False,
        repair=False,
    ))

    assert created["action"] == "create"
    assert created["title"].startswith("웹 지식 · ")
    assert not created["title"].startswith("Code (")
    assert "odysseus_artifact: web-knowledge" in created["content"]
    assert "+09:00" in created["content"]

    updated = asyncio.run(upsert_web_knowledge_artifact(
        session_id=session_id,
        owner="alice",
        query="기존 근거에 최신 사례를 추가해줘.",
        answer="## 새 사례\n\n검토 큐를 추가합니다 [출처 2].",
        sources=initial_sources,
        continuation=True,
        delta=True,
        repair=False,
    ))

    assert updated["action"] == "update"
    assert updated["doc_id"] == created["doc_id"]
    assert updated["version"] == 2
    assert "후속 보완" in updated["content"]
    assert "검토 큐를 추가합니다" in updated["content"]

    db = testing_session()
    try:
        docs = db.query(Document).filter(Document.session_id == session_id).all()
        versions = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == created["doc_id"]
        ).order_by(DocumentVersion.version_number).all()
        assert len(docs) == 1
        assert [version.version_number for version in versions] == [1, 2]
        assert docs[0].owner == "alice"
    finally:
        db.close()


def test_web_knowledge_artifact_rejects_cross_owner_session(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'artifact-owner.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", testing_session)

    session_id = "session-" + uuid.uuid4().hex
    db = testing_session()
    try:
        db.add(DbSession(
            id=session_id,
            owner="bob",
            name="Bob",
            model="gpt-test",
            endpoint_url="http://test",
        ))
        db.commit()
    finally:
        db.close()

    result = asyncio.run(upsert_web_knowledge_artifact(
        session_id=session_id,
        owner="alice",
        query="다른 사용자의 세션",
        answer="충분히 긴 답변 " * 100,
        sources=[{
            "url": "https://example.test/owner",
            "title": "Owner source",
            "fetched": True,
            "usable": True,
            "evidence_status": "fetched",
        }],
        continuation=False,
        delta=False,
        repair=False,
    ))

    assert result["error"] == "Cannot write a knowledge artifact in another user's session"


def test_web_knowledge_artifact_inherits_session_owner_in_auth_disabled_mode(
    monkeypatch, tmp_path
):
    """An ownerless caller is the documented single-user/auth-disabled path."""

    engine = create_engine(
        f"sqlite:///{tmp_path / 'artifact-single-user.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", testing_session)

    session_id = "session-" + uuid.uuid4().hex
    db = testing_session()
    try:
        db.add(DbSession(
            id=session_id,
            owner="legacy-primary-user",
            name="Single user",
            model="gpt-test",
            endpoint_url="http://test",
        ))
        db.commit()
    finally:
        db.close()

    result = asyncio.run(upsert_web_knowledge_artifact(
        session_id=session_id,
        owner=None,
        query="인증 비활성 단일 사용자 웹 지식 정리",
        answer="충분히 긴 검증 답변 " * 100,
        sources=[{
            "url": "https://example.test/single-user",
            "title": "Single user source",
            "fetched": True,
            "usable": True,
            "evidence_status": "fetched",
        }],
        continuation=False,
        delta=False,
        repair=False,
    ))

    assert result["action"] == "create"
    db = testing_session()
    try:
        document = db.query(Document).filter(Document.id == result["doc_id"]).one()
        assert document.owner == "legacy-primary-user"
    finally:
        db.close()
