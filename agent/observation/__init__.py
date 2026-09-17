"""Hermes 2.0 — observation harness (H2.0-004).

Measurement layer: observes real browser actions, records decisions in a
ledger, and aggregates metrics — **without** altering any trajectory.

Modes (``agent.browser_action_verification``, or the env override
``HERMES_BROWSER_ACTION_VERIFICATION``):

    "off"      nothing is observed; behaviour is byte-identical to today
    "observe"  existing behaviour runs unchanged; H2.0 observes in parallel,
               records, and never influences the result returned to the agent
    "enforce"  the integration point exists and is tested, but is NOT enabled
               by default and MUST NOT be turned on globally in this phase

Nothing in this package is imported by the core agent loop yet — wiring is a
reviewed, separate change (see ``integration.py`` for the exact 3-line diff).
"""

from __future__ import annotations

from .integration import (
    OBSERVABLE_TOOLS,
    ObservationContext,
    begin_observation,
    end_observation,
    observation_is_informational_only,
    resolve_mode,
)
from .ledger import (
    DecisionLedger,
    EvidenceQuality,
    LedgerEntry,
    VerificationMode,
    ledger_dir,
)
from .metrics import MetricsCollector, MetricsReport, compute_metrics

__all__ = [
    # modes & ledger
    "VerificationMode",
    "EvidenceQuality",
    "LedgerEntry",
    "DecisionLedger",
    "ledger_dir",
    # metrics
    "MetricsCollector",
    "MetricsReport",
    "compute_metrics",
    # integration
    "OBSERVABLE_TOOLS",
    "ObservationContext",
    "resolve_mode",
    "begin_observation",
    "end_observation",
    "observation_is_informational_only",
]
