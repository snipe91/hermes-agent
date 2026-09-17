"""Hermes 2.0 — observation integration (mode OFF / OBSERVE / ENFORCE).

The pipeline::

    begin_observation()  -> BEFORE State
        [caller runs the existing action, untouched]
    end_observation()    -> AFTER State -> diff -> verifier
                            -> escalation policy -> optional vision
                            -> final verdict -> ledger

Guarantee that shapes every line here:
    In OBSERVE mode, H2.0 must never change what the agent sees, never block a
    trajectory, and never raise. Every stage is individually wrapped, and a
    failure in any of them degrades to "no observation" — never to a broken
    tool call.

Integration point (documented, NOT applied in this phase):
    ``ToolRegistry.dispatch`` in ``tools/registry.py``::

        def dispatch(self, name, args, **kwargs):
            entry = self.get_entry(name)
            if not entry:
                return json.dumps({"error": f"Unknown tool: {name}"})
            obs = begin_observation(name, args, kwargs.get("task_id"))   # +1
            try:
                ...
                result = entry.handler(args, **kwargs)
                normalized = self._normalize_handler_result(name, result)
                end_observation(obs, normalized, success=True)           # +2
                return normalized
            except Exception as e:
                ...
                end_observation(obs, None, success=False, error=str(e))  # +3
                return json.dumps({"error": sanitized})

    Three added lines. ``begin_observation`` returns ``None`` in OFF mode, and
    both functions short-circuit on ``None``, so the OFF path costs one
    attribute-free identity check.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agent.perception.vision_escalation import (
    EscalationPolicy,
    RiskLevel,
    VisionObservation,
    escalate_unknown,
    infer_risk_level,
    vision_is_available,
)
from agent.verification.action_verifier import infer_expected_transition
from agent.verification.evidence import ActionEvidence, Outcome

from .ledger import (
    DecisionLedger,
    EvidenceQuality,
    LedgerEntry,
    VerificationMode,
    utc_now,
)

logger = logging.getLogger(__name__)


# Tools this layer knows how to observe. Anything else is ignored entirely —
# observing a terminal command with browser semantics would be meaningless.
OBSERVABLE_TOOLS = frozenset({
    "browser_click",
    "browser_type",
    "browser_navigate",
    "browser_press",
})


def resolve_mode(config: dict[str, Any] | None = None) -> VerificationMode:
    """Resolve the active mode.

    Precedence mirrors the repo's existing ``verify_on_stop`` idiom:
    an explicit ``HERMES_BROWSER_ACTION_VERIFICATION`` env var wins, then
    ``agent.browser_action_verification`` in config, then a safe default of
    ``"off"``.

    The default is OFF on purpose: an experimental layer must be opted into.

    Args:
        config: Pre-loaded config dict, or None to load it.

    Returns:
        The resolved mode. Unknown values degrade to OFF.
    """
    import os

    env = os.environ.get("HERMES_BROWSER_ACTION_VERIFICATION")
    if env is not None:
        return VerificationMode.parse(env, default=VerificationMode.OFF)

    if config is None:
        try:
            from hermes_cli.config import load_config

            config = load_config()
        except Exception:
            config = {}

    raw: Any = None
    if isinstance(config, dict):
        agent_cfg = config.get("agent")
        if isinstance(agent_cfg, dict):
            raw = agent_cfg.get("browser_action_verification")

    return VerificationMode.parse(raw, default=VerificationMode.OFF)


@dataclass
class ObservationContext:
    """State carried from ``begin_observation`` to ``end_observation``."""

    task_id: str
    tool_name: str
    tool_args: dict[str, Any]
    mode: VerificationMode

    started_at: float = field(default_factory=utc_now)
    before: Any = None
    before_error: str | None = None
    before_ms: float = 0.0  # H2.0 overhead already spent capturing BEFORE
    risk: RiskLevel = RiskLevel.MEDIUM
    expected: Any = None

    # Optional shared ledger: callers may own one ledger for a whole session.
    ledger: DecisionLedger | None = None
    calls_used: int = 0


def _get_cache():
    """Return the process-wide WorldState cache, or a throwaway one.

    Never raises: a cache that cannot be constructed must not stop observation.
    """
    try:
        from agent.perception.world_state_cache import get_cache

        return get_cache()
    except Exception:
        from agent.perception.world_state_cache import WorldStateCache

        return WorldStateCache()


def _should_observe(tool_name: str, mode: VerificationMode) -> bool:
    if mode is VerificationMode.OFF:
        return False
    return tool_name in OBSERVABLE_TOOLS


def begin_observation(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    task_id: str | None = None,
    *,
    mode: VerificationMode | None = None,
    config: dict[str, Any] | None = None,
    observer: Any = None,
    ledger: DecisionLedger | None = None,
    risk: RiskLevel | None = None,
    expected: Any = None,
) -> ObservationContext | None:
    """Capture the BEFORE state. Returns ``None`` when nothing should happen.

    Returning ``None`` is the OFF fast path AND the degradation path: any
    failure to set up observation yields ``None``, and the caller's
    ``end_observation`` then does nothing.

    Never raises.
    """
    try:
        if mode is None:
            mode = resolve_mode(config)

        if not _should_observe(tool_name or "", mode):
            return None

        tid = task_id or "default"

        if observer is None:
            from agent.perception.browser_observer import BrowserObserver

            observer = BrowserObserver(task_id=tid)

        # ── BEFORE: reuse a fresh cached state when one exists ───────────
        # A snapshot costs ~280-330 ms, so serving a recent one is the single
        # cheapest win available. Any cache failure degrades to a real capture.
        cache = _get_cache()
        before = None
        before_ms = 0.0
        ctx_before_error: str | None = None
        _b0 = time.perf_counter()
        try:
            before = cache.get(tid)
        except Exception as exc:
            logger.debug("H2 observe: cache read failed (%s)", exc)
            before = None
        if before is None:
            try:
                before = observer.capture()
            except Exception as exc:
                ctx_before_error = f"{type(exc).__name__}: {exc}"
                logger.debug("H2 observe: before-capture failed (%s)", exc)
            else:
                ctx_before_error = None
                try:
                    cache.put(tid, before)
                except Exception as exc:
                    logger.debug("H2 observe: cache write failed (%s)", exc)
        before_ms = (time.perf_counter() - _b0) * 1000.0

        # ── intent: infer an expectation, or leave it None (=> UNKNOWN) ──
        snapshot_text = ""
        try:
            snapshot_text = getattr(before, "accessibility_snapshot", "") or ""
        except Exception:
            snapshot_text = ""

        resolved_expected = expected
        if resolved_expected is None:
            try:
                from agent.perception.intent import build_intent

                inferred = build_intent(
                    tool_name,
                    tool_args,
                    expected=None,
                    snapshot_text=snapshot_text,
                    risk_level=(risk or infer_risk_level(tool_name, tool_args)).value,
                )
                resolved_expected = inferred.expected_transition
                if resolved_expected is not None:
                    ctx_intent_source = inferred.source
            except Exception as exc:
                logger.debug("H2 observe: intent inference failed (%s)", exc)

        ctx = ObservationContext(
            task_id=tid,
            tool_name=tool_name,
            tool_args=dict(tool_args or {}),
            mode=mode,
            before=before,
            before_error=ctx_before_error,
            before_ms=before_ms,
            risk=risk or infer_risk_level(tool_name, tool_args),
            expected=resolved_expected,
            ledger=ledger,
        )

        return ctx
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("H2 observe: begin_observation failed (%s)", exc)
        return None


def end_observation(
    ctx: ObservationContext | None,
    result: Any = None,
    *,
    success: bool = True,
    error: str | None = None,
    action_latency_ms: float = 0.0,
    observer: Any = None,
    policy: EscalationPolicy | None = None,
    vision_available: bool | None = None,
    runner: Any = None,
) -> ActionEvidence | None:
    """Observe AFTER, verify, optionally escalate, and record. Never raises.

    Args:
        ctx: The context from ``begin_observation``; ``None`` short-circuits.
        result: What the tool returned (recorded, never inspected for meaning).
        success: Whether the tool reported success.
        error: Tool-level error string, if any.
        action_latency_ms: How long the tool's own execution took. Measured by
            the caller (the middleware wraps ``next_call``), and kept strictly
            separate from H2.0's own overhead.
        observer: Injection seam for tests.
        policy: Escalation policy.
        vision_available: Override the availability probe.
        runner: Vision runner injection seam.

    Returns:
        The ``ActionEvidence`` (post-escalation) for callers that want it, or
        ``None`` when nothing was observed. **The return value is informational
        only** — in OBSERVE mode the caller must not act on it.
    """
    if ctx is None:
        return None

    started = time.perf_counter()
    vision_ms = 0.0
    after_ms = 0.0
    verify_ms = 0.0
    initial_verdict = Outcome.UNKNOWN.value
    final_verdict = Outcome.UNKNOWN.value
    unknown_reason = "none"
    escalated = False
    quality = EvidenceQuality.UNAVAILABLE.value
    obstacles = 0
    verify_error: str | None = None
    evidence: ActionEvidence | None = None

    try:
        if observer is None:
            from agent.perception.browser_observer import BrowserObserver

            observer = BrowserObserver(task_id=ctx.task_id)

        after = None
        after_error: str | None = None
        # The action just ran, so any cached state is now stale by definition.
        # A cache that survived the action would make every click look like it
        # changed nothing.
        try:
            _get_cache().invalidate(ctx.task_id)
        except Exception as exc:
            logger.debug("H2 observe: cache invalidate failed (%s)", exc)
        _a0 = time.perf_counter()
        try:
            after = observer.capture()
        except Exception as exc:
            after_error = f"{type(exc).__name__}: {exc}"
            logger.debug("H2 observe: after-capture failed (%s)", exc)
        after_ms = (time.perf_counter() - _a0) * 1000.0
        try:
            from agent.perception.world_state_cache import get_cache as _gc

            _gc().put(ctx.task_id, after)
        except Exception as exc:
            logger.debug("H2 observe: cache store after failed (%s)", exc)

        # ── verify ────────────────────────────────────────────────────────
        _v0 = time.perf_counter()
        try:
            from agent.verification.action_verifier import verify_action

            evidence = verify_action(
                before=ctx.before,
                after=after,
                expected=ctx.expected,
                tool_name=ctx.tool_name,
                tool_args=ctx.tool_args,
                tool_success=success,
                task_id=ctx.task_id,
            )
            initial_verdict = evidence.outcome.value
            final_verdict = initial_verdict
            unknown_reason = getattr(evidence, "unknown_reason", "none") or "none"
            if evidence.diff is not None:
                obstacles = (
                    evidence.diff.dialogs_opened
                    + evidence.diff.overlays_added
                    + evidence.diff.errors_added
                )
        except Exception as exc:
            verify_error = f"{type(exc).__name__}: {exc}"
            logger.warning("H2 observe: verifier failed (%s)", exc)
        verify_ms = (time.perf_counter() - _v0) * 1000.0
        if evidence is not None and evidence.outcome is Outcome.UNKNOWN:
            try:
                v_start = time.perf_counter()
                escalated_ev, observation, decision = escalate_unknown(
                    evidence=evidence,
                    risk=ctx.risk,
                    expected=ctx.expected,
                    policy=policy,
                    task_id=ctx.task_id,
                    vision_available=vision_available,
                    calls_used=ctx.calls_used,
                    runner=runner,
                )
                if decision.needed:
                    escalated = True
                    vision_ms = (time.perf_counter() - v_start) * 1000.0
                    quality = _quality_for(observation)
                    if escalated_ev.outcome is not Outcome.UNKNOWN:
                        final_verdict = escalated_ev.outcome.value
                    else:
                        # Vision ran but did not settle it.
                        unknown_reason = "vision_inconclusive"
                    evidence = escalated_ev
                elif "unavailable" in (getattr(decision, "reason", "") or "").lower():
                    # Vision was the only way forward and it is provably absent.
                    # Recording the reason is the point: it distinguishes "we
                    # could not see" from "we could not decide".
                    unknown_reason = "vision_unavailable"
            except Exception as exc:
                logger.warning("H2 observe: escalation failed (%s)", exc)

        # ── evidence quality when no vision ran ──────────────────────────
        if quality == EvidenceQuality.UNAVAILABLE.value:
            quality = _quality_without_vision(
                evidence, ctx.before, after_error or ctx.before_error
            )

    except Exception as exc:  # pragma: no cover - defensive outer guard
        verify_error = verify_error or f"{type(exc).__name__}: {exc}"
        logger.warning("H2 observe: end_observation failed (%s)", exc)

    latency_ms = (time.perf_counter() - started) * 1000.0

    # ── ledger (best-effort, always last) ────────────────────────────────
    try:
        ledger = ctx.ledger
        if ledger is None:
            ledger = DecisionLedger(task_id=ctx.task_id, mode=ctx.mode)
        entry = LedgerEntry(
            timestamp=utc_now(),
            task_id=ctx.task_id,
            action_type=ctx.tool_name,
            target=_target_of(ctx.tool_args),
            correlation_id=_correlation_of(ctx.tool_args),
            risk_level=ctx.risk.value,
            before_state_hash=_hash_of(ctx.before),
            after_state_hash=_hash_of(evidence.after if evidence else None),
            state_changed=bool(evidence.diff.changed)
            if evidence and evidence.diff
            else False,
            expected_state_present=bool(
                ctx.expected is not None and ctx.expected.has_any_claim()
            ),
            initial_verdict=initial_verdict,
            vision_escalated=escalated,
            final_verdict=final_verdict,
            unknown_reason=unknown_reason,
            obstacles_detected=obstacles,
            observation_quality=quality,
            # H2.0 overhead = only the phases H2.0 owns. The action's own
            # duration is reported separately and never folded in here.
            snapshot_before_ms=ctx.before_ms,
            snapshot_after_ms=after_ms,
            verification_latency_ms=verify_ms,
            vision_latency_ms=vision_ms,
            total_observation_overhead_ms=(
                ctx.before_ms + after_ms + verify_ms + vision_ms
            ),
            action_latency_ms=action_latency_ms,
            latency_ms=latency_ms,  # total wall time (action + overhead)
            error=error or verify_error,
            mode=ctx.mode.value,
            ground_truth=None,  # never inferred
            tool_reported_success=success,
            metadata={
                "result_type": type(result).__name__,
                "before_error": ctx.before_error,
            },
        )
        ledger.record(entry)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("H2 observe: ledger failed (%s)", exc)

    return evidence


def _correlation_of(tool_args: dict[str, Any]) -> str:
    """H3-④E (a) — clé de corrélation, recopiée TELLE QUELLE depuis l'appel observé.

    La source est ``args["delegation_id"]``, déjà transporté par le contexte
    (``ObservationContext.tool_args``) : aucune convention, aucun renommage.

    Absente ⇒ ``""``. **Aucun repli vers ``task_id``** : ce sont deux identités
    distinctes, et une observation sans clé ne doit être rattachée à RIEN.
    """
    value = (tool_args or {}).get("delegation_id")
    return str(value) if value else ""


def _target_of(tool_args: dict[str, Any]) -> str:
    """Best-effort description of what the action targeted."""
    for key in ("ref", "url", "selector", "text"):
        value = tool_args.get(key)
        if value:
            return str(value)[:200]
    return ""


def _hash_of(state: Any) -> str | None:
    try:
        return state.structural_hash if state is not None else None
    except Exception:
        return None


def _quality_for(observation: VisionObservation | None) -> str:
    """Map a vision observation to an evidence quality."""
    if observation is None:
        return EvidenceQuality.UNAVAILABLE.value
    if not observation.available:
        return EvidenceQuality.UNAVAILABLE.value
    return EvidenceQuality.VISUAL_HEURISTIC.value


def _quality_without_vision(
    evidence: ActionEvidence | None,
    before: Any,
    observation_error: str | None,
) -> str:
    """Classify evidence quality when the structural path alone was used."""
    if observation_error:
        return EvidenceQuality.UNAVAILABLE.value
    if evidence is None or evidence.before is None or evidence.after is None:
        return EvidenceQuality.UNAVAILABLE.value
    if not evidence.before.observed_ok or not evidence.after.observed_ok:
        return EvidenceQuality.UNAVAILABLE.value
    if evidence.expected is not None and evidence.expected.has_any_claim():
        return EvidenceQuality.STRUCTURAL.value
    # Observable, but nothing was claimed — the strongest honest statement.
    return EvidenceQuality.STRUCTURAL.value


def observation_is_informational_only(mode: VerificationMode) -> bool:
    """Whether a verdict may be acted upon.

    True for OFF and OBSERVE — the agent's trajectory must be untouched.
    Only ENFORCE would ever return False, and ENFORCE is not enabled in this
    phase.
    """
    return mode is not VerificationMode.ENFORCE
