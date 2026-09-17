"""Tests for the Hermes 2.0 verification evidence primitives."""

from __future__ import annotations

import json

import pytest

from agent.perception.state_diff import diff_world_states
from agent.perception.world_state import WorldState
from agent.verification import (
    ActionEvidence,
    ExpectedTransition,
    Outcome,
)


def _state(**kwargs) -> WorldState:
    base: dict = {"task_id": "test"}
    base.update(kwargs)
    return WorldState(**base)


def _evidence(**kwargs) -> ActionEvidence:
    base: dict = {"task_id": "test"}
    base.update(kwargs)
    return ActionEvidence(**base)


# ── Outcome ───────────────────────────────────────────────────────────────
def test_outcome_is_three_valued_and_unknown_is_distinct():
    assert Outcome.VERIFIED is not Outcome.FAILED
    assert Outcome.UNKNOWN is not Outcome.FAILED
    assert Outcome.UNKNOWN.value == "unknown"
    assert {o.value for o in Outcome} == {"verified", "failed", "unknown"}


# ── ExpectedTransition ────────────────────────────────────────────────────
def test_empty_transition_has_no_claim():
    assert ExpectedTransition().has_any_claim() is False
    assert (
        ExpectedTransition(description="cliquer sur Enregistrer").has_any_claim()
        is False
    )


def test_transition_with_any_signal_has_a_claim():
    assert ExpectedTransition(expect_url_change=True).has_any_claim() is True
    assert ExpectedTransition(expect_url_contains="dashboard").has_any_claim() is True
    assert ExpectedTransition(expect_dom_change=True).has_any_claim() is True
    assert ExpectedTransition(expect_element_delta=(1, 5)).has_any_claim() is True
    assert ExpectedTransition(min_element_count=3).has_any_claim() is True


def test_transition_to_dict_is_json_safe():
    transition = ExpectedTransition(
        description="ouvrir le programme",
        expect_url_contains="programme",
        expect_element_delta=(0, 4),
    )
    payload = transition.to_dict()

    json.dumps(payload)
    assert payload["expect_element_delta"] == [0, 4]
    assert payload["expect_url_contains"] == "programme"


def test_transition_is_frozen():
    transition = ExpectedTransition(description="x")
    with pytest.raises(Exception):
        transition.description = "y"  # type: ignore[misc]


# ── ActionEvidence ────────────────────────────────────────────────────────
def test_evidence_defaults_to_unknown_not_failed():
    """The absence of information must never read as failure."""
    ev = _evidence()

    assert ev.outcome is Outcome.UNKNOWN
    assert ev.unknown is True
    assert ev.failed is False
    assert ev.verified is False
    assert ev.would_retry is False


def test_only_failed_justifies_a_retry():
    assert _evidence(outcome=Outcome.FAILED).would_retry is True
    assert _evidence(outcome=Outcome.UNKNOWN).would_retry is False
    assert _evidence(outcome=Outcome.VERIFIED).would_retry is False


def test_tool_success_alone_is_explicitly_not_proof():
    ev = _evidence(tool_success=True, outcome=Outcome.UNKNOWN)

    assert ev.tool_success is True
    assert ev.outcome is Outcome.UNKNOWN
    assert ev.metadata == {}  # tagging happens in the verifier, not here


def test_evidence_summary_omits_heavy_fields():
    before = _state(url="https://a.test", accessibility_snapshot="x" * 4000)
    after = _state(url="https://b.test", accessibility_snapshot="y" * 4000)
    ev = _evidence(
        tool_name="browser_click",
        before=before,
        after=after,
        diff=diff_world_states(before, after),
        outcome=Outcome.VERIFIED,
    )
    summary = ev.summary()

    assert summary["outcome"] == "verified"
    assert summary["has_before"] is True
    assert summary["has_after"] is True
    # Snapshots must not leak into the loop-safe view.
    assert "x" * 100 not in json.dumps(summary)


def test_evidence_to_dict_is_json_safe():
    before = _state(url="https://a.test", accessibility_snapshot="button OK")
    after = _state(
        url="https://b.test",
        accessibility_snapshot="button OK\nmenu Next",
        element_count=2,
    )
    ev = _evidence(
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        tool_success=True,
        before=before,
        after=after,
        diff=diff_world_states(before, after),
        expected=ExpectedTransition(description="aller sur b", expect_url_change=True),
        outcome=Outcome.VERIFIED,
        reasons=("url changed",),
    )
    payload = ev.to_dict()

    json.dumps(payload)
    assert payload["tool_args"] == {"ref": "@e5"}
    assert payload["diff"]["url_changed"] is True
    assert payload["before"]["url"] == "https://a.test"
    assert payload["after"]["element_count"] == 2
    assert payload["expected_full"]["expect_url_change"] is True
