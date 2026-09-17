"""H2.0 observation middleware — the single integration point.

Registered as a ``tool_execution`` middleware via the repo's existing plugin
system. This means **no core file is modified**: ``agent/tool_executor.py``
already calls ``run_tool_execution_middleware``, and with no middleware
registered that call is a single dict lookup followed by ``next_call(args)``.

Behaviour by mode (``agent.browser_action_verification``, env override
``HERMES_BROWSER_ACTION_VERIFICATION``):

    off      returns ``next_call(args)`` immediately — byte-identical to today
    observe  wraps the call: BEGIN -> action -> END, records a ledger entry,
             and returns the action's result **unchanged**
    enforce  identical to observe in this phase; the verdict is not acted upon

Phase-1 scope: **only ``browser_click`` is observed.** Other browser tools and
all non-browser tools pass through untouched — proven by tests, not assumed.

Hard invariant: the value returned by this middleware is always exactly what
``next_call`` returned (or the exception it raised). H2.0 can fail in any way
it likes; it can never change a tool's result.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from agent.observation import (
    VerificationMode,
    begin_observation,
    end_observation,
    resolve_mode,
)
from agent.observation.ledger import DecisionLedger

logger = logging.getLogger(__name__)

# ── PHASE 1 SCOPE ─────────────────────────────────────────────────────────
# Deliberately a single tool. Widening this is a reviewed decision, made only
# after the first real measurement run.
OBSERVED_TOOLS_PHASE1: frozenset[str] = frozenset({"browser_click"})

# One ledger per session, reused across actions so entries accumulate in a
# single file. Keyed by task_id; bounded to avoid unbounded growth.
_LEDGERS: dict[str, DecisionLedger] = {}
_MAX_LEDGERS = 32


def _ledger_for(task_id: str) -> DecisionLedger:
    """Return (and lazily create) the ledger for a task."""
    ledger = _LEDGERS.get(task_id)
    if ledger is None:
        if len(_LEDGERS) >= _MAX_LEDGERS:
            _LEDGERS.clear()  # coarse but bounded; entries are on disk anyway
        ledger = DecisionLedger(task_id=task_id)
        _LEDGERS[task_id] = ledger
    return ledger


def _extract_success(result: Any) -> tuple[bool, str | None]:
    """Infer whether a tool reported success, from its returned payload.

    Conservative: only a clear ``success: false`` or an ``error`` key counts as
    a failure. Everything else is treated as "no error reported", which keeps
    the signal honest without guessing at tool-specific shapes.
    """
    import json

    payload: Any = result
    if isinstance(result, str):
        try:
            payload = json.loads(result)
        except Exception:
            return True, None  # non-JSON text: no error reported
    if isinstance(payload, dict):
        if payload.get("success") is False:
            return False, str(payload.get("error") or "reported success=false")
        if payload.get("error"):
            return False, str(payload["error"])
    return True, None


def observe_tool_execution(
    tool_name: str,
    args: dict[str, Any],
    next_call: Callable[[dict[str, Any]], Any],
    **context: Any,
) -> Any:
    """Wrap a tool execution with H2.0 observation.

    This function is registered as ``tool_execution`` middleware. It must be
    invisible when H2.0 is off, and must never alter the downstream result.
    """
    # ── fast path: not in scope, or disabled ─────────────────────────────
    try:
        if tool_name not in OBSERVED_TOOLS_PHASE1:
            return next_call(args)
        mode = resolve_mode()
        if mode is VerificationMode.OFF:
            return next_call(args)
    except Exception as exc:  # pragma: no cover - defensive
        # A failure while *deciding* must not stop the tool.
        logger.warning("H2 middleware: pre-check failed (%s)", exc)
        return next_call(args)

    task_id = str(context.get("task_id") or "default")

    # ── BEFORE (never blocks) ────────────────────────────────────────────
    ctx = None
    try:
        ctx = begin_observation(
            tool_name,
            args,
            task_id,
            mode=mode,
            ledger=_ledger_for(task_id),
        )
    except Exception as exc:
        logger.warning("H2 middleware: begin_observation failed (%s)", exc)
        ctx = None

    # ── ACTION — the existing execution, timed on its own ────────────────
    action_ms = 0.0
    result: Any = None
    success = True
    error: str | None = None
    raised: BaseException | None = None

    _t0 = time.perf_counter()
    try:
        result = next_call(args)
    except BaseException as exc:  # noqa: BLE001 - we re-raise unchanged
        raised = exc
        success = False
        error = f"{type(exc).__name__}: {exc}"
    finally:
        action_ms = (time.perf_counter() - _t0) * 1000.0

    if raised is None:
        success, error = _extract_success(result)

    # ── AFTER (never blocks, never alters) ───────────────────────────────
    if ctx is not None:
        try:
            end_observation(
                ctx,
                result,
                success=success,
                error=error,
                action_latency_ms=action_ms,
            )
        except Exception as exc:
            logger.warning("H2 middleware: end_observation failed (%s)", exc)

    # ── the invariant: pass through exactly what happened ────────────────
    if raised is not None:
        raise raised
    return result


def register(ctx) -> None:
    """Register the observation middleware with the plugin context."""
    ctx.register_middleware("tool_execution", observe_tool_execution)


__all__ = [
    "OBSERVED_TOOLS_PHASE1",
    "observe_tool_execution",
    "register",
]
