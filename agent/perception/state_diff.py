"""Hermes 2.0 — StateDiff: observable change between two WorldStates.

A diff answers one question: *did the world change in a way that matters?*
It never decides whether an action succeeded — it flags what verification
should look at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .world_state import WorldState


@dataclass(frozen=True)
class StateDiff:
    """Describes observable changes between two WorldState snapshots."""

    changed: bool

    url_changed: bool = False
    title_changed: bool = False
    accessibility_changed: bool = False
    element_count_changed: bool = False

    dialogs_opened: int = 0
    dialogs_closed: int = 0
    overlays_added: int = 0
    overlays_removed: int = 0
    errors_added: int = 0
    errors_removed: int = 0

    loading_started: bool = False
    loading_finished: bool = False

    details: list[str] = field(default_factory=list)

    @property
    def meaningful_change(self) -> bool:
        """Alias kept explicit for callers reading intent, not flags."""
        return self.changed

    @property
    def suspicious(self) -> bool:
        """True when an action produced little/no change or added an obstacle.

        This does NOT mean the action failed. It means verification should
        investigate further before the loop treats the step as done.
        """
        return (
            not self.changed
            or self.dialogs_opened > 0
            or self.overlays_added > 0
            or self.errors_added > 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Compact, JSON-safe representation for the agent loop / logs."""
        return {
            "changed": self.changed,
            "url_changed": self.url_changed,
            "title_changed": self.title_changed,
            "accessibility_changed": self.accessibility_changed,
            "element_count_changed": self.element_count_changed,
            "dialogs_opened": self.dialogs_opened,
            "dialogs_closed": self.dialogs_closed,
            "overlays_added": self.overlays_added,
            "overlays_removed": self.overlays_removed,
            "errors_added": self.errors_added,
            "errors_removed": self.errors_removed,
            "loading_started": self.loading_started,
            "loading_finished": self.loading_finished,
            "suspicious": self.suspicious,
            "details": list(self.details),
        }


def _count_delta(before: tuple, after: tuple) -> tuple[int, int]:
    """Return (added, removed) counts for two tuples.

    Deliberately length-based: obstacle tuples are small and we only need to
    know whether the interaction got worse, not which exact item appeared.
    """
    before_len = len(before)
    after_len = len(after)

    if after_len >= before_len:
        return after_len - before_len, 0

    return 0, before_len - after_len


def diff_world_states(before: WorldState, after: WorldState) -> StateDiff:
    """Compute the observable difference between two observations."""
    details: list[str] = []

    url_changed = before.url != after.url
    title_changed = before.title != after.title
    accessibility_changed = before.accessibility_hash != after.accessibility_hash
    element_count_changed = before.element_count != after.element_count

    dialogs_opened, dialogs_closed = _count_delta(before.dialogs, after.dialogs)
    overlays_added, overlays_removed = _count_delta(before.overlays, after.overlays)
    errors_added, errors_removed = _count_delta(before.errors, after.errors)

    loading_started = not before.loading and after.loading
    loading_finished = before.loading and not after.loading

    if url_changed:
        details.append("url_changed")
    if title_changed:
        details.append("title_changed")
    if accessibility_changed:
        details.append("accessibility_changed")
    if element_count_changed:
        details.append("element_count_changed")
    if dialogs_opened:
        details.append("dialog_opened")
    if dialogs_closed:
        details.append("dialog_closed")
    if overlays_added:
        details.append("overlay_added")
    if overlays_removed:
        details.append("overlay_removed")
    if errors_added:
        details.append("error_added")
    if errors_removed:
        details.append("error_removed")
    if loading_started:
        details.append("loading_started")
    if loading_finished:
        details.append("loading_finished")

    changed = bool(details)

    return StateDiff(
        changed=changed,
        url_changed=url_changed,
        title_changed=title_changed,
        accessibility_changed=accessibility_changed,
        element_count_changed=element_count_changed,
        dialogs_opened=dialogs_opened,
        dialogs_closed=dialogs_closed,
        overlays_added=overlays_added,
        overlays_removed=overlays_removed,
        errors_added=errors_added,
        errors_removed=errors_removed,
        loading_started=loading_started,
        loading_finished=loading_finished,
        details=details,
    )
