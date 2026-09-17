"""H2.0-011 (part 2/2) — RED tests for browser_click() as a single batch.

The pair scrollintoview + click must now cost ONE CLI invocation, while
preserving every observable behaviour: the click stays the authority, the
scroll stays best-effort, refs stay refs-only, and Camofox/blocked pages never
reach the CLI at all.

These must FAIL against the current implementation (which issues two calls).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tools.browser_tool as bt  # noqa: E402


class BatchBackend:
    """Records every _run_browser_command call and fakes batch results."""

    def __init__(self, click_success=True, click_error=None,
                 scroll_success=True, scroll_error=None, drop_click=False):
        self.calls: list[dict] = []
        self.click_success = click_success
        self.click_error = click_error
        self.scroll_success = scroll_success
        self.scroll_error = scroll_error
        self.drop_click = drop_click

    def __call__(self, task_id, command, args=None, timeout=None,
                 _engine_override=None, stdin_data=None):
        self.calls.append({
            "task_id": task_id,
            "command": command,
            "args": list(args or []),
            "timeout": timeout,
            "stdin_data": stdin_data,
        })
        if command != "batch":
            return {"success": True, "data": {}}

        # Read the requested target back out of the payload we were handed.
        cmds = json.loads(stdin_data) if stdin_data else []
        target = cmds[1][1] if len(cmds) > 1 else "@e?"

        items = [
            {"command": ["scrollintoview", target], "success": self.scroll_success,
             "error": self.scroll_error, "result": {}},
        ]
        if not self.drop_click:
            items.append(
                {"command": ["click", target], "success": self.click_success,
                 "error": self.click_error, "result": {"clicked": target}},
            )
        return {"success": all(i["success"] for i in items), "data": {"results": items}}

    @property
    def batch_calls(self) -> list[dict]:
        return [c for c in self.calls if c["command"] == "batch"]


def _install(monkeypatch, backend):
    monkeypatch.setattr(bt, "_run_browser_command", backend)
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: False)
    monkeypatch.setattr(bt, "_blocked_private_page_action", lambda tid, cmd: None)


# ── 6. exactly ONE CLI invocation, and it is a batch ─────────────────────
def test_one_single_cli_invocation(monkeypatch):
    backend = BatchBackend()
    _install(monkeypatch, backend)
    bt.browser_click("@e5", task_id="t")
    assert len(backend.calls) == 1, (
        f"scroll+click must cost one invocation, got {len(backend.calls)}"
    )
    assert backend.calls[0]["command"] == "batch"


# ── 7. order is scrollintoview THEN click ────────────────────────────────
def test_order_is_scroll_then_click(monkeypatch):
    backend = BatchBackend()
    _install(monkeypatch, backend)
    bt.browser_click("@e5", task_id="t")
    payload = json.loads(backend.batch_calls[0]["stdin_data"])
    assert [c[0] for c in payload] == ["scrollintoview", "click"]


# ── 8. both commands target the SAME ref ─────────────────────────────────
def test_both_commands_share_the_same_target(monkeypatch):
    backend = BatchBackend()
    _install(monkeypatch, backend)
    bt.browser_click("@e5", task_id="t")
    payload = json.loads(backend.batch_calls[0]["stdin_data"])
    assert payload[0][1] == payload[1][1] == "@e5"


# ── 9. no --bail: a failing scroll must not stop the click ───────────────
def test_no_bail_flag_and_click_still_runs_after_scroll_failure(monkeypatch):
    backend = BatchBackend(scroll_success=False, scroll_error="Unknown ref: e5")
    _install(monkeypatch, backend)
    payload_raw = None
    bt.browser_click("@e5", task_id="t")
    payload_raw = backend.batch_calls[0]["stdin_data"]
    assert "--bail" not in payload_raw, "no --bail: the click must always be attempted"
    assert backend.batch_calls[0]["args"] == [] or "--bail" not in backend.batch_calls[0]["args"]


# ── 10. scroll failed but click succeeded -> SUCCESS ─────────────────────
def test_scroll_failure_with_click_success_is_success(monkeypatch):
    backend = BatchBackend(scroll_success=False, scroll_error="Unknown ref: e5",
                           click_success=True)
    _install(monkeypatch, backend)
    payload = json.loads(bt.browser_click("@e5", task_id="t"))
    assert payload["success"] is True, "a scroll failure must not mask a real click"


# ── 11. scroll succeeded but click failed -> the CLICK error wins ────────
def test_click_failure_is_the_authority(monkeypatch):
    backend = BatchBackend(scroll_success=True, click_success=False,
                           click_error="element detached from DOM")
    _install(monkeypatch, backend)
    payload = json.loads(bt.browser_click("@e5", task_id="t"))
    assert payload["success"] is False
    assert payload["error"] == "element detached from DOM", (
        "a scroll success must never turn a click failure into a success"
    )


# ── 12. invalid ref -> the click's own Unknown ref error is preserved ────
def test_invalid_ref_keeps_click_unknown_ref_error(monkeypatch):
    backend = BatchBackend(click_success=False, click_error="Unknown ref: e999",
                           scroll_success=False, scroll_error="Unknown ref: e999")
    _install(monkeypatch, backend)
    payload = json.loads(bt.browser_click("@e999", task_id="t"))
    assert payload["success"] is False
    assert "Unknown ref: e999" in payload["error"]


# ── 13. a batch with no click item -> clean failure, never a success ─────
def test_batch_without_click_result_fails_cleanly(monkeypatch):
    backend = BatchBackend(drop_click=True)
    _install(monkeypatch, backend)
    payload = json.loads(bt.browser_click("@e5", task_id="t"))
    assert payload["success"] is False, "no click result must never be a success"


# ── 14. the global timeout is 40 s ───────────────────────────────────────
def test_batch_timeout_is_40_seconds(monkeypatch):
    backend = BatchBackend()
    _install(monkeypatch, backend)
    bt.browser_click("@e5", task_id="t")
    assert backend.batch_calls[0]["timeout"] == 40, (
        "a single global budget must cover scroll+click; 15+25 serialised into 40"
    )


# ── 15. Camofox never reaches the batch path ─────────────────────────────
def test_camofox_does_not_use_batch(monkeypatch):
    import tools.browser_camofox as camofox

    called: dict = {}
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: True)
    monkeypatch.setattr(
        camofox, "camofox_click",
        lambda ref, tid: called.setdefault("ref", ref) or '{"success": true}',
    )
    backend = BatchBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    bt.browser_click("@e5", task_id="t")

    assert called.get("ref") == "@e5"
    assert backend.calls == [], "camofox must not touch the CLI"


# ── 16. a blocked page never reaches the batch path ──────────────────────
def test_blocked_page_does_not_use_batch(monkeypatch):
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: False)
    monkeypatch.setattr(
        bt, "_blocked_private_page_action",
        lambda tid, cmd: '{"success": false, "error": "blocked"}',
    )
    backend = BatchBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is False
    assert backend.calls == [], "a blocked page must never issue a batch"


# ── 17. refs-only is unchanged: a bare ref becomes @e5 in the payload ────
def test_bare_ref_is_normalised_in_the_batch_payload(monkeypatch):
    backend = BatchBackend()
    _install(monkeypatch, backend)
    bt.browser_click("e5", task_id="t")
    payload = json.loads(backend.batch_calls[0]["stdin_data"])
    assert payload[0][1] == "@e5" and payload[1][1] == "@e5"
