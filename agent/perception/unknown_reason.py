"""Hermes 2.0 — structured reasons for an UNKNOWN verdict.

UNKNOWN is not one condition, it is several, and they need different fixes:

    no_expected_transition   nothing was claimed, so nothing can be proven
    insufficient_observation we could not look (or looked and saw too little)
    contradictory_observation the evidence disagrees with itself
    vision_unavailable       vision was needed but no backend exists
    vision_inconclusive      vision ran and did not settle the question
    observer_failure         the observation mechanism itself errored

The reason is ADDITIVE: it never replaces the verdict, it only annotates it.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class UnknownReason(str, Enum):
    """Why a verdict came out UNKNOWN."""

    NONE = "none"
    NO_EXPECTED_TRANSITION = "no_expected_transition"
    INSUFFICIENT_OBSERVATION = "insufficient_observation"
    CONTRADICTORY_OBSERVATION = "contradictory_observation"
    VISION_UNAVAILABLE = "vision_unavailable"
    VISION_INCONCLUSIVE = "vision_inconclusive"
    OBSERVER_FAILURE = "observer_failure"
    NOT_APPLICABLE = "not_applicable"

    @classmethod
    def parse(cls, raw: Any) -> "UnknownReason":
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, str):
            for member in cls:
                if member.value == raw.strip().lower():
                    return member
        return cls.NONE


#: Ordered by priority when several reasons apply. The most *actionable* cause
#: wins: a broken observer explains everything else, and a missing expectation
#: is more diagnostic than "we could not see".
_PRIORITY: tuple[UnknownReason, ...] = (
    UnknownReason.OBSERVER_FAILURE,
    UnknownReason.NO_EXPECTED_TRANSITION,
    UnknownReason.CONTRADICTORY_OBSERVATION,
    UnknownReason.VISION_UNAVAILABLE,
    UnknownReason.VISION_INCONCLUSIVE,
    UnknownReason.INSUFFICIENT_OBSERVATION,
)


def pick_reason(*candidates: UnknownReason) -> UnknownReason:
    """Return the highest-priority reason among the candidates.

    Args:
        *candidates: Reasons that could apply. ``NONE``/``NOT_APPLICABLE`` are
            ignored unless nothing else is present.

    Returns:
        The most actionable reason, or ``NONE`` if no candidate is meaningful.
    """
    relevant = [
        c
        for c in candidates
        if c not in (UnknownReason.NONE, UnknownReason.NOT_APPLICABLE)
    ]
    for reason in _PRIORITY:
        if reason in relevant:
            return reason
    return UnknownReason.NONE
