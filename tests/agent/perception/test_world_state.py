"""Tests for the Hermes 2.0 perception layer (WorldState + StateDiff + Observer)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent.perception import (
    BrowserObserver,
    WorldState,
    diff_world_states,
)


def _state(**kwargs: Any) -> WorldState:
    base: dict[str, Any] = {"task_id": "test"}
    base.update(kwargs)
    return WorldState(**base)


# ── WorldState ────────────────────────────────────────────────────────────
def test_world_state_hash_is_stable():
    state = _state(
        url="https://example.com",
        accessibility_snapshot="button Save",
        element_count=1,
    )

    assert state.accessibility_hash == state.accessibility_hash
    assert state.structural_hash == state.structural_hash


def test_structural_hash_ignores_timestamp():
    """Two observations of the same page at different times hash identically."""
    before = _state(url="https://example.com", accessibility_snapshot="button Save")
    after = _state(
        url="https://example.com",
        accessibility_snapshot="button Save",
        timestamp=before.timestamp + 120,
    )

    assert before.structural_hash == after.structural_hash


def test_world_state_is_frozen():
    state = _state(url="https://example.com")
    with pytest.raises(Exception):
        state.url = "https://other.com"  # type: ignore[misc]


def test_has_obstacles_detects_each_kind():
    assert _state().has_obstacles is False
    assert _state(dialogs=({"type": "alert"},)).has_obstacles is True
    assert _state(overlays=({"type": "modal"},)).has_obstacles is True
    assert _state(errors=({"message": "boom"},)).has_obstacles is True


def test_summary_omits_snapshot_but_exposes_signals():
    snapshot = "x" * 5000
    state = _state(
        url="https://example.com", accessibility_snapshot=snapshot, element_count=7
    )
    summary = state.summary()

    assert summary["element_count"] == 7
    assert summary["url"] == "https://example.com"
    assert summary["has_obstacles"] is False
    assert summary["structural_hash"] == state.structural_hash
    # The heavy payload must not leak into the loop-safe representation.
    assert snapshot not in json.dumps(summary)


def test_observed_ok_flag():
    assert _state().observed_ok is True
    assert _state(metadata={"observation_error": "boom"}).observed_ok is False


# ── StateDiff ─────────────────────────────────────────────────────────────
def test_identical_states_have_no_diff():
    before = _state(
        url="https://example.com", accessibility_snapshot="button Save", element_count=1
    )
    after = _state(
        url="https://example.com", accessibility_snapshot="button Save", element_count=1
    )

    diff = diff_world_states(before, after)

    assert diff.changed is False
    assert diff.meaningful_change is False
    # An action with zero observable effect is exactly what verification must look at.
    assert diff.suspicious is True


def test_dom_change_is_detected():
    before = _state(
        url="https://example.com",
        accessibility_snapshot="button Settings",
        element_count=1,
    )
    after = _state(
        url="https://example.com",
        accessibility_snapshot="button Settings\nmenu Preferences",
        element_count=2,
    )

    diff = diff_world_states(before, after)

    assert diff.changed is True
    assert diff.accessibility_changed is True
    assert diff.element_count_changed is True
    assert diff.suspicious is False


def test_url_change_is_detected():
    diff = diff_world_states(
        _state(url="https://example.com/a"),
        _state(url="https://example.com/b"),
    )

    assert diff.url_changed is True
    assert diff.changed is True
    assert "url_changed" in diff.details


def test_title_only_change_is_detected():
    diff = diff_world_states(
        _state(url="https://example.com", title="Loading…"),
        _state(url="https://example.com", title="Dashboard"),
    )

    assert diff.title_changed is True
    assert diff.changed is True
    assert diff.url_changed is False


def test_overlay_makes_state_suspicious():
    diff = diff_world_states(
        _state(),
        _state(overlays=({"type": "modal", "label": "Cookie consent"},)),
    )

    assert diff.overlays_added == 1
    assert diff.suspicious is True
    assert diff.changed is True


def test_error_removal_is_a_change_but_not_suspicious():
    before = _state(errors=({"message": "boom"},))
    after = _state()

    diff = diff_world_states(before, after)

    assert diff.errors_removed == 1
    assert diff.errors_added == 0
    assert diff.changed is True
    # Something improved; nothing to investigate.
    assert diff.suspicious is False


def test_loading_transitions():
    started = diff_world_states(_state(loading=False), _state(loading=True))
    assert started.loading_started is True
    assert started.loading_finished is False

    finished = diff_world_states(_state(loading=True), _state(loading=False))
    assert finished.loading_finished is True
    assert finished.loading_started is False


def test_diff_to_dict_is_json_safe():
    diff = diff_world_states(_state(url="https://a.test"), _state(url="https://b.test"))
    payload = diff.to_dict()

    assert payload["changed"] is True
    assert payload["url_changed"] is True
    json.dumps(payload)  # must not raise


# ── BrowserObserver ───────────────────────────────────────────────────────
def test_observer_parses_snapshot_payload():
    observer = BrowserObserver(task_id="t1")
    state = observer._build_state({
        "success": True,
        "snapshot": "Page URL: https://example.com/pricing\nPage Title: Pricing\nbutton Buy",
        "element_count": 1,
    })

    assert state.url == "https://example.com/pricing"
    assert state.title == "Pricing"
    assert state.element_count == 1
    assert state.metadata["has_supervisor_state"] is False
    assert state.observed_ok is True


def test_observer_parses_markdown_style_snapshot():
    observer = BrowserObserver(task_id="t1")
    state = observer._build_state({
        "success": True,
        "snapshot": "# https://example.com/blog - Le blog\nheading Bonjour",
        "element_count": 2,
    })

    assert state.url == "https://example.com/blog"
    assert state.title == "Le blog"


def test_observer_injects_supervisor_obstacles():
    observer = BrowserObserver(task_id="t1")
    state = observer._build_state({
        "success": True,
        "snapshot": "button OK",
        "element_count": 1,
        "dialogs": [{"type": "confirm", "message": "Supprimer ?"}],
        "overlays": [{"type": "modal", "label": "Tutoriel"}],
    })

    assert len(state.dialogs) == 1
    assert len(state.overlays) == 1
    assert state.has_obstacles is True
    assert state.metadata["has_supervisor_state"] is True


def test_observer_handles_invalid_json():
    observer = BrowserObserver(task_id="t1")
    payload = observer._parse_result("not-json{")

    assert payload["success"] is False
    assert "JSON" in payload["error"]


def test_observer_capture_never_raises_on_failure(monkeypatch):
    """A crashing browser tool must degrade to an errored WorldState."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tools.browser_tool":
            raise ImportError("browser unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    state = BrowserObserver(task_id="t1").capture()

    assert state.observed_ok is False
    assert state.accessibility_snapshot == ""
    assert "observation_error" in state.metadata


def test_observer_capture_uses_tool_result(monkeypatch):
    """End-to-end through the real code path with a stubbed tool."""
    import sys
    import types

    fake_module = types.ModuleType("tools.browser_tool")

    def browser_snapshot(full=False, task_id=None, user_task=None):
        return json.dumps({
            "success": True,
            "snapshot": "Page URL: https://fitclair.com/dashboard\nbutton Programme",
            "element_count": 3,
        })

    fake_module.browser_snapshot = browser_snapshot  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tools.browser_tool", fake_module)

    state = BrowserObserver(task_id="t1").capture(user_task="ouvrir le programme")

    assert state.observed_ok is True
    assert state.url == "https://fitclair.com/dashboard"
    assert state.element_count == 3

    # And the diff against the same page (no change) must look suspicious.
    diff = diff_world_states(state, state)
    assert diff.changed is False
    assert diff.suspicious is True
