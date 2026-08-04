"""Search analytics, metrics tracking, and exception hierarchy."""

import json
import hashlib
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from zoneinfo import ZoneInfo

from core.constants import DATA_DIR

from .cache import cache_metrics

logger = logging.getLogger(__name__)

# Dedicated error logger — write to the data logs directory (writable on both
# native runs and Docker, where DATA_DIR resolves to the bind-mounted volume).
_log_dir = Path(DATA_DIR) / "logs"
_error_log_path = _log_dir / "search_engine_error.log"
error_logger = logging.getLogger("search_engine_error")
error_logger.propagate = False


class _KstIsoFormatter(logging.Formatter):
    """Render operational log timestamps as KST ISO 8601 with +09:00."""

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(
            record.created, tz=ZoneInfo("Asia/Seoul")
        ).isoformat(timespec="seconds")


try:
    _log_dir.mkdir(parents=True, exist_ok=True)
    _error_handler = logging.FileHandler(_error_log_path, encoding="utf-8")
    _error_handler.setLevel(logging.WARNING)
    _error_handler.setFormatter(
        _KstIsoFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    error_logger.addHandler(_error_handler)
except Exception as _e:
    logging.getLogger(__name__).warning("search_engine_error log handler unavailable: %s", _e)

# Analytics file — also in the writable logs volume.
ANALYTICS_FILE = _log_dir / "search_analytics.json"


# ----------------------------------------------------------------------
# Custom exception hierarchy
# ----------------------------------------------------------------------
class SearchEngineError(Exception):
    """Base class for all search-engine related errors."""


class NetworkError(SearchEngineError):
    """Raised when a network request fails (e.g., timeout, DNS error)."""


class ParseError(SearchEngineError):
    """Raised when HTML or other content cannot be parsed."""


class RateLimitError(SearchEngineError):
    """Raised when the remote service returns a rate-limit (HTTP 429)."""


class ProviderError(SearchEngineError):
    """Raised when a provider responds with a non-rate-limit protocol error."""


# ----------------------------------------------------------------------
# Analytics helpers
# ----------------------------------------------------------------------
def _default_analytics() -> Dict[str, Any]:
    return {
        "total_queries": 0,
        "successful_queries": 0,
        "failed_queries": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "query_patterns": {},
    }


def query_fingerprint(query: str) -> str:
    """Return a stable, non-reversible identifier for an analytics query."""

    value = re.sub(r"\s+", " ", str(query or "")).strip()
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _scrub_query_patterns(patterns: Any) -> tuple[Dict[str, Any], bool]:
    """Migrate legacy plaintext query keys to fingerprints in-place."""

    if not isinstance(patterns, dict):
        return {}, bool(patterns)
    scrubbed: Dict[str, Any] = {}
    changed = False
    for raw_key, raw_entry in patterns.items():
        key = str(raw_key or "")
        safe_key = key if re.fullmatch(r"sha256:[0-9a-f]{16}", key) else query_fingerprint(key)
        changed = changed or safe_key != key
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        target = scrubbed.setdefault(safe_key, {"count": 0, "successes": 0})
        target["count"] += int(entry.get("count") or 0)
        target["successes"] += int(entry.get("successes") or 0)
    return scrubbed, changed


def _load_analytics() -> Dict[str, Any]:
    """Load analytics data from the JSON file, creating defaults if missing."""
    if not ANALYTICS_FILE.exists():
        default = _default_analytics()
        _save_analytics(default)
        return default
    try:
        with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge over defaults so a file written by an older schema (or a
        # partial write) still has every counter — _record_query indexes
        # these keys directly and would otherwise raise KeyError.
        merged = _default_analytics()
        if isinstance(data, dict):
            merged.update(data)
        merged["query_patterns"], scrubbed = _scrub_query_patterns(
            merged.get("query_patterns")
        )
        if scrubbed:
            _save_analytics(merged)
        return merged
    except Exception as e:
        logger.warning(f"Failed to load analytics file: {e}")
        return _default_analytics()


def _save_analytics(data: Dict[str, Any]) -> None:
    """Persist analytics data to the JSON file."""
    try:
        with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write analytics file: {e}")


def _record_query(query: str, success: bool, cache_hit: bool) -> None:
    """Update analytics for a single query execution."""
    analytics = _load_analytics()
    analytics["total_queries"] += 1
    if success:
        analytics["successful_queries"] += 1
    else:
        analytics["failed_queries"] += 1

    if cache_hit:
        analytics["cache_hits"] += 1
        cache_metrics["hits"] += 1
    else:
        analytics["cache_misses"] += 1
        cache_metrics["misses"] += 1

    patterns = analytics["query_patterns"]
    fingerprint = query_fingerprint(query)
    entry = patterns.get(fingerprint, {"count": 0, "successes": 0})
    entry["count"] += 1
    if success:
        entry["successes"] += 1
    patterns[fingerprint] = entry

    _save_analytics(analytics)


def get_search_stats() -> Dict[str, Any]:
    """Return aggregated search analytics."""
    analytics = _load_analytics()
    total = analytics.get("total_queries", 0) or 1
    success_rate = analytics.get("successful_queries", 0) / total
    cache_total = analytics.get("cache_hits", 0) + analytics.get("cache_misses", 0) or 1
    cache_hit_rate = analytics.get("cache_hits", 0) / cache_total

    pattern_counter = Counter({
        q: data["count"] for q, data in analytics.get("query_patterns", {}).items()
    })
    most_common = [q for q, _ in pattern_counter.most_common(5)]

    return {
        # Kept for API compatibility; values are opaque fingerprints, never
        # plaintext user queries.  New clients should use the explicit name.
        "most_common_queries": most_common,
        "most_common_query_fingerprints": most_common,
        "success_rate": success_rate,
        "cache_hit_rate": cache_hit_rate,
        "total_queries": analytics.get("total_queries", 0),
        "successful_queries": analytics.get("successful_queries", 0),
        "failed_queries": analytics.get("failed_queries", 0),
        "cache_hits": analytics.get("cache_hits", 0),
        "cache_misses": analytics.get("cache_misses", 0),
        "cache_evictions": cache_metrics["evictions"],
        "runtime_cache_hits": cache_metrics["hits"],
        "runtime_cache_misses": cache_metrics["misses"],
    }
