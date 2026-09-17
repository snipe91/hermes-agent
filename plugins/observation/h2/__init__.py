"""H2.0 observation plugin — bundled, loaded by the plugin manager.

Registers one ``tool_execution`` middleware. Nothing is observed unless the
mode is explicitly set to ``observe`` (or ``enforce``); with the default mode
of ``off`` the middleware returns immediately and Hermes behaves exactly as
before.
"""

from __future__ import annotations

from plugins.observation.h2.middleware import (
    OBSERVED_TOOLS_PHASE1,
    observe_tool_execution,
    register,
)

__all__ = ["register", "observe_tool_execution", "OBSERVED_TOOLS_PHASE1"]
