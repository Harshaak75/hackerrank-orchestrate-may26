"""
response_cache.py
─────────────────
Near-duplicate response cache for the support pipeline.

Uses Jaccard similarity on keyword token sets to detect tickets that are
semantically close enough to re-use a previous LLM response.  This avoids
expensive (2–8 s) Gemini calls for rephrased versions of the same issue.

Key design decisions
────────────────────
• Similarity metric : Jaccard on alphanumeric tokens ≥ 3 chars, stop-words
                      removed.  No external ML dependency.
• Threshold         : 0.65 (configurable).  In practice: "cannot login" and
                      "i can't log in" score ~0.67 → cache hit.
• Company isolation : Cache hits only allowed within the same company.
                      Visa's billing response must NOT serve a HackerRank
                      billing question.
• Persistence       : Appended to support_tickets/response_cache.jsonl so the
                      cache survives across runs (useful in production).
• Cache tagging     : Hit responses get "[CACHE HIT: similarity=X.XX]"
                      prepended to justification for full auditability.
• Thread safety     : Append-only file writes are safe for single-process use.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from config import REPO_ROOT, STOP_WORDS

CACHE_PATH = REPO_ROOT / "support_tickets" / "response_cache.jsonl"
SIMILARITY_THRESHOLD = 0.65  # Jaccard coefficient threshold


# ──────────────────────────────────────────────────────────────────────────────
# Token helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> frozenset[str]:
    """Return a frozenset of meaningful lowercase tokens (≥ 3 chars, no stop-words)."""
    tokens = re.findall(r"[a-z0-9]{3,}", text.lower())
    return frozenset(t for t in tokens if t not in STOP_WORDS)


def _jaccard(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity coefficient between two token sets."""
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union)


# ──────────────────────────────────────────────────────────────────────────────
# Cache class
# ──────────────────────────────────────────────────────────────────────────────

class ResponseCache:
    """In-memory + persistent near-duplicate response cache.

    The cache is loaded from JSONL at startup and every new entry is
    appended immediately so no data is lost on crash.
    """

    def __init__(
        self,
        path: Path = CACHE_PATH,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self.path = path
        self.threshold = threshold
        self._entries: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load existing cache entries from disk."""
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        self._entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Skip corrupt lines

    def lookup(self, issue: str, subject: str, company: str) -> Optional[dict]:
        """Return a cached result for a near-duplicate ticket, or None.

        Only matches within the same company to prevent cross-domain leakage.
        The returned dict has a [CACHE HIT] tag in the justification.
        """
        query_tokens = _tokenize(f"{subject} {issue}")
        if not query_tokens:
            return None

        best_score = 0.0
        best_entry: Optional[dict] = None

        for entry in self._entries:
            # Strict company isolation
            if entry.get("company", "").lower() != company.lower():
                continue
            cached_tokens = frozenset(entry.get("tokens", []))
            score = _jaccard(query_tokens, cached_tokens)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= self.threshold and best_entry is not None:
            result = best_entry["result"].copy()
            result["justification"] = (
                f"[CACHE HIT: similarity={best_score:.2f}, "
                f"original='{best_entry.get('issue_preview', '')[:60]}'] "
                + result.get("justification", "")
            )
            return result

        return None

    def store(self, issue: str, subject: str, company: str, result: dict) -> None:
        """Persist a new result entry to the cache (in-memory + disk)."""
        tokens = list(_tokenize(f"{subject} {issue}"))
        # Don't cache entries that were themselves cache hits (avoid poisoning)
        if "[CACHE HIT" in result.get("justification", ""):
            return
        entry = {
            "company": company,
            "tokens": tokens,
            "issue_preview": f"{subject}: {issue}"[:100],
            # Exclude feedback and internal columns from cached results
            "result": {
                k: v for k, v in result.items()
                if k not in {"feedback_score", "feedback_comment", "issue", "subject", "company"}
            },
        }
        self._entries.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def stats(self) -> dict:
        """Return basic cache statistics."""
        companies: dict[str, int] = {}
        for e in self._entries:
            c = e.get("company", "unknown")
            companies[c] = companies.get(c, 0) + 1
        return {
            "total_entries": len(self._entries),
            "by_company": companies,
            "threshold": self.threshold,
            "path": str(self.path),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton (one cache per process)
# ──────────────────────────────────────────────────────────────────────────────

_cache: Optional[ResponseCache] = None


def get_cache() -> ResponseCache:
    global _cache
    if _cache is None:
        _cache = ResponseCache()
    return _cache


def cache_lookup(issue: str, subject: str, company: str) -> Optional[dict]:
    """Public interface: look up a near-duplicate response. Returns dict or None."""
    return get_cache().lookup(issue=issue, subject=subject, company=company)


def cache_store(issue: str, subject: str, company: str, result: dict) -> None:
    """Public interface: store a resolved ticket in the cache."""
    get_cache().store(issue=issue, subject=subject, company=company, result=result)


def cache_stats() -> dict:
    """Return cache statistics dict."""
    return get_cache().stats()
