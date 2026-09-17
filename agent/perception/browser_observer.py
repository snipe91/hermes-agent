"""Hermes 2.0 — BrowserObserver: read-only adapter over Hermes' browser tools.

Contract:
    - NO browser action is performed here (no click, no navigation, no eval
      that mutates the page).
    - Any failure degrades to an incomplete WorldState instead of raising.
    - Existing browser behaviour is untouched: this module is additive.

Reality check on `browser_snapshot()` (verified against tools/browser_tool.py):
    It always returns `success`, `snapshot`, `element_count`. It returns
    `url`/`title` NEVER, and `dialogs`/`overlays`/`errors` only when a CDP
    supervisor is attached to the task. The observer therefore recovers
    url/title from the snapshot text when they are absent, and treats
    obstacle fields as best-effort.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .world_state import WorldState

logger = logging.getLogger(__name__)

# Snapshot headers Hermes/chromium emits, most specific first.
_URL_PATTERNS = (
    re.compile(
        r"^\s*[-*]?\s*(?:page\s+)?url\s*[:=]\s*(\S+)", re.IGNORECASE | re.MULTILINE
    ),
    re.compile(r"^\s*#{0,3}\s*(https?://\S+)", re.MULTILINE),
)
_TITLE_PATTERNS = (
    re.compile(
        r"^\s*[-*]?\s*(?:page\s+)?title\s*[:=]\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*#{0,3}\s*https?://\S+\s+[-–—]\s*(.+?)\s*$", re.MULTILINE),
)

_LOADING_HINTS = (
    "loading",
    "please wait",
    "chargement",
    "veuillez patienter",
    "spinner",
)

# Keys a CDP supervisor snapshot may inject into the browser_snapshot payload.
_OBSTACLE_KEYS = ("dialogs", "overlays", "errors")


class BrowserObserver:
    """Read-only adapter around Hermes' existing browser tools."""

    def __init__(self, task_id: str = "default") -> None:
        self.task_id = task_id

    # ── public API ────────────────────────────────────────────────────────
    def capture(
        self,
        *,
        user_task: str | None = None,
        full: bool = True,
    ) -> WorldState:
        """Observe the current page and return an immutable WorldState.

        ``full`` defaults to **True**. This changed in H2.0-007 after a real-run
        investigation: with ``full=False`` the snapshot only lists interactive
        elements, so text changes, added ``div``/``p`` nodes, ``role=alert``
        banners and style-only changes were all invisible. Measured on the local
        bench page, 9 of 10 real changes went undetected. ``full=True`` costs no
        more (271 ms vs 414 ms, within noise) and returned 14 % more content.

        A diff that cannot see a change reports "nothing happened", which is
        worse than reporting "unknown".

        Never raises: a failed observation is reported inside the returned
        state's metadata as ``observation_error``.
        """
        try:
            from tools.browser_tool import browser_snapshot

            raw = browser_snapshot(
                full=full,
                task_id=self.task_id,
                user_task=user_task,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("BrowserObserver: snapshot call failed")
            return self._failed(str(exc))

        payload = self._parse_result(raw)

        if not payload.get("success"):
            error = payload.get("error", "unknown browser snapshot error")
            logger.warning("BrowserObserver: snapshot returned failure: %s", error)
            return self._failed(error)

        return self._build_state(payload)

    # ── internals ─────────────────────────────────────────────────────────
    def _failed(self, error: str) -> WorldState:
        return WorldState(
            task_id=self.task_id,
            metadata={"observation_error": error},
        )

    @staticmethod
    def _parse_result(raw: Any) -> dict[str, Any]:
        """Normalise the tool's return value (documented as a JSON string)."""
        if isinstance(raw, dict):
            return raw

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"success": False, "error": "Invalid browser snapshot JSON"}
            if isinstance(parsed, dict):
                return parsed

        return {"success": False, "error": "Unexpected browser snapshot response type"}

    def _build_state(self, payload: dict[str, Any]) -> WorldState:
        snapshot = payload.get("snapshot", "")
        if not isinstance(snapshot, str):
            snapshot = str(snapshot)

        dialogs = self._extract_sequence(payload.get("dialogs"))
        overlays = self._extract_sequence(payload.get("overlays"))
        errors = self._extract_sequence(payload.get("errors"))

        url = payload.get("url") or _first_match(_URL_PATTERNS, snapshot)
        title = payload.get("title") or _first_match(_TITLE_PATTERNS, snapshot)

        # `loading` is not reported by browser_snapshot; only trust an explicit
        # boolean from a supervisor, otherwise fall back to a textual hint.
        if isinstance(payload.get("loading"), bool):
            loading = payload["loading"]
        else:
            loading = _looks_loading(snapshot)

        raw_keys = sorted(payload.keys())
        return WorldState(
            task_id=self.task_id,
            url=url,
            title=title,
            accessibility_snapshot=snapshot,
            element_count=int(payload.get("element_count") or 0),
            dialogs=dialogs,
            overlays=overlays,
            errors=errors,
            loading=loading,
            metadata={
                "source": "browser_snapshot",
                "raw_keys": raw_keys,
                "has_supervisor_state": any(key in payload for key in _OBSTACLE_KEYS),
                "url_from_snapshot": url is not None and "url" not in payload,
                "supervisor_error": payload.get("error")
                if payload.get("error")
                else None,
            },
        )

    @staticmethod
    def _extract_sequence(value: Any) -> tuple[dict[str, Any], ...]:
        """Coerce a supervisor-provided collection into a tuple of dicts."""
        if not value:
            return ()

        if isinstance(value, dict):
            return (value,)

        if isinstance(value, (list, tuple)):
            return tuple(
                item if isinstance(item, dict) else {"value": item} for item in value
            )

        return ({"value": value},)

    def capture_diff(
        self,
        *,
        user_task: str | None = None,
        full: bool = False,
    ) -> tuple[WorldState, str]:
        """Convenience: observe once and return (state, structural_hash).

        Kept intentionally trivial — callers that need a real diff should hold
        the previous WorldState themselves and use ``diff_world_states``.
        """
        state = self.capture(user_task=user_task, full=full)
        return state, state.structural_hash


def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    """Return the first capture group of the first pattern that matches."""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _looks_loading(snapshot: str) -> bool:
    """Very conservative loading hint — avoids false positives on long pages."""
    if not snapshot:
        return False
    head = snapshot[:2000].lower()
    return any(hint in head for hint in _LOADING_HINTS)
