"""H2.0-008c/011 — browser_click: scroll + click in ONE batch invocation.

Originally written for H2.0-008c, when the two steps were separate CLI calls.
H2.0-011 merged them into a single `batch` invocation, so these tests were
ported to assert the same *observable contract* over the new transport:

    1. the target is brought into view before it is clicked
    2. the scroll stays best-effort: its failure never becomes the click's result
    3. a failing click keeps its existing clean failure behaviour
    4. refs stay refs-only; CSS selectors are still not supported here
    5. blocked pages and Camofox never reach the CLI at all

The transport-specific assertions (one invocation, no --bail, timeout) live in
test_browser_click_batch.py.
"""

from __future__ import annotations

import json

import pytest

from tools import browser_tool as bt


class FakeBackend:
    """Records CLI calls and answers `batch` like the real CLI would."""

    def __init__(self, click_result=None, scroll_result=None, scroll_raises=False,
                 batch_raises=False):
        self.calls: list[dict] = []
        self._click = click_result if click_result is not None else {"success": True}
        self._scroll = scroll_result if scroll_result is not None else {"success": True}
        self._scroll_raises = scroll_raises
        self._batch_raises = batch_raises

    def __call__(self, task_id, command, args=None, timeout=None, **kwargs):
        stdin_data = kwargs.get("stdin_data")
        self.calls.append({
            "command": command,
            "args": tuple(args or []),
            "stdin_data": stdin_data,
            "timeout": timeout,
        })
        if command != "batch":
            return {"success": True}

        if self._batch_raises:
            raise RuntimeError("batch backend exploded")

        cmds = json.loads(stdin_data) if stdin_data else []
        target = cmds[1][1] if len(cmds) > 1 else "@?"

        scroll_ok = bool(self._scroll.get("success")) and not self._scroll_raises
        items = [
            {
                "command": ["scrollintoview", target],
                "success": scroll_ok,
                "error": self._scroll.get("error") if not scroll_ok else None,
                "result": None,
            },
            {
                "command": ["click", target],
                "success": bool(self._click.get("success")),
                "error": self._click.get("error"),
                "result": self._click.get("data"),
            },
        ]
        return {
            "success": all(i["success"] for i in items),
            "data": {"results": items},
        }

    @property
    def commands(self) -> list[str]:
        return [c["command"] for c in self.calls]

    @property
    def payload(self) -> list[list[str]]:
        return json.loads(self.calls[0]["stdin_data"]) if self.calls else []


@pytest.fixture(autouse=True)
def _no_private_block(monkeypatch):
    """The private-page guard is unrelated to this fix; keep it inert."""
    monkeypatch.setattr(bt, "_blocked_private_page_action", lambda *a, **k: None)
    monkeypatch.setattr(bt, "_last_session_key", lambda key: key)
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: False)
    monkeypatch.setattr(bt, "_copy_fallback_warning", lambda resp, result: resp)


# ── 1. the target is brought into view first, same target for both ────────
def test_target_is_brought_into_view_before_the_click(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    bt.browser_click("@e5", task_id="t")

    assert [c[0] for c in backend.payload] == ["scrollintoview", "click"]
    assert backend.payload[0][1] == backend.payload[1][1] == "@e5"


# ── 2. a scroll failure never becomes the click's result ──────────────────
def test_scroll_failure_does_not_change_the_click_result(monkeypatch):
    backend = FakeBackend(scroll_result={"success": False, "error": "nope"},
                          click_result={"success": True})
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is True


# ── 3. a scroll that raises is absorbed ──────────────────────────────────
def test_scroll_exception_is_swallowed(monkeypatch):
    backend = FakeBackend(scroll_raises=True, click_result={"success": True})
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is True


# ── 4. a failing click keeps its clean failure ───────────────────────────
def test_failing_click_still_reports_clean_failure(monkeypatch):
    backend = FakeBackend(
        click_result={"success": False, "error": "element detached from DOM"}
    )
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is False
    assert payload["error"] == "element detached from DOM"


# ── 5. the click's error outranks the scroll's ───────────────────────────
def test_scroll_error_does_not_overwrite_a_click_error(monkeypatch):
    backend = FakeBackend(
        scroll_result={"success": False, "error": "scroll boom"},
        click_result={"success": False, "error": "element detached from DOM"},
    )
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["error"] == "element detached from DOM"


# ── 6. a bare ref is normalised for both commands ────────────────────────
def test_bare_ref_is_normalised_identically_for_both(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    bt.browser_click("e5", task_id="t")

    assert [c[1] for c in backend.payload] == ["@e5", "@e5"]


# ── 7. documented constraint: refs only, no CSS selectors ────────────────
def test_css_selector_is_not_supported_and_gets_prefixed(monkeypatch):
    """Documents an existing limitation rather than asserting a feature.

    ``browser_click`` accepts **refs only**. A CSS selector is prefixed with
    '@', producing '@#b10', which no backend can resolve. This is the
    pre-existing behaviour and is deliberately NOT changed here.
    """
    backend = FakeBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    bt.browser_click("#b10", task_id="t")

    assert [c[1] for c in backend.payload] == ["@#b10", "@#b10"], (
        "this assertion documents a limitation; if selector support is ever "
        "added, update the docstring of browser_click() at the same time"
    )


# ── 8. a scroll failure leaves a debug trace ─────────────────────────────
def test_scroll_failure_is_logged_for_observability(monkeypatch, caplog):
    backend = FakeBackend(
        scroll_result={"success": False, "error": "scroll backend broken"}
    )
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    with caplog.at_level("DEBUG"):
        payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is True
    assert any("scrollintoview" in str(r.message) for r in caplog.records), (
        "scroll failure should leave a debug trace"
    )


# ── 9. an already-@ ref is passed through untouched ──────────────────────
def test_at_prefixed_ref_is_passed_through(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    bt.browser_click("@e7", task_id="t")

    assert [c[1] for c in backend.payload] == ["@e7", "@e7"]


# ── 10. a blocked page never reaches the CLI ─────────────────────────────
def test_blocked_page_skips_both_scroll_and_click(monkeypatch):
    monkeypatch.setattr(
        bt, "_blocked_private_page_action",
        lambda *a, **k: '{"success": false, "error": "blocked"}',
    )
    backend = FakeBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    payload = json.loads(bt.browser_click("@e5", task_id="t"))

    assert payload["success"] is False
    assert backend.calls == []


# ── 11. Camofox delegates without touching the CLI ───────────────────────
def test_camofox_delegates_without_scrolling(monkeypatch):
    import tools.browser_camofox as camofox

    called: dict = {}
    monkeypatch.setattr(bt, "_is_camofox_mode", lambda: True)
    monkeypatch.setattr(
        camofox, "camofox_click",
        lambda ref, tid: called.setdefault("ref", ref) or "{}",
    )
    backend = FakeBackend()
    monkeypatch.setattr(bt, "_run_browser_command", backend)

    bt.browser_click("@e5", task_id="t")

    assert called.get("ref") == "@e5"
    assert backend.calls == []
