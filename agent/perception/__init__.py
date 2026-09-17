"""Hermes 2.0 — perception layer (Phase 1: passive).

This package observes existing Hermes/browser state without changing any
existing agent behaviour. It executes no actions, calls no LLM, and decides
nothing on its own.

The full accessibility snapshot lives on WorldState; `summary()` and
`StateDiff.to_dict()` are the small, safe representations to pass around the
agent loop.
"""

from __future__ import annotations

from .browser_observer import BrowserObserver
from .state_diff import StateDiff, diff_world_states
from .vision_escalation import (
    EscalationDecision,
    EscalationPolicy,
    RiskLevel,
    VisionBudget,
    VisionObservation,
    decide_escalation,
    escalate_unknown,
    infer_risk_level,
    judge_observation,
    observe_with_vision,
    vision_is_available,
)
from .world_state import WorldState

__all__ = [
    "WorldState",
    "StateDiff",
    "diff_world_states",
    "BrowserObserver",
    # H2.0-003 — vision escalation
    "RiskLevel",
    "EscalationPolicy",
    "EscalationDecision",
    "VisionObservation",
    "VisionBudget",
    "infer_risk_level",
    "decide_escalation",
    "observe_with_vision",
    "judge_observation",
    "escalate_unknown",
    "vision_is_available",
]
