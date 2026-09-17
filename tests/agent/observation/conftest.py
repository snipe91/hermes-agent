"""Shared fixtures for the observation tests.

The WorldState cache is process-wide by design (production has one browser
session per task). In tests that would let one test's observation leak into the
next, which silently turns "the DOM changed" into "nothing changed". Every test
in this package therefore starts and ends with an empty cache.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_world_state_cache():
    """Give every test a private, empty WorldState cache."""
    try:
        from agent.perception.world_state_cache import reset_cache
    except Exception:  # pragma: no cover - module always present
        yield
        return

    reset_cache()
    try:
        yield
    finally:
        reset_cache()
