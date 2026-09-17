"""H2.0-011b — RED tests for the engine branch inside browser_click().

Decision C: the batch optimisation applies to Chrome (the default, `auto`),
while Lightpanda keeps the historical two-call path so that the
Lightpanda→Chrome fallback and its `fallback_warning` keep working exactly as
before.

The engine is resolved with `_get_browser_engine()` — the SAME call
`_run_browser_command()` uses. No new heuristic lives in browser_click().

These must FAIL against the current implementation (which always batches).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tools.browser_tool as bt  # noqa: E402


class EngineBackend:
    """Records calls; answers `batch` and single commands like the real CLI."""

    def __init__(self, click_success=True, click_error=None,
                 scroll_success=True, fallback_warning=None):
        self.calls: list[dict] = []
        self.click_success = click_success
        self.click_error = click_error
        self.scroll_success = scroll_success
        self.fallback_warning = fallback_warning

    def __call__(self, task_id, command, args=None, timeout=None,
                 _engine_override=None, stdin_data=None):
        self.calls.append({
            "command": command,
            "args": list(args or []),
            "timeout": timeout,
            "stdin_data": stdin_data,
            "_engine_override": _engine_override,
        })
        result: dict = {"success": True, "data": {}}

        if command == "scrollintoview":
            result = {"success": self.scroll_success, "error": None, "data": {}}
        elif command == "click":
            result = {
                "success": self.click_success,
                "error": self.click_error,
                "data": {"clicked": (args or ["?"])[0]},
            }
        elif command == "batch":
            cmds = json.loads(stdin_data) if stdin_data else []
            target = cmds[1][1] if len(cmds) > 1 else "@?"
            items = [
                {"command": ["scrollintoview", target], "success": self.scroll_success,
                 "error": None, "result": None},
                {"command": ["click", target], "success": self.click_success,
                 "error": self.click_error, "result": {"clicked": target}},
            ]
            result = {"success": all(i["success"] for i in items),
                      "data": {"results": items}}

        if self.fallback_warning is not None:
            result["fallback_warning"] = self.fallback_warning
            result["browser_engine"] = "chrome"
        return result

    @property
    def commands(self) -> list[str]:
        return [c["command"] for c in self.calls]


def _install(monkeypatch, backend, engine: str):
    monkeypatch.setattr(bt, "_run_browser_command", backend)
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: False)
    monkeypatch.setattr(bt, "_blocked_private_page_action", lambda tid, cmd: None)
    monkeypatch.setattr(bt, "_last_session_key", lambda k: k)
    monkeypatch.setattr(bt, "_get_browser_engine", lambda: engine)


# ── 1. Lightpanda keeps the historical two-call path ─────────────────────
def test_lightpanda_uses_legacy_two_calls(monkeypatch):
    backend = EngineBackend()
    _install(monkeypatch, backend, "lightpanda")

    bt.browser_click("@e5", task_id="t")

    assert backend.commands == ["scrollintoview", "click"], (
        "under Lightpanda the two operations must stay separate so the "
        "Lightpanda→Chrome fallback keeps applying to each of them"
    )


# ── 2. engine=auto (the default) resolves to Chrome -> batch ─────────────
def test_auto_engine_uses_batch(monkeypatch):
    backend = EngineBackend()
    _install(monkeypatch, backend, "auto")

    bt.browser_click("@e5", task_id="t")

    assert backend.commands == ["batch"], "auto means Chrome: batch it"


# ── 3. an explicit chrome engine also batches ────────────────────────────
def test_chrome_engine_uses_batch(monkeypatch):
    backend = EngineBackend()
    _install(monkeypatch, backend, "chrome")

    bt.browser_click("@e5", task_id="t")

    assert backend.commands == ["batch"]


# ── 4. the fallback_warning survives on the Lightpanda path ──────────────
def test_lightpanda_propagates_the_fallback_warning(monkeypatch):
    warning = "⚠ Lightpanda fallback: Chrome was used for this browser action."
    backend = EngineBackend(fallback_warning=warning)
    _install(monkeypatch, backend, "lightpanda")

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload.get("fallback_warning") == warning, (
        "the Lightpanda fallback warning is a real user-facing contract and "
        "must keep reaching the caller"
    )
    assert payload.get("browser_engine") == "chrome"


# ── 5. the engine probe is the SAME resolution as _run_browser_command ───
def test_engine_probe_uses_get_browser_engine(monkeypatch):
    """browser_click must not invent its own engine heuristic."""
    seen = {"calls": 0}
    backend = EngineBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: False)
    monkeypatch.setattr(bt, "_blocked_private_page_action", lambda tid, cmd: None)
    monkeypatch.setattr(bt, "_last_session_key", lambda k: k)

    def spy_engine():
        seen["calls"] += 1
        return "auto"

    monkeypatch.setattr(bt, "_get_browser_engine", spy_engine)

    bt.browser_click("@e5", task_id="t")

    assert seen["calls"] >= 1, (
        "_get_browser_engine() is the single source of truth for the engine; "
        "browser_click must consult it rather than guess"
    )


# ── 6. Lightpanda still reports a scroll failure as best-effort ──────────
def test_lightpanda_scroll_failure_is_still_best_effort(monkeypatch):
    backend = EngineBackend(scroll_success=False, click_success=True)
    _install(monkeypatch, backend, "lightpanda")

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is True


# ── 7. Lightpanda: a failing click still fails cleanly ───────────────────
def test_lightpanda_click_failure_is_clean(monkeypatch):
    backend = EngineBackend(click_success=False, click_error="element detached from DOM")
    _install(monkeypatch, backend, "lightpanda")

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is False
    assert payload["error"] == "element detached from DOM"
