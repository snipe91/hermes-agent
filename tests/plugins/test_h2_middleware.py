"""Tests for the H2.0 observation middleware (phase-1 scope + robustness).

The middleware is the ONLY integration point. These tests prove:
    - phase-1 scope is exactly {browser_click}
    - the returned value is always identical to what the downstream returned
    - every H2.0 failure mode is invisible to the caller
"""

from __future__ import annotations

import json

import pytest

from agent.observation import DecisionLedger, VerificationMode
from agent.perception.world_state import WorldState
from plugins.observation.h2 import OBSERVED_TOOLS_PHASE1
from plugins.observation.h2 import middleware as mw


def make_state(url: str, snapshot: str, **kwargs) -> WorldState:
    """Small factory so tests read clearly."""
    base: dict = {"task_id": "t1", "url": url, "accessibility_snapshot": snapshot}
    base.update(kwargs)
    return WorldState(**base)


# ── helpers ───────────────────────────────────────────────────────────────
class FakeObserver:
    def __init__(self, states=None):
        self.calls = 0
        self._states = states or (
            make_state(url="https://a.test", snapshot="button A"),
            make_state(url="https://b.test", snapshot="button A\nmenu B"),
        )

    def capture(self, **kwargs):  # noqa: ARG002
        self.calls += 1
        return self._states[min(self.calls - 1, len(self._states) - 1)]


def _patch_observer(monkeypatch, observer):
    """Force begin/end_observation to use our fake observer."""
    import agent.perception.browser_observer as bo

    class Factory:
        def __init__(self, *a, **k):  # noqa: ARG002
            pass

        def capture(self, **kwargs):
            return observer.capture(**kwargs)

    monkeypatch.setattr(bo, "BrowserObserver", Factory)


def _ledger_dir(monkeypatch, tmp_path):
    """Route all ledgers to tmp_path, caching per task_id.

    The cache matters: the middleware and the assertions must see the SAME
    ledger instance, otherwise entries land in a throwaway object.
    """
    cache: dict[str, DecisionLedger] = {}

    def factory(task_id):
        if task_id not in cache:
            cache[task_id] = DecisionLedger(task_id=task_id, directory=tmp_path)
        return cache[task_id]

    monkeypatch.setattr(mw, "_ledger_for", factory)
    mw._LEDGERS.clear()
    return cache


def _no_vision(monkeypatch):
    """Prevent real vision calls: tests must never need an LLM provider."""
    import agent.observation.integration as integ

    def fake_escalate(*args, **kwargs):  # noqa: ARG001
        decision = type(
            "D", (), {"needed": False, "reason": "disabled in tests", "risk": None}
        )()
        return kwargs.get("evidence"), None, decision

    monkeypatch.setattr(integ, "escalate_unknown", fake_escalate)


CALLED = {"n": 0}


def _downstream(result):
    def call(args):  # noqa: ARG001
        CALLED["n"] += 1
        return result

    return call


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Reset module state and neutralise vision for every test.

    No test in this file may reach a real vision model: it would be slow,
    non-deterministic, and would fail on a machine without an LLM provider.
    """
    mw._LEDGERS.clear()
    CALLED["n"] = 0
    _no_vision(monkeypatch)


# ── phase-1 scope ─────────────────────────────────────────────────────────
def test_phase1_scope_is_browser_click_only():
    assert OBSERVED_TOOLS_PHASE1 == frozenset({"browser_click"})


def test_browser_click_is_observed_in_observe_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("CLICKED")
    )

    assert result == "CLICKED"  # unchanged
    ledger = mw._ledger_for("default")
    assert len(ledger.entries()) == 1
    assert ledger.entries()[0].action_type == "browser_click"


@pytest.mark.parametrize(
    "tool",
    ["browser_navigate", "browser_snapshot", "browser_type", "browser_press"],
)
def test_other_browser_tools_are_not_observed(monkeypatch, tmp_path, tool):
    """Phase 1 is deliberately narrow: only browser_click."""
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    observer = FakeObserver()
    _patch_observer(monkeypatch, observer)

    result = mw.observe_tool_execution(tool, {}, _downstream("OK"))

    assert result == "OK"
    assert observer.calls == 0  # no snapshot taken
    assert mw._ledger_for("default").entries() == []


@pytest.mark.parametrize(
    "tool", ["terminal", "read_file", "write_file", "web_search", "delegate_task"]
)
def test_non_browser_tools_are_not_observed(monkeypatch, tmp_path, tool):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    observer = FakeObserver()
    _patch_observer(monkeypatch, observer)

    result = mw.observe_tool_execution(tool, {}, _downstream("OK"))

    assert result == "OK"
    assert observer.calls == 0
    assert mw._ledger_for("default").entries() == []


# ── OFF ───────────────────────────────────────────────────────────────────
def test_off_returns_immediately_without_observing(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "off")
    _ledger_dir(monkeypatch, tmp_path)
    observer = FakeObserver()
    _patch_observer(monkeypatch, observer)

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"
    assert CALLED["n"] == 1  # the tool DID run
    assert observer.calls == 0  # but nothing was observed
    assert mw._ledger_for("default").entries() == []


def test_off_is_the_default_when_nothing_is_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_BROWSER_ACTION_VERIFICATION", raising=False)
    _ledger_dir(monkeypatch, tmp_path)
    observer = FakeObserver()
    _patch_observer(monkeypatch, observer)

    mw.observe_tool_execution("browser_click", {"ref": "@e5"}, _downstream("OK"))

    assert observer.calls == 0


# ── result identity ───────────────────────────────────────────────────────
def test_result_object_is_returned_by_identity(monkeypatch, tmp_path):
    """Not just equal — the very same object the downstream produced."""
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())

    payload = {"success": True, "clicked": "@e5"}
    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream(payload)
    )

    assert result is payload


def test_exception_is_re_raised_unchanged(monkeypatch, tmp_path):
    """A failing action must propagate the ORIGINAL exception."""
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())

    def boom(args):  # noqa: ARG001
        raise ValueError("element not found")

    with pytest.raises(ValueError, match="element not found"):
        mw.observe_tool_execution("browser_click", {"ref": "@gone"}, boom)

    # The failure was still recorded.
    entries = mw._ledger_for("default").entries()
    assert len(entries) == 1
    assert entries[0].tool_reported_success is False


def test_tool_reported_failure_is_detected_from_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())

    mw.observe_tool_execution(
        "browser_click",
        {"ref": "@e5"},
        _downstream(json.dumps({"success": False, "error": "no such ref"})),
    )

    entry = mw._ledger_for("default").entries()[0]
    assert entry.tool_reported_success is False
    assert "no such ref" in (entry.error or "")


# ── robustness: every H2.0 failure is invisible ───────────────────────────
def test_before_capture_failure_does_not_break_the_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)

    class Boom(FakeObserver):
        def capture(self, **kwargs):
            raise RuntimeError("snapshot exploded")

    _patch_observer(monkeypatch, Boom())

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"  # the tool result survives


def test_begin_observation_failure_is_swallowed(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    monkeypatch.setattr(
        mw,
        "begin_observation",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"


def test_end_observation_failure_is_swallowed(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())
    monkeypatch.setattr(
        mw,
        "end_observation",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"


def test_verifier_failure_does_not_propagate(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())

    import agent.verification.action_verifier as av

    monkeypatch.setattr(
        av, "verify_action", lambda **k: (_ for _ in ()).throw(RuntimeError("v boom"))
    )

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"


def test_ledger_failure_does_not_propagate(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    monkeypatch.setattr(
        mw,
        "_ledger_for",
        lambda task_id: DecisionLedger(task_id=task_id, directory=blocker),
    )
    _patch_observer(monkeypatch, FakeObserver())

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"


def test_resolve_mode_failure_does_not_break_the_tool(monkeypatch):
    monkeypatch.setattr(
        mw,
        "resolve_mode",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cfg boom")),
    )

    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream("OK")
    )

    assert result == "OK"


# ── register ──────────────────────────────────────────────────────────────
def test_register_hooks_the_tool_execution_middleware():
    class FakeCtx:
        def __init__(self):
            self.registered = []

        def register_middleware(self, kind, callback):
            self.registered.append((kind, callback))

    ctx = FakeCtx()
    mw.register(ctx)

    assert len(ctx.registered) == 1
    kind, callback = ctx.registered[0]
    assert kind == "tool_execution"
    assert callback is mw.observe_tool_execution


def test_enforce_mode_also_passes_the_result_through(monkeypatch, tmp_path):
    """ENFORCE must not act on the verdict in this phase."""
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "enforce")
    _ledger_dir(monkeypatch, tmp_path)
    _patch_observer(monkeypatch, FakeObserver())

    payload = "ORIGINAL"
    result = mw.observe_tool_execution(
        "browser_click", {"ref": "@e5"}, _downstream(payload)
    )

    assert result == payload
    assert mw._ledger_for("default").entries()[0].mode == VerificationMode.ENFORCE.value
