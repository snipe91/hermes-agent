"""Hermes 2.0 — WorldState: an immutable observation of the world.

This module is deliberately provider-agnostic. It does not execute actions,
call an LLM, or decide what the agent should do. It is pure data plus two
hashes used for lightweight state comparison.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


def _stable_hash(value: Any) -> str:
    """Create a deterministic hash for lightweight state comparison."""
    text = repr(value).encode("utf-8", errors="replace")
    return hashlib.sha256(text).hexdigest()


@dataclass(frozen=True)
class WorldState:
    """Immutable observation of the browser/world at a point in time.

    Attributes:
        task_id: Session/task this observation belongs to.
        url: Current page URL, when known.
        title: Current page title, when known.
        accessibility_snapshot: Raw accessibility-tree text (the main evidence).
        element_count: Number of interactive refs the browser reported.
        dialogs: Pending native/JS dialogs observed.
        overlays: Modals, cookie banners, and other obstructing layers.
        errors: Page or console errors observed.
        screenshot_path: Path to a persisted screenshot, if one was taken.
        loading: Whether the page appeared to still be loading.
        timestamp: Unix time the observation was taken.
        metadata: Free-form extras (observation errors, source, raw keys...).
    """

    task_id: str

    url: str | None = None
    title: str | None = None

    accessibility_snapshot: str = ""
    element_count: int = 0

    dialogs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    overlays: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    errors: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    screenshot_path: str | None = None

    loading: bool = False

    timestamp: float = field(default_factory=time.time)

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def accessibility_hash(self) -> str:
        """Hash of the accessibility snapshot alone (pure DOM structure)."""
        return _stable_hash(self.accessibility_snapshot)

    @property
    def structural_hash(self) -> str:
        """Hash of every structural signal, ignoring the timestamp."""
        return _stable_hash({
            "url": self.url,
            "title": self.title,
            "accessibility": self.accessibility_snapshot,
            "element_count": self.element_count,
            "dialogs": self.dialogs,
            "overlays": self.overlays,
            "errors": self.errors,
            "loading": self.loading,
        })

    @property
    def has_obstacles(self) -> bool:
        """True when something is blocking or degrading the interaction."""
        return bool(self.dialogs or self.overlays or self.errors)

    @property
    def observed_ok(self) -> bool:
        """False when the observation itself failed (not a page problem)."""
        return "observation_error" not in self.metadata

    def summary(self) -> dict[str, Any]:
        """Small representation safe to pass around the agent loop.

        The full accessibility snapshot is intentionally NOT included: it is
        large, and callers that need it already hold the WorldState object.
        """
        return {
            "task_id": self.task_id,
            "url": self.url,
            "title": self.title,
            "element_count": self.element_count,
            "has_dialogs": bool(self.dialogs),
            "has_overlays": bool(self.overlays),
            "has_errors": bool(self.errors),
            "has_obstacles": self.has_obstacles,
            "observed_ok": self.observed_ok,
            "loading": self.loading,
            "has_screenshot": bool(self.screenshot_path),
            "structural_hash": self.structural_hash,
            "timestamp": self.timestamp,
        }
