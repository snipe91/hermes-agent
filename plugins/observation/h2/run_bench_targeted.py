#!/usr/bin/env python3
"""H2.0 real-session run — baseline vs observe, on a real browser.

Drives the REAL browser tool through the REAL middleware path:

    baseline = browser_click() called directly (no middleware)
    observe  = browser_click() wrapped by run_tool_execution_middleware()

Both use the same page and the same elements, so the delta between them is
H2.0's actual observation overhead.

⚠️ All actions are strictly reversible and local (file:// page, no network, no
publish, no payment, no deletion).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("HERMES_BROWSER_ACTION_VERIFICATION", "observe")

TASK = "h2bench17"
PAGE = (Path(__file__).resolve().parent / "h2_bench_page.html").as_uri()

from hermes_cli.middleware import run_tool_execution_middleware  # noqa: E402
from hermes_cli.plugins import get_plugin_manager  # noqa: E402
from tools import browser_tool as bt  # noqa: E402


def load_plugins() -> bool:
    pm = get_plugin_manager()
    pm.discover_and_load()
    return pm.has_middleware("tool_execution")


REF_RE = re.compile(r"^\s*-\s*(\w+)\s+\"(.*?)\"\s+\[.*?ref=e(\d+)", re.MULTILINE)


def refs_from_snapshot(snap_json: str) -> list[str]:
    """Pull clickable element refs out of a browser_snapshot payload.

    The snapshot lines look like::

        - button "Bouton simple" [ref=e3]

    Note the ref is ``e3`` here, while ``browser_click`` expects ``@e3``.
    """
    try:
        payload = json.loads(snap_json)
    except Exception:
        payload = {}
    text = payload.get("snapshot") or ""

    found: list[str] = []
    for role, _label, num in REF_RE.findall(text):
        if role not in {"button", "link", "menuitem", "tab", "checkbox", "radio"}:
            continue
        ref = f"@e{num}"
        if ref not in found:
            found.append(ref)
    return found


def navigated() -> None:
    bt.browser_navigate(url=PAGE, task_id=TASK)


def do_click_direct(ref: str):
    """Baseline path: the tool, invoked with no middleware involved."""
    return bt.browser_click(ref, task_id=TASK)


def do_click_observed(ref: str):
    """Observe path: exactly how tool_executor invokes the tool."""
    return run_tool_execution_middleware(
        "browser_click",
        {"ref": ref, "task_id": TASK},
        lambda args: bt.browser_click(args["ref"], task_id=args.get("task_id", TASK)),
        task_id=TASK,
        session_id="h2bench17-session",
    )


def main() -> int:
    print("─" * 62)
    print("  H2.0 — EXÉCUTION RÉELLE : BASELINE + OBSERVE")
    print("─" * 62)

    if not load_plugins():
        print("  ❌ middleware H2 non enregistré — ABANDON")
        return 2
    print("  ✅ middleware H2 enregistré")

    navigated()
    snap = bt.browser_snapshot(full=False, task_id=TASK)
    refs = refs_from_snapshot(snap)
    print(f"  page chargée · {len(refs)} éléments interactifs : {refs[:12]}")
    if not refs:
        print("  ❌ aucun élément trouvé — ABANDON")
        return 2

    mode = os.environ.get("HERMES_BROWSER_ACTION_VERIFICATION")
    print(f"  mode = {mode}")

    # ── BASELINE: 10 direct clicks ────────────────────────────────────────
    print("\n  ── BASELINE (10 clics directs, sans middleware) ──")
    baseline = []
    for i in range(10):
        ref = refs[i % len(refs)]
        t0 = time.perf_counter()
        out = do_click_direct(ref)
        ms = (time.perf_counter() - t0) * 1000.0
        baseline.append({
            "ref": ref,
            "latency_ms": round(ms, 3),
            "ok": '"success": false' not in (out or ""),
        })
    ok = sum(1 for b in baseline if b["ok"])
    print(
        f"     {len(baseline)} clics · ok={ok} · "
        f"moyenne={sum(b['latency_ms'] for b in baseline) / len(baseline):.1f} ms"
    )
    Path("/tmp/h2_baseline.json").write_text(json.dumps(baseline), encoding="utf-8")

    # ── OBSERVE: 50 clicks through the middleware ─────────────────────────
    print("\n  ── OBSERVE CIBLÉ (12 clics via le middleware H2) ──")
    observed = []
    for i in range(12):
        ref = refs[i % len(refs)]
        t0 = time.perf_counter()
        out = do_click_observed(ref)
        ms = (time.perf_counter() - t0) * 1000.0
        observed.append({
            "ref": ref,
            "latency_ms": round(ms, 3),
            "ok": '"success": false' not in (out or ""),
        })
        if (i + 1) % 10 == 0:
            print(f"     ... {i + 1}/12")
    print(
        f"     {len(observed)} clics · ok={sum(1 for o in observed if o['ok'])} · "
        f"moyenne={sum(o['latency_ms'] for o in observed) / len(observed):.1f} ms"
    )
    Path("/tmp/h2_observed.json").write_text(json.dumps(observed), encoding="utf-8")

    print("\n  ✅ run terminé · ledger dans ~/.hermes/cache/h2/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
