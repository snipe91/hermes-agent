"""Hermes 2.0 — Decision Ledger.

Append-only record of every verified action decision, so H2.0 can be *measured*
before it is ever given the power to alter a trajectory.

Storage choice: JSONL, one file per session, following the existing
``agent/moa_trace.py`` pattern. Rationale (after inspecting the repo):
    - SQLite is already used by ``insights``/``verification_evidence`` for
      structured, queryable stores. H2.0 needs an append-only event log, not a
      queryable schema, so a database would be over-engineering.
    - JSONL survives concurrent writers better than a locked SQLite file, and a
      failed write must never break a tool call.
    - It is readable and greppable by a human debugging a session.

Everything here is best-effort: a ledger failure must never propagate.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VerificationMode(str, Enum):
    """How much of H2.0 is active."""

    OFF = "off"
    OBSERVE = "observe"
    ENFORCE = "enforce"

    @classmethod
    def parse(cls, raw: Any, default: "VerificationMode" = None) -> "VerificationMode":  # type: ignore[assignment]
        """Parse a config value, falling back safely to OFF.

        An unrecognised value must never enable the experimental layer.
        """
        fallback = default or cls.OFF
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, bool):
            return cls.OBSERVE if raw else cls.OFF
        if isinstance(raw, str):
            token = raw.strip().lower()
            for member in cls:
                if member.value == token:
                    return member
            # Tolerate the common truthy spellings for "observe only".
            if token in {"1", "true", "yes", "on", "log"}:
                return cls.OBSERVE
            if token in {"0", "false", "no", "off", "none", ""}:
                return cls.OFF
        return fallback


class EvidenceQuality(str, Enum):
    """Where a verdict's evidence comes from — NOT a probability.

    Deliberately categorical: we must never manufacture a confidence score the
    underlying signal does not support.

    DETERMINISTIC     decided from an exact structural comparison
    STRUCTURAL        decided from accessibility-tree / element signals
    VISUAL_HEURISTIC  decided from a vision model's prose, keyword-parsed
    UNAVAILABLE       no usable evidence; verdict is UNKNOWN
    """

    DETERMINISTIC = "deterministic"
    STRUCTURAL = "structural"
    VISUAL_HEURISTIC = "visual_heuristic"
    UNAVAILABLE = "unavailable"


@dataclass
class LedgerEntry:
    """One structured decision record.

    Fields mirror the measurement plan: enough to answer "what fraction of real
    browser clicks are observable?", "how often does vision fire?", and "how
    much latency does H2.0 add?".

    ``ground_truth`` is intentionally nullable and NEVER inferred. H2.0's own
    VERIFIED is not truth, and nothing here may pretend otherwise.
    """

    timestamp: float
    task_id: str
    action_type: str
    target: str = ""

    #: H3-④E (a) — clé de corrélation EXPLICITE (identifiant de run du Brain), DISTINCTE de
    #: ``task_id``. Recopiée TELLE QUELLE depuis les arguments de l'appel observé
    #: (``args["delegation_id"]``) ; jamais déduite, JAMAIS de repli sur ``task_id``.
    #: Absente ⇒ ``""`` ⇒ l'observation n'est rattachée à aucun run (jamais arbitrairement).
    correlation_id: str = ""

    risk_level: str = "medium"

    before_state_hash: str | None = None
    after_state_hash: str | None = None
    state_changed: bool = False
    expected_state_present: bool = False

    initial_verdict: str = "unknown"
    vision_escalated: bool = False
    final_verdict: str = "unknown"

    #: Structured cause when the verdict is UNKNOWN. Annotates, never replaces.
    unknown_reason: str = "none"

    obstacles_detected: int = 0
    observation_quality: str = EvidenceQuality.UNAVAILABLE.value

    # ── Latency breakdown (never merged: H2.0 overhead must stay separable
    #    from the tool's own execution time) ────────────────────────────────
    action_latency_ms: float = 0.0  # the browser_click call itself
    snapshot_before_ms: float = 0.0  # H2.0 overhead — before-capture
    snapshot_after_ms: float = 0.0  # H2.0 overhead — after-capture
    verification_latency_ms: float = 0.0  # H2.0 overhead — verify + diff
    vision_latency_ms: float = 0.0  # H2.0 overhead — vision call
    total_observation_overhead_ms: float = 0.0  # sum of H2.0-only phases

    # Kept for backward compatibility with earlier ledger entries.
    latency_ms: float = 0.0

    error: str | None = None
    mode: str = VerificationMode.OBSERVE.value

    # Post-hoc evaluation hook. Always None at write time — never invented.
    ground_truth: str | None = None

    tool_reported_success: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe representation."""
        return {
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "action_type": self.action_type,
            "target": self.target,
            "correlation_id": self.correlation_id,
            "risk_level": self.risk_level,
            "before_state_hash": self.before_state_hash,
            "after_state_hash": self.after_state_hash,
            "state_changed": self.state_changed,
            "expected_state_present": self.expected_state_present,
            "initial_verdict": self.initial_verdict,
            "vision_escalated": self.vision_escalated,
            "final_verdict": self.final_verdict,
            "unknown_reason": self.unknown_reason,
            "obstacles_detected": self.obstacles_detected,
            "observation_quality": self.observation_quality,
            # Latency: action time and H2.0 overhead are reported separately.
            "action_latency_ms": round(self.action_latency_ms, 3),
            "snapshot_before_ms": round(self.snapshot_before_ms, 3),
            "snapshot_after_ms": round(self.snapshot_after_ms, 3),
            "verification_latency_ms": round(self.verification_latency_ms, 3),
            "vision_latency_ms": round(self.vision_latency_ms, 3),
            "total_observation_overhead_ms": round(
                self.total_observation_overhead_ms, 3
            ),
            "latency_ms": round(self.latency_ms, 3),
            "error": self.error,
            "mode": self.mode,
            "ground_truth": self.ground_truth,
            "tool_reported_success": self.tool_reported_success,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LedgerEntry":
        """Rebuild an entry from its JSON form (used by tests and analysis)."""
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in payload.items() if k in known})


def ledger_dir() -> Path:
    """Directory holding per-session ledgers, under the Hermes home."""
    try:
        from hermes_constants import get_hermes_dir

        return get_hermes_dir("cache/h2", "h2_ledger")
    except Exception:
        # Defensive fallback: never let a missing helper break observation.
        return Path(os.path.expanduser("~/.hermes/cache/h2"))


class DecisionLedger:
    """Append-only ledger of H2.0 decisions.

    Every public method swallows its own failures: H2.0 is an experimental
    layer, and a broken ledger must never break a tool call.
    """

    def __init__(
        self,
        task_id: str = "default",
        mode: VerificationMode = VerificationMode.OBSERVE,
        *,
        directory: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.task_id = task_id
        self.mode = mode
        self._dir = directory
        self.enabled = enabled
        self._in_memory: list[LedgerEntry] = []
        self._write_failures = 0

    # ── writing ───────────────────────────────────────────────────────────
    def record(self, entry: LedgerEntry) -> bool:
        """Append an entry. Returns False on failure — never raises."""
        if not self.enabled:
            return False

        self._in_memory.append(entry)

        try:
            path = self.path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            return True
        except Exception as exc:
            self._write_failures += 1
            logger.warning("H2 ledger write failed (%s): %s", type(exc).__name__, exc)
            return False

    # ── reading ───────────────────────────────────────────────────────────
    def path(self) -> Path:
        base = self._dir if self._dir is not None else ledger_dir()
        return base / f"{_sanitize(self.task_id)}.jsonl"

    def entries(self) -> list[LedgerEntry]:
        """Entries recorded in this process (not re-read from disk)."""
        return list(self._in_memory)

    def read_from_disk(self) -> list[LedgerEntry]:
        """Read back everything written for this task. Never raises."""
        out: list[LedgerEntry] = []
        try:
            path = self.path()
            if not path.exists():
                return out
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(LedgerEntry.from_dict(json.loads(line)))
                    except Exception:
                        continue  # skip a corrupt line, keep the rest
        except Exception as exc:
            logger.warning("H2 ledger read failed: %s", exc)
        return out

    @property
    def write_failures(self) -> int:
        return self._write_failures

    def clear(self) -> None:
        """Drop in-memory entries (used by tests)."""
        self._in_memory.clear()


def _sanitize(value: str) -> str:
    """Make a task id safe for a filename.

    Slashes are replaced, so the result can never escape its directory. Leading
    dots and ``..`` runs are also collapsed: a literal ``..`` in a filename is
    legal on POSIX but reads as path traversal to both humans and any downstream
    scanner, so it is not worth keeping.
    """
    keep = [c if (c.isalnum() or c in "-_.") else "_" for c in (value or "default")]
    name = "".join(keep)[:120]

    # Collapse any run of dots ("..", "...") down to a single separator.
    while ".." in name:
        name = name.replace("..", ".")

    name = name.strip(".")
    return name or "default"


def utc_now() -> float:
    """Timestamp helper (separated for testability)."""
    return time.time()
