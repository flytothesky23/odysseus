"""Default-merge on load for services/search/analytics.py.

src/search/analytics.py was fixed to merge a loaded analytics file over
defaults so _record_query never hits a missing counter, but the services
copy diverged and still returns json.load(f) verbatim. The services copy
is the live one: services/search/core.py calls _record_query on every
search, so an analytics file missing a key (older schema or partial
write) raises KeyError and breaks comprehensive_web_search.

Mirrors tests/test_search_analytics_defaults.py which covers the src copy.
"""
import json
import logging
import re

import services.search.analytics as analytics


def test_operational_log_timestamp_is_kst_iso_8601():
    record = logging.LogRecord("search", logging.WARNING, __file__, 1, "x", (), None)
    rendered = analytics._KstIsoFormatter("%(asctime)s").format(record)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", rendered)


def test_load_merges_defaults_for_partial_file(tmp_path, monkeypatch):
    f = tmp_path / "search_analytics.json"
    f.write_text(json.dumps({"total_queries": 5}), encoding="utf-8")
    monkeypatch.setattr(analytics, "ANALYTICS_FILE", f)

    data = analytics._load_analytics()

    assert data["total_queries"] == 5
    assert data["query_patterns"] == {}
    for key in ("successful_queries", "failed_queries", "cache_hits", "cache_misses"):
        assert data[key] == 0


def test_record_query_survives_partial_file(tmp_path, monkeypatch):
    f = tmp_path / "search_analytics.json"
    f.write_text(json.dumps({"total_queries": 1}), encoding="utf-8")
    monkeypatch.setattr(analytics, "ANALYTICS_FILE", f)

    # Before the fix this raised KeyError on the missing counters.
    analytics._record_query("hello world", success=True, cache_hit=False)

    data = analytics._load_analytics()
    assert data["total_queries"] == 2
    assert data["successful_queries"] == 1
    assert "hello world" not in data["query_patterns"]
    fingerprint = analytics.query_fingerprint("hello world")
    assert data["query_patterns"][fingerprint]["count"] == 1


def test_load_migrates_legacy_plaintext_query_patterns(tmp_path, monkeypatch):
    path = tmp_path / "search_analytics.json"
    path.write_text(
        '{"query_patterns":{"private full query":{"count":2,"successes":1}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(analytics, "ANALYTICS_FILE", path)

    loaded = analytics._load_analytics()

    assert "private full query" not in loaded["query_patterns"]
    assert loaded["query_patterns"][analytics.query_fingerprint("private full query")]["count"] == 2
    assert "private full query" not in path.read_text(encoding="utf-8")
