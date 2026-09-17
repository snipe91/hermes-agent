"""Hermes 2.0 — WorldState cache.

Motivation, from the H2.0-006 real run:

    snapshot_before_mean = 282.8 ms
    snapshot_after_mean  = 327.6 ms
    -> 610 ms per click, 62 % of H2.0's total overhead

Yet in a normal browser trajectory a snapshot has *often just been taken* —
``browser_snapshot`` is one of the most-called browser tools. Re-taking an
identical snapshot to answer "what did the world look like a moment ago?" is
the single cheapest win available.

Freshness policy (justified by measurement, not invented):

    A snapshot costs ~280-330 ms. Any cache window shorter than that saves
    nothing, because the caller would have paid for a fresh snapshot anyway.
    A window of 400 ms is therefore the smallest value that can pay off, and
    it is deliberately conservative: it is roughly one snapshot's own cost.

    Beyond MAX_AGE_MS the entry is discarded outright rather than served as
    "stale but usable" — a stale state used as a BEFORE is worse than no
    observation at all, because it would produce a fictitious diff.

Invalidation is explicit and mandatory after a mutating action. A cache that
survives a click would make every click look like it changed nothing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

#: Below this age, a cached state is byte-identical to what a fresh snapshot
#: would return for an unchanged page, and cheaper than taking one.
DEFAULT_FRESHNESS_MS = 400.0

#: Above this age the entry is dropped, never served.
DEFAULT_MAX_AGE_MS = 60_000.0


@dataclass
class CacheEntry:
    """One cached observation."""

    state: Any
    timestamp: float
    url: str = ""
    title: str = ""
    state_hash: str = ""
    source: str = "snapshot"
    hits: int = 0

    def age_ms(self, now: float | None = None) -> float:
        return ((now if now is not None else time.time()) - self.timestamp) * 1000.0


@dataclass
class CacheStats:
    """Counters proving the cache actually saves work."""

    hits: int = 0
    misses: int = 0
    stores: int = 0
    invalidations: int = 0
    expired: int = 0
    errors: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "invalidations": self.invalidations,
            "expired": self.expired,
            "errors": self.errors,
            "hit_rate": self.hit_rate,
        }


class WorldStateCache:
    """Per-task cache of recent WorldStates.

    Best-effort by design: any failure degrades to "no cache", which costs a
    snapshot but never breaks a caller.
    """

    def __init__(
        self,
        freshness_ms: float = DEFAULT_FRESHNESS_MS,
        max_age_ms: float = DEFAULT_MAX_AGE_MS,
    ) -> None:
        self.freshness_ms = freshness_ms
        self.max_age_ms = max_age_ms
        self.stats = CacheStats()
        self._entries: dict[str, CacheEntry] = {}
        self._clock = time.time

    # ── reads ─────────────────────────────────────────────────────────────
    def get(self, task_id: str, *, now: float | None = None) -> Any | None:
        """Return a cached state if it is fresh enough to stand in for a new one.

        Returns ``None`` when there is nothing usable — the caller then takes a
        real snapshot. Never raises.
        """
        try:
            entry = self._entries.get(task_id)
            if entry is None:
                self.stats.misses += 1
                return None

            age = entry.age_ms(now if now is not None else self._clock())
            if age > self.max_age_ms:
                del self._entries[task_id]
                self.stats.expired += 1
                self.stats.misses += 1
                return None

            if age > self.freshness_ms:
                # Fresh enough to keep, too old to serve.
                self.stats.misses += 1
                return None

            entry.hits += 1
            self.stats.hits += 1
            return entry.state
        except Exception:
            self.stats.errors += 1
            self.stats.misses += 1
            return None

    # ── writes ────────────────────────────────────────────────────────────
    def put(self, task_id: str, state: Any, *, source: str = "snapshot") -> bool:
        """Store a state. Returns False on failure, never raises."""
        try:
            self._entries[task_id] = CacheEntry(
                state=state,
                timestamp=self._clock(),
                url=getattr(state, "url", "") or "",
                title=getattr(state, "title", "") or "",
                state_hash=getattr(state, "structural_hash", "") or "",
                source=source,
            )
            self.stats.stores += 1
            return True
        except Exception:
            self.stats.errors += 1
            return False

    def invalidate(self, task_id: str) -> None:
        """Drop a task's entry. MUST be called after a mutating action."""
        try:
            if task_id in self._entries:
                del self._entries[task_id]
                self.stats.invalidations += 1
        except Exception:
            self.stats.errors += 1

    def invalidate_all(self) -> None:
        try:
            self._entries.clear()
            self.stats.invalidations += 1
        except Exception:
            self.stats.errors += 1

    # ── introspection ─────────────────────────────────────────────────────
    def peek(self, task_id: str) -> CacheEntry | None:
        """Entry without touching hit/miss counters (for diagnostics and tests)."""
        return self._entries.get(task_id)

    def age_of(self, task_id: str) -> float | None:
        entry = self._entries.get(task_id)
        return entry.age_ms(self._clock()) if entry else None

    def __len__(self) -> int:
        return len(self._entries)


#: Process-wide cache. One per process is right: task entries are keyed by
#: task_id, and a fresh process has no observations to reuse anyway.
_GLOBAL_CACHE = WorldStateCache()


def get_cache() -> WorldStateCache:
    """Return the process-wide cache."""
    return _GLOBAL_CACHE


def reset_cache() -> None:
    """Replace the global cache (used by tests)."""
    global _GLOBAL_CACHE
    _GLOBAL_CACHE = WorldStateCache()
