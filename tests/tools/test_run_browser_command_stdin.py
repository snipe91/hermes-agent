"""H2.0-011 (part 1/2) — RED tests for `stdin_data` + batch normalisation.

Exercises `_run_browser_command` itself by mocking `subprocess.Popen`, so the
stdin wiring and the result normalisation are observed directly rather than
through a fake caller.

These must FAIL against the current implementation.
"""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

import tools.browser_tool as bt  # noqa: E402


class FakeStdin:
    """Captures what would have been written to the child's stdin."""

    def __init__(self):
        self.written = b""
        self.closed = False

    def write(self, data):
        self.written += data

    def close(self):
        self.closed = True


def make_fake_proc(stdout_text="", returncode=0, cmd=None):
    """A MagicMock stands in for Popen's return value.

    Using a real object here means chasing every attribute the production path
    happens to touch (stdin/args/poll/wait/communicate/__enter__...). A mock
    already satisfies all of them, so the tests stay focused on behaviour.
    """
    proc = MagicMock()
    proc.returncode = returncode
    proc.args = cmd if cmd is not None else []
    proc.stdin = FakeStdin()
    proc.wait.return_value = 0
    proc.poll.return_value = returncode
    proc.communicate.return_value = (stdout_text, "")
    proc.kill = MagicMock()
    return proc


FakeProc = make_fake_proc


@pytest.fixture
def popen_spy(monkeypatch, tmp_path):
    """Intercept Popen and capture the kwargs Hermes would use."""
    captured: dict = {}

    def fake_popen(cmd_parts, **kwargs):
        captured["cmd"] = cmd_parts
        captured["kwargs"] = kwargs
        proc = FakeProc()
        captured["proc"] = proc
        return proc

    # The function reads stdout/stderr from temp files, so we stub those.
    monkeypatch.setattr(bt.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        bt, "_read_command_output_files", lambda out, err: ('{"success": true}', "")
    )
    monkeypatch.setattr(bt, "_unlink_command_output_files", lambda *a: None)
    monkeypatch.setattr(bt, "_get_session_info", lambda tid: {"session_name": "t1"})
    monkeypatch.setattr(bt, "_write_owner_pid", lambda *a: None)
    monkeypatch.setattr(bt, "_build_browser_env", lambda: {})
    monkeypatch.setattr(bt, "_merge_browser_path", lambda p: p)
    monkeypatch.setattr(bt, "_socket_safe_tmpdir", lambda: str(tmp_path))
    monkeypatch.setattr(bt, "BROWSER_SESSION_INACTIVITY_TIMEOUT", 60)
    monkeypatch.setattr(bt, "_get_browser_engine", lambda: "auto")
    monkeypatch.setattr(bt, "_is_headed_mode", lambda: False)
    monkeypatch.setattr(bt, "_needs_chromium_sandbox_bypass", lambda: False)
    monkeypatch.setattr(bt, "_maybe_autoinstall_chromium", lambda: False)
    monkeypatch.setattr(bt, "_running_in_docker", lambda: False)
    monkeypatch.setattr(bt, "_chromium_available", lambda: True, raising=False)
    return captured


# ── 1. stdin stays DEVNULL when no payload is supplied ────────────────────
def test_no_stdin_data_keeps_devnull(popen_spy):
    bt._run_browser_command("t", "click", ["@e5"], timeout=25)
    assert popen_spy["kwargs"]["stdin"] is bt.subprocess.DEVNULL, (
        "callers that pass no stdin_data must keep today's DEVNULL behaviour"
    )


# ── 2. stdin becomes a PIPE and receives the exact payload ────────────────
def test_stdin_data_opens_pipe_and_writes_payload(popen_spy):
    payload = json.dumps([["scrollintoview", "@e5"], ["click", "@e5"]])
    bt._run_browser_command("t", "batch", [], stdin_data=payload, timeout=40)
    assert popen_spy["kwargs"]["stdin"] is bt.subprocess.PIPE, (
        "a stdin_data call must switch stdin to a pipe"
    )


# ── 3. the pipe is written then closed (otherwise the CLI blocks on EOF) ──
def test_stdin_pipe_is_written_and_closed(popen_spy):
    payload = json.dumps([["click", "@e5"]])
    bt._run_browser_command("t", "batch", [], stdin_data=payload, timeout=40)
    proc = popen_spy["proc"]
    assert proc.stdin.written == payload.encode("utf-8"), (
        "the child must receive the exact JSON payload"
    )
    assert proc.stdin.closed is True, "stdin must be closed or the CLI waits forever"


# ── 4. a batch array is normalised into the dict contract ────────────────
def test_batch_list_is_normalised_to_dict(monkeypatch, tmp_path):
    items = [
        {"command": ["scrollintoview", "@e5"], "success": False, "error": "x", "result": None},
        {"command": ["click", "@e5"], "success": True, "error": None, "result": {}},
    ]
    _patch_stdout(monkeypatch, tmp_path, json.dumps(items))
    result = bt._run_browser_command("t", "batch", [], stdin_data="[]", timeout=40)
    assert isinstance(result, dict), "batch must not leak a bare list to callers"
    assert result["data"]["results"] == items


# ── 5. a normal command's shape is strictly unchanged ────────────────────
def test_normal_command_result_shape_unchanged(monkeypatch, tmp_path):
    inner = {"success": True, "data": {"clicked": "@e5"}, "error": None}
    _patch_stdout(monkeypatch, tmp_path, json.dumps(inner))
    result = bt._run_browser_command("t", "click", ["@e5"], timeout=25)
    assert result == inner, "non-batch commands must be returned verbatim"


# ── 6. a JSON *list* from a NON-batch command is not auto-normalised ─────
def test_non_batch_list_is_not_normalised(monkeypatch, tmp_path):
    _patch_stdout(monkeypatch, tmp_path, json.dumps([1, 2, 3]))
    result = bt._run_browser_command("t", "eval", ["[1,2,3]"], timeout=25)
    assert result == [1, 2, 3], (
        "normalisation must key off command == 'batch', not off the payload type"
    )


def _seed_stdout_file(monkeypatch, stdout_text: str) -> None:
    """Seed the stdout temp file the moment the production code creates it.

    The success path does NOT call ``_read_command_output_files`` — it reads the
    file directly (``open(stdout_path).read()``). Stubbing the reader therefore
    has no effect; the file itself has to carry the payload.
    """
    import os as _os

    real_open = _os.open

    def fake_os_open(path, flags, mode=0o600):
        fd = real_open(path, flags, mode)
        if "_stdout_" in str(path) and stdout_text:
            _os.write(fd, stdout_text.encode("utf-8"))
            _os.lseek(fd, 0, _os.SEEK_SET)
        return fd

    monkeypatch.setattr(bt.os, "open", fake_os_open)


def _patch_stdout(monkeypatch, tmp_path, stdout_text: str) -> None:
    """Share the Popen/stdout stubbing used by the parsing tests."""
    monkeypatch.setattr(
        bt.subprocess,
        "Popen",
        lambda cmd, **kw: make_fake_proc(stdout_text=stdout_text, cmd=cmd),
    )
    _seed_stdout_file(monkeypatch, stdout_text)
    monkeypatch.setattr(
        bt, "_read_command_output_files", lambda out, err: (stdout_text, "")
    )
    monkeypatch.setattr(bt, "_unlink_command_output_files", lambda *a: None)
    monkeypatch.setattr(bt, "_get_session_info", lambda tid: {"session_name": "t1"})
    monkeypatch.setattr(bt, "_write_owner_pid", lambda *a: None)
    monkeypatch.setattr(bt, "_build_browser_env", lambda: {})
    monkeypatch.setattr(bt, "_merge_browser_path", lambda p: p)
    monkeypatch.setattr(bt, "_socket_safe_tmpdir", lambda: str(tmp_path))
    monkeypatch.setattr(bt, "BROWSER_SESSION_INACTIVITY_TIMEOUT", 60)
    monkeypatch.setattr(bt, "_get_browser_engine", lambda: "auto")
    monkeypatch.setattr(bt, "_is_headed_mode", lambda: False)
    monkeypatch.setattr(bt, "_needs_chromium_sandbox_bypass", lambda: False)
    monkeypatch.setattr(bt, "_maybe_autoinstall_chromium", lambda: False)
    monkeypatch.setattr(bt, "_running_in_docker", lambda: False)
