"""Hermes 2.0 — evidence for a single verified action.

An ``ActionEvidence`` is the audit trail of one action: what we expected,
what the world looked like before and after, and what we concluded.

The outcome vocabulary is intentionally three-valued:

    VERIFIED  the expected transition was observed
    FAILED    the world contradicts the expectation (wrong page, obstacle,
              expected change provably absent)
    UNKNOWN   we cannot tell — no expectation to check against, observation
              failed, or the signals are simply not discriminating

``UNKNOWN`` must never be collapsed into ``FAILED``. Treating "I don't know"
as "it broke" would make the verifier untrustworthy and push the agent into
pointless retries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.perception.state_diff import StateDiff
from agent.perception.world_state import WorldState


class Outcome(str, Enum):
    """Three-valued verification result."""

    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value


@dataclass(frozen=True)
class ExpectedTransition:
    """What the caller claims should happen when the action succeeds.

    Every field is optional. A field left at ``None`` means "I make no claim
    about this signal", which keeps it out of the decision instead of
    accidentally counting as satisfaction.

    Attributes:
        description: Human-readable statement of the goal, for logs.
        expect_url_change: True = URL must change, False = must stay, None = no claim.
        expect_url_contains: Substring the resulting URL must contain.
        expect_url_missing: Substring the resulting URL must NOT contain.
        expect_dom_change: True = accessibility tree must change, False = must not.
        expect_element_delta: (min, max) inclusive bounds on element_count delta.
        expect_appearing: Category of element the action is ALLOWED to bring on
            screen — one of ``dialog``/``overlay``/``error``/``blocking``. It is a
            QUALIFIED EXCEPTION, not a switch: only that category is tolerated when
            actually observed, and every other obstacle remains a violation while
            ``expect_no_obstacles`` holds. ``None`` means no claim.
        expect_no_obstacles: True = no new dialog/overlay/error may appear.
        min_element_count: Absolute floor on the resulting element count.
        allow_loading: True = an observed loading state is not a failure.
    """

    description: str = ""

    expect_url_change: bool | None = None
    expect_url_contains: str | None = None
    expect_url_missing: str | None = None

    expect_dom_change: bool | None = None
    expect_element_delta: tuple[int, int] | None = None
    expect_appearing: str | None = None

    expect_no_obstacles: bool = True
    min_element_count: int | None = None

    allow_loading: bool = False

    def has_any_claim(self) -> bool:
        """True when at least one signal is actually asserted.

        A transition carrying no claim cannot verify anything: it must yield
        UNKNOWN, not VERIFIED.

        ``expect_appearing`` counts: an expectation that declares an appearing
        element IS a claim — otherwise "X must appear" would paradoxically be
        treated as no expectation at all.
        """
        return any((
            self.expect_url_change is not None,
            self.expect_url_contains is not None,
            self.expect_url_missing is not None,
            self.expect_dom_change is not None,
            self.expect_element_delta is not None,
            self.expect_appearing is not None,
            self.min_element_count is not None,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "expect_url_change": self.expect_url_change,
            "expect_url_contains": self.expect_url_contains,
            "expect_url_missing": self.expect_url_missing,
            "expect_dom_change": self.expect_dom_change,
            "expect_element_delta": list(self.expect_element_delta)
            if self.expect_element_delta
            else None,
            "expect_appearing": self.expect_appearing,
            "expect_no_obstacles": self.expect_no_obstacles,
            "min_element_count": self.min_element_count,
            "allow_loading": self.allow_loading,
        }


@dataclass(frozen=True)
class ActionEvidence:
    """The audit trail of one action and its verification.

    Attributes:
        task_id: Session/task the action belongs to.
        tool_name: Tool that was invoked (e.g. ``browser_click``).
        tool_args: Arguments passed to the tool, if known.
        tool_success: What the tool *reported*. Never sufficient on its own.
        before: Observation taken before the action, when available.
        after: Observation taken after the action, when available.
        diff: Structural difference between the two observations.
        expected: The claim being checked, when the caller supplied one.
        outcome: Final three-valued verdict.
        reasons: Ordered, human-readable justification of the verdict.
        vision_used: Whether an escalated vision check contributed.
        metadata: Free-form extras (timing, observation errors...).
    """

    task_id: str
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_success: bool = False

    before: WorldState | None = None
    after: WorldState | None = None
    diff: StateDiff | None = None

    expected: ExpectedTransition | None = None

    outcome: Outcome = Outcome.UNKNOWN
    reasons: tuple[str, ...] = ()
    #: Structured cause for an UNKNOWN verdict. Additive: it annotates the
    #: verdict, it never replaces it. See ``agent.perception.unknown_reason``.
    unknown_reason: str = "none"

    vision_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.outcome is Outcome.VERIFIED

    @property
    def failed(self) -> bool:
        return self.outcome is Outcome.FAILED

    @property
    def unknown(self) -> bool:
        return self.outcome is Outcome.UNKNOWN

    @property
    def would_retry(self) -> bool:
        """Whether a caller should consider retrying.

        Only a *proven* failure justifies an automatic retry. An UNKNOWN
        result must not trigger one — that is the whole point of keeping the
        two apart.
        """
        return self.outcome is Outcome.FAILED

    def summary(self) -> dict[str, Any]:
        """Loop-safe representation (no snapshots, no full diffs)."""
        return {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "tool_success": self.tool_success,
            "outcome": self.outcome.value,
            "would_retry": self.would_retry,
            "vision_used": self.vision_used,
            "has_before": self.before is not None,
            "has_after": self.after is not None,
            "expected": self.expected.description if self.expected else None,
            "reasons": list(self.reasons),
        }

    def to_dict(self) -> dict[str, Any]:
        """Full, JSON-safe representation for logs and tests."""
        return {
            **self.summary(),
            "tool_args": dict(self.tool_args),
            "diff": self.diff.to_dict() if self.diff else None,
            "before": self.before.summary() if self.before else None,
            "after": self.after.summary() if self.after else None,
            "expected_full": self.expected.to_dict() if self.expected else None,
            "metadata": dict(self.metadata),
        }
