#!/usr/bin/env python3
"""H2.0-011 — real before/after benchmark of browser_click().

BEFORE reproduces the pre-011 implementation exactly: two separate CLI calls
(scrollintoview, then click). AFTER calls the patched browser_click(), which
issues one batch.

Ground truth for correctness is the DOM itself: window.__hits is appended by a
capture-phase listener, so it records what ACTUALLY received the click. It is a
benchmark oracle only — nothing in production reads it.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.browser_tool import (  # noqa: E402
    _run_browser_command,
    browser_click,
    browser_snapshot,
)

BASE = (Path(__file__).resolve().parent / "h2_click_page.html").as_uri()
TASK = "h2011"
BIN = "/Users/snipe91/.npm-global/bin/agent-browser"

TARGETS = [
    ("#b1  (dans viewport)",  "e2",  "b1"),
    ("#b5  (dans viewport)",  "e6",  "b5"),
    ("#b10 (hors viewport)",  "e11", "b10"),
]


def ev(js: str):
    r = _run_browser_command(TASK, "eval", [js], timeout=25)
    d = r.get("data") or {}
    return d.get("result") if isinstance(d, dict) else None


def fresh() -> None:
    _run_browser_command(TASK, "open", [f"{BASE}?t={time.time_ns()}"], timeout=45)
    time.sleep(0.3)
    browser_snapshot(full=True, task_id=TASK)


def hits() -> list[str]:
    raw = ev("JSON.stringify(window.__hits || [])")
    try:
        return json.loads(raw) if isinstance(raw, str) else []
    except Exception:
        return []


def count_procs() -> int:
    """How many CLI processes have been launched so far (rough gauge)."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "agent-browser"], capture_output=True, text=True, timeout=10
        )
        return len([x for x in out.stdout.split() if x.strip()])
    except Exception:
        return -1


def before(target_ref: str) -> float:
    """The pre-011 implementation: two invocations."""
    t0 = time.perf_counter()
    _run_browser_command(TASK, "scrollintoview", [target_ref], timeout=15)
    _run_browser_command(TASK, "click", [target_ref], timeout=25)
    return (time.perf_counter() - t0) * 1000.0


def after(target_ref: str) -> float:
    """The patched browser_click: one batch."""
    t0 = time.perf_counter()
    browser_click(target_ref, task_id=TASK)
    return (time.perf_counter() - t0) * 1000.0


def main() -> int:
    rows = []
    print("=" * 100)
    print("  H2.0-011 — browser_click() : AVANT (2 appels) vs APRES (1 batch)")
    print("=" * 100)
    print(f"  {'cible':22} {'attendu':8} {'AVANT DOM':10} {'ok':4} {'ms':>7}   "
          f"{'APRES DOM':10} {'ok':4} {'ms':>7}")
    print("  " + "─" * 92)

    for label, ref, expected in TARGETS:
        fresh()
        ev("window.__reset()")
        ms_b = before(ref)
        time.sleep(0.25)
        got_b = hits()

        fresh()
        ev("window.__reset()")
        ms_a = after(ref)
        time.sleep(0.25)
        got_a = hits()

        dom_b = got_b[0] if got_b else "-"
        dom_a = got_a[0] if got_a else "-"
        rows.append({
            "label": label, "ref": ref, "expected": expected,
            "before_dom": dom_b, "before_ok": dom_b == expected, "before_ms": ms_b,
            "after_dom": dom_a, "after_ok": dom_a == expected, "after_ms": ms_a,
        })
        print(f"  {label:22} {expected:8} {dom_b:10} {str(dom_b == expected):4} "
              f"{ms_b:7.0f}   {dom_a:10} {str(dom_a == expected):4} {ms_a:7.0f}")

    # ── invalid ref ───────────────────────────────────────────────────────
    print("\n  REF INVALIDE @e999")
    fresh()
    raw_b = None
    t0 = time.perf_counter()
    _run_browser_command(TASK, "scrollintoview", ["@e999"], timeout=15)
    r_b = _run_browser_command(TASK, "click", ["@e999"], timeout=25)
    raw_b = json.dumps(r_b, ensure_ascii=False)[:80]
    print(f"    AVANT : {raw_b}")
    raw_a = json.loads(browser_click("@e999", task_id=TASK))
    print(f"    APRES : {json.dumps(raw_a, ensure_ascii=False)[:90]}")

    # ── totals ────────────────────────────────────────────────────────────
    b_ok = sum(1 for r in rows if r["before_ok"])
    a_ok = sum(1 for r in rows if r["after_ok"])
    b_ms = statistics.mean([r["before_ms"] for r in rows])
    a_ms = statistics.mean([r["after_ms"] for r in rows])

    print("\n" + "─" * 100)
    print("  SYNTHESE")
    print(f"    cibles reellement atteintes    AVANT {b_ok}/{len(rows)}"
          f"      APRES {a_ok}/{len(rows)}")
    print(f"    latence moyenne                AVANT {b_ms:7.1f} ms"
          f"   APRES {a_ms:7.1f} ms   (delta {a_ms - b_ms:+.1f} ms)")
    print(f"    appels CLI par clic observe    AVANT 2         APRES 1"
          f"        (reduction {2 - 1} round-trip)")
    print(f"    processus agent-browser vivants apres le run : {count_procs()}")

    Path("/tmp/h2_011_before_after.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n  JSON -> /tmp/h2_011_before_after.json")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
