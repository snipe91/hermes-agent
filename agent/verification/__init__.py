"""Hermes 2.0 — verification layer (Phase 1: additive, no wiring).

This package verifies that a *single* action achieved what was expected,
by comparing the observed world before and after the action.

Design constraints (deliberate):
    - `UNKNOWN` is a first-class outcome, distinct from `FAILED`. An agent
      that cannot tell is not the same as an agent that knows it broke.
    - A tool returning ``success=True`` is NOT evidence the objective was
      reached — it only means the tool call itself did not error out.
    - No vision call by default: verification works on structural signals.
      Vision escalation is a later phase, triggered only on ambiguity.
    - Nothing here mutates browser state or the agent loop.

Relationship to existing infrastructure (do NOT duplicate these):
    - ``agent/verification_evidence.py`` records *terminal command* evidence
      in SQLite for the coding verify-on-stop flow. That module is about
      shell/coding proof and is not browser-aware; this package does not
      replace or extend its storage.
    - ``agent/verification_stop.py`` + ``agent/verify_hooks.py`` drive the
      end-of-turn "did you verify before finishing?" nudge. They act once
      per turn, not once per action. This package is per-action.
"""

from __future__ import annotations

from .action_verifier import (
    ActionVerifier,
    infer_expected_transition,
    verify_action,
)
from .evidence import (
    ActionEvidence,
    ExpectedTransition,
    Outcome,
)

__all__ = [
    "Outcome",
    "ExpectedTransition",
    "ActionEvidence",
    "ActionVerifier",
    "verify_action",
    "infer_expected_transition",
]
