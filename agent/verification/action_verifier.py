"""Hermes 2.0 — per-action verification.

Pipeline implemented here::

    ACTION -> BEFORE STATE -> EXECUTION -> AFTER STATE
           -> STATE DIFF -> EXPECTED TRANSITION -> VERIFIED / FAILED / UNKNOWN

Scope discipline:
    - This module does NOT wrap, patch, or import-time-hook ``browser_click``
      or any other tool. Wiring is a separate phase, and only after these
      tests are complete.
    - It performs no page-mutating action. The only browser call it makes is
      ``browser_snapshot`` (read-only), through ``BrowserObserver``.
    - It never calls a vision model by default.

Documented limitations (verified against the real codebase — not invented):

    1. **No expectation is inferable from a browser tool call.**
       ``browser_click(ref="@e5")`` carries no machine-readable statement of
       what should happen; the ref is an opaque handle from the last snapshot.
       There is therefore no reliable way to derive an ``ExpectedTransition``
       from the tool name and args alone. ``infer_expected_transition`` only
       handles the one case where the intent is unambiguous (``browser_navigate``
       with a ``url``), and returns ``None`` otherwise, which forces UNKNOWN.
       Callers that know the goal must pass it explicitly.

    2. **Obstacles are only partially observable.**
       ``browser_snapshot`` returns ``dialogs`` / ``overlays`` / ``errors``
       only when a CDP supervisor is attached. Otherwise those tuples are
       always empty, so "no new obstacles" can be vacuously satisfied. The
       evidence records ``metadata["obstacles_observable"]`` so a caller can
       tell the difference between "none appeared" and "we could not look".

    3. **Loading is heuristic.** ``browser_snapshot`` does not report a loading
       flag; it is inferred from snapshot text by ``BrowserObserver``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from agent.perception.browser_observer import BrowserObserver
from agent.perception.state_diff import StateDiff, diff_world_states
from agent.perception.unknown_reason import UnknownReason
from agent.perception.world_state import WorldState

from .evidence import ActionEvidence, ExpectedTransition, Outcome

logger = logging.getLogger(__name__)


# ── expectation inference ─────────────────────────────────────────────────
def infer_expected_transition(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
) -> ExpectedTransition | None:
    """Derive an expectation from a tool call when — and only when — unambiguous.

    Returns ``None`` when no reliable claim can be made, which the verifier
    turns into UNKNOWN. This is the honest default: most browser actions carry
    no machine-readable statement of their intended effect.

    Args:
        tool_name: Name of the invoked tool.
        tool_args: Arguments it was invoked with.

    Returns:
        An ``ExpectedTransition`` when the intent follows from the arguments,
        otherwise ``None``.
    """
    args = tool_args or {}
    name = (tool_name or "").strip()

    if name == "browser_navigate":
        url = str(args.get("url") or "").strip()
        if url:
            return ExpectedTransition(
                description=f"navigate to {url}",
                expect_url_change=True,
                expect_url_contains=_host_and_path(url),
                expect_no_obstacles=True,
            )
        return None

    # browser_click / browser_type / browser_press_on_ref and friends: the ref
    # is opaque and the intent is unknown. No claim -> UNKNOWN, by design.
    return None


def _host_and_path(url: str) -> str | None:
    """Reduce a URL to a stable, comparable fragment (scheme-less)."""
    cleaned = url.strip()
    if not cleaned:
        return None
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    cleaned = cleaned.split("#", 1)[0].rstrip("/")
    return cleaned or None


# ── the verifier ──────────────────────────────────────────────────────────
class ActionVerifier:
    """Verify a single action by diffing the world around it.

    Usage (explicit observation, no wiring required)::

        verifier = ActionVerifier(task_id="t1")
        before = verifier.observe()
        result = tool_call()                  # unchanged, existing code
        evidence = verifier.verify_after(
            before=before,
            tool_name="browser_click",
            tool_args={"ref": "@e5"},
            tool_success=result_ok,
            expected=ExpectedTransition(expect_url_contains="dashboard"),
        )
        if evidence.failed:
            ...

    Nothing here is called automatically. The class is inert until a caller
    uses it.
    """

    def __init__(
        self,
        task_id: str = "default",
        observer: BrowserObserver | None = None,
        *,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.task_id = task_id
        self.observer = observer or BrowserObserver(task_id=task_id)
        self.config = config

    # ── observation ───────────────────────────────────────────────────────
    def observe(
        self,
        *,
        user_task: str | None = None,
        full: bool = False,
    ) -> WorldState:
        """Take a read-only observation. Never raises."""
        return self.observer.capture(user_task=user_task, full=full)

    # ── public entry points ───────────────────────────────────────────────
    def verify_after(
        self,
        *,
        before: WorldState | None,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        tool_success: bool = False,
        expected: ExpectedTransition | None = None,
        user_task: str | None = None,
        after: WorldState | None = None,
        full: bool = False,
    ) -> ActionEvidence:
        """Observe the current state and verify the action against ``expected``.

        Args:
            before: Observation taken before the action (None if unavailable).
            tool_name: Tool that ran.
            tool_args: Arguments it ran with.
            tool_success: What the tool reported. Not treated as proof.
            expected: The claim to check. ``None`` -> UNKNOWN.
            user_task: Passed through to the observation.
            after: Pre-captured post-state, to avoid a second observation.
            full: Request a full snapshot when observing.

        Returns:
            An ``ActionEvidence`` whose ``outcome`` is never a guess.
        """
        if after is None:
            after = self.observe(user_task=user_task, full=full)
        return verify_action(
            before=before,
            after=after,
            expected=expected,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_success=tool_success,
            task_id=self.task_id,
        )

    @contextmanager
    def around(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        *,
        expected: ExpectedTransition | None = None,
        user_task: str | None = None,
        full: bool = False,
    ) -> Iterator[Callable[..., ActionEvidence]]:
        """Observe before/after around a caller-supplied block.

        The caller still owns execution — this does not invoke any tool::

            with verifier.around("browser_click", {"ref": "@e5"}) as done:
                ok = browser_click("@e5")     # existing code, untouched
                evidence = done(ok)

        Yields:
            A callable taking the tool's reported success and returning the
            ``ActionEvidence``.
        """
        before = self.observe(user_task=user_task, full=full)

        def _done(tool_success: bool = False, **kwargs: Any) -> ActionEvidence:
            return self.verify_after(
                before=before,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_success=tool_success,
                expected=expected,
                user_task=user_task,
                after=kwargs.get("after"),
                full=full,
            )

        yield _done


# ── pure evaluation ───────────────────────────────────────────────────────
def verify_action(
    *,
    before: WorldState | None,
    after: WorldState | None,
    expected: ExpectedTransition | None = None,
    tool_name: str = "",
    tool_args: dict[str, Any] | None = None,
    tool_success: bool = False,
    task_id: str = "default",
) -> ActionEvidence:
    """Pure function: evaluate an action from two observations.

    No I/O, no browser, no model call — which makes it trivially testable and
    safe to call from anywhere.

    Decision order:
        1. Missing observation        -> UNKNOWN (we could not look)
        2. No expectation / no claim  -> UNKNOWN (nothing to check)
        3. Any violated claim         -> FAILED
        4. All claims satisfied       -> VERIFIED
    """
    reasons: list[str] = []
    metadata: dict[str, Any] = {}

    # ── 1. observability ──────────────────────────────────────────────────
    if before is None or after is None:
        reasons.append("missing observation (before/after unavailable)")
        metadata["observability"] = "partial"
        return _build(
            Outcome.UNKNOWN,
            reasons,
            metadata,
            task_id,
            tool_name,
            tool_args,
            tool_success,
            before,
            after,
            None,
            expected,
        )

    if not after.observed_ok:
        reasons.append(
            f"post-action observation failed: {after.metadata.get('observation_error')}"
        )
        metadata["observability"] = "failed"
        return _build(
            Outcome.UNKNOWN,
            reasons,
            metadata,
            task_id,
            tool_name,
            tool_args,
            tool_success,
            before,
            after,
            None,
            expected,
        )

    diff = diff_world_states(before, after)

    # Obstacles are only visible when a CDP supervisor is attached; record
    # whether we could actually look, so "none appeared" is distinguishable
    # from "we could not see".
    obstacles_observable = bool(
        after.metadata.get("has_supervisor_state")
        or before.metadata.get("has_supervisor_state")
        or before.dialogs
        or before.overlays
        or before.errors
        or after.dialogs
        or after.overlays
        or after.errors
    )
    metadata["obstacles_observable"] = obstacles_observable

    # ── 2. is there anything to check? ────────────────────────────────────
    if expected is None:
        reasons.append("no expectation supplied (tool call carries no stated goal)")
        return _build(
            Outcome.UNKNOWN,
            reasons,
            metadata,
            task_id,
            tool_name,
            tool_args,
            tool_success,
            before,
            after,
            diff,
            expected,
        )

    if not expected.has_any_claim():
        reasons.append("expectation carries no checkable claim")
        return _build(
            Outcome.UNKNOWN,
            reasons,
            metadata,
            task_id,
            tool_name,
            tool_args,
            tool_success,
            before,
            after,
            diff,
            expected,
        )

    # ── 3. evaluate every claim; a violation is a proven failure ──────────
    violations: list[str] = []
    satisfactions: list[str] = []

    # 3a. URL claims
    if expected.expect_url_contains is not None:
        needle = expected.expect_url_contains
        if needle.lower() in (after.url or "").lower():
            satisfactions.append(f"url contains {needle!r}")
        else:
            violations.append(f"url {after.url!r} does not contain {needle!r}")

    if expected.expect_url_missing is not None:
        needle = expected.expect_url_missing
        if needle.lower() in (after.url or "").lower():
            violations.append(f"url {after.url!r} must not contain {needle!r}")
        else:
            satisfactions.append(f"url free of {needle!r}")

    if expected.expect_url_change is True:
        if diff.url_changed:
            satisfactions.append("url changed")
        elif after.loading and not expected.allow_loading:
            # Navigation may still be in flight; not proof of failure.
            reasons.append("url unchanged but page still loading")
            return _build(
                Outcome.UNKNOWN,
                reasons,
                metadata,
                task_id,
                tool_name,
                tool_args,
                tool_success,
                before,
                after,
                diff,
                expected,
            )
        else:
            violations.append("url did not change")
    elif expected.expect_url_change is False:
        if diff.url_changed:
            violations.append(f"url changed unexpectedly ({after.url!r})")
        else:
            satisfactions.append("url unchanged as expected")

    # 3b. DOM claims
    if expected.expect_dom_change is True:
        if diff.accessibility_changed:
            satisfactions.append("accessibility tree changed")
        elif after.loading and not expected.allow_loading:
            reasons.append("dom unchanged but page still loading")
            return _build(
                Outcome.UNKNOWN,
                reasons,
                metadata,
                task_id,
                tool_name,
                tool_args,
                tool_success,
                before,
                after,
                diff,
                expected,
            )
        else:
            violations.append("accessibility tree unchanged")
    elif expected.expect_dom_change is False:
        if diff.accessibility_changed:
            violations.append("accessibility tree changed unexpectedly")
        else:
            satisfactions.append("accessibility tree stable")

    # 3c. Element-count claims
    if expected.expect_element_delta is not None:
        low, high = expected.expect_element_delta
        delta = after.element_count - before.element_count
        if low <= delta <= high:
            satisfactions.append(f"element delta {delta} within [{low}, {high}]")
        else:
            violations.append(f"element delta {delta} outside [{low}, {high}]")

    if expected.min_element_count is not None:
        if after.element_count >= expected.min_element_count:
            satisfactions.append(
                f"element count {after.element_count} >= {expected.min_element_count}"
            )
        else:
            violations.append(
                f"element count {after.element_count} < {expected.min_element_count}"
            )

    # 3d. Obstacles
    if expected.expect_no_obstacles:
        added = diff.dialogs_opened + diff.overlays_added + diff.errors_added
        if added:
            violations.append(
                "obstacle appeared after the action "
                f"(dialogs +{diff.dialogs_opened}, overlays +{diff.overlays_added}, "
                f"errors +{diff.errors_added})"
            )
        elif obstacles_observable:
            satisfactions.append("no obstacle appeared")
        else:
            # Nothing to observe: record it as an explicit non-finding rather
            # than claiming the world is clean. Kept in `satisfactions` because
            # that list is what reaches the verdict.
            satisfactions.append(
                "no obstacle claim checkable (obstacles not observable without a CDP supervisor)"
            )

    # ── 4. verdict ────────────────────────────────────────────────────────
    if violations:
        return _build(
            Outcome.FAILED,
            violations + satisfactions,
            metadata,
            task_id,
            tool_name,
            tool_args,
            tool_success,
            before,
            after,
            diff,
            expected,
        )

    if satisfactions:
        return _build(
            Outcome.VERIFIED,
            satisfactions,
            metadata,
            task_id,
            tool_name,
            tool_args,
            tool_success,
            before,
            after,
            diff,
            expected,
        )

    reasons.append("no claim could be evaluated from the available signals")
    return _build(
        Outcome.UNKNOWN,
        reasons,
        metadata,
        task_id,
        tool_name,
        tool_args,
        tool_success,
        before,
        after,
        diff,
        expected,
    )


def _infer_unknown_reason(
    outcome: Outcome,
    reasons: list[str],
    before: WorldState | None,
    after: WorldState | None,
) -> str:
    """Classify *why* a verdict came out UNKNOWN.

    Derived from the reasons the verifier already produces, so no caller has to
    be changed and no new decision path is introduced. The verdict itself is
    untouched — this only annotates it.

    Args:
        outcome: The verdict the verifier reached.
        reasons: Human-readable reasons gathered during evaluation.
        before: The BEFORE observation, if any.
        after: The AFTER observation, if any.

    Returns:
        An ``UnknownReason`` value; ``"none"`` for non-UNKNOWN verdicts.
    """
    if outcome is not Outcome.UNKNOWN:
        return UnknownReason.NONE.value

    text = " ".join(reasons).lower()

    observer_broken = False
    for state in (before, after):
        if state is None:
            continue
        try:
            if not state.observed_ok:
                observer_broken = True
        except Exception:
            observer_broken = True
    if observer_broken or "missing observation" in text:
        return UnknownReason.OBSERVER_FAILURE.value

    if "no expectation supplied" in text or "carries no checkable claim" in text:
        return UnknownReason.NO_EXPECTED_TRANSITION.value

    if "contradict" in text:
        return UnknownReason.CONTRADICTORY_OBSERVATION.value

    if "vision" in text and "unavailable" in text:
        return UnknownReason.VISION_UNAVAILABLE.value

    if "no claim could be evaluated" in text:
        return UnknownReason.INSUFFICIENT_OBSERVATION.value

    return UnknownReason.INSUFFICIENT_OBSERVATION.value


def _build(
    outcome: Outcome,
    reasons: list[str],
    metadata: dict[str, Any],
    task_id: str,
    tool_name: str,
    tool_args: dict[str, Any] | None,
    tool_success: bool,
    before: WorldState | None,
    after: WorldState | None,
    diff: StateDiff | None,
    expected: ExpectedTransition | None,
) -> ActionEvidence:
    """Assemble the evidence record, tagging tool-reported success honestly."""
    meta = dict(metadata)
    meta["tool_reported_success"] = tool_success
    meta["tool_success_is_proof"] = False
    if tool_success and outcome is Outcome.UNKNOWN:
        meta["note"] = "tool reported success but the objective is not demonstrated"

    return ActionEvidence(
        task_id=task_id,
        tool_name=tool_name,
        tool_args=dict(tool_args or {}),
        tool_success=tool_success,
        before=before,
        after=after,
        diff=diff,
        expected=expected,
        outcome=outcome,
        reasons=tuple(reasons),
        unknown_reason=_infer_unknown_reason(outcome, reasons, before, after),
        vision_used=False,
        metadata=meta,
    )
