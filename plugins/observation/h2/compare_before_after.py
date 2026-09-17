#!/usr/bin/env python3
"""H2.0-008c — BEFORE/AFTER the browser_click scroll fix.

BEFORE is reproduced by calling the CLI directly (`click` alone), which is
exactly what the old `browser_click` did.
AFTER goes through the patched `browser_click` (scrollintoview + click).

Ground truth: window.__hits. tool_success is recorded only to be compared.
"""

from __future__ import annotations

import json
import statistics
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
TASK = "h2008c"


def ev(js: str):
    r = _run_browser_command(TASK, "eval", [js], timeout=25)
    d = r.get("data") or {}
    return d.get("result") if isinstance(d, dict) else None


def open_fresh() -> None:
    _run_browser_command(TASK, "open", [f"{BASE}?r={time.time_ns()}"], timeout=45)
    time.sleep(0.35)
    browser_snapshot(full=True, task_id=TASK)


def hits() -> list[str]:
    raw = ev("JSON.stringify(window.__hits || [])")
    try:
        return json.loads(raw) if isinstance(raw, str) else []
    except Exception:
        return []


def probe(sel: str) -> dict:
    raw = ev(f"window.__probe({json.dumps(sel)})")
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}


def before_call(target: str) -> tuple[bool, float]:
    """Reproduce the OLD browser_click: no scroll, @ forced on everything."""
    t = target if target.startswith("@") else f"@{target}"
    t0 = time.perf_counter()
    r = _run_browser_command(TASK, "click", [t], timeout=25)
    return bool(r.get("success")), (time.perf_counter() - t0) * 1000.0


def after_call(target: str) -> tuple[bool, float]:
    """The PATCHED browser_click."""
    t0 = time.perf_counter()
    raw = browser_click(target, task_id=TASK)
    ms = (time.perf_counter() - t0) * 1000.0
    return '"success": true' in str(raw), ms


CASES = [
    ("dans viewport", "#b1", "b1"),
    ("dans viewport", "#b5", "b5"),
    ("hors viewport", "#b9", "b9"),
    ("hors viewport", "#b10", "b10"),
    ("ref hors vp", "@e11", "b10"),
]


def main() -> int:
    rows: list[dict] = []

    print("═" * 104)
    print("  H2.0-008c — browser_click : AVANT vs APRES le fix")
    print("═" * 104)
    print(f"  {'cible':6} {'attendu':8} {'AVANT DOM':10} {'reçu':5} {'ms':>6}   "
          f"{'APRES DOM':10} {'reçu':5} {'ms':>6}")
    print("  " + "─" * 96)

    for label, target, expected in CASES:
        # BEFORE
        open_fresh()
        ev("window.__reset()")
        ok_b, ms_b = before_call(target)
        time.sleep(0.25)
        got_b = hits()
        dom_b = got_b[0] if got_b else "-"

        # AFTER
        open_fresh()
        ev("window.__reset()")
        ok_a, ms_a = after_call(target)
        time.sleep(0.25)
        got_a = hits()
        dom_a = got_a[0] if got_a else "-"

        rows.append({
            "case": label, "target": target, "expected": expected,
            "before_dom": dom_b, "before_ok": dom_b == expected,
            "before_tool": ok_b, "before_ms": round(ms_b, 1),
            "after_dom": dom_a, "after_ok": dom_a == expected,
            "after_tool": ok_a, "after_ms": round(ms_a, 1),
        })
        print(f"  {target:6} {expected:8} {dom_b:10} {str(dom_b == expected):5} {ms_b:6.0f}   "
              f"{dom_a:10} {str(dom_a == expected):5} {ms_a:6.0f}")

    # ── aggregate ─────────────────────────────────────────────────────────
    b_ok = sum(1 for r in rows if r["before_ok"])
    a_ok = sum(1 for r in rows if r["after_ok"])
    b_ms = statistics.mean([r["before_ms"] for r in rows])
    a_ms = statistics.mean([r["after_ms"] for r in rows])

    print("\n" + "─" * 104)
    print(f"  CIBLES RÉELLEMENT ATTEINTES   AVANT : {b_ok}/{len(rows)}"
          f"      APRES : {a_ok}/{len(rows)}")
    print(f"  LATENCE MOYENNE               AVANT : {b_ms:6.1f} ms"
          f"    APRES : {a_ms:6.1f} ms   (delta {a_ms - b_ms:+.1f} ms)")

    faux_succes_b = [r for r in rows if r["before_tool"] and not r["before_ok"]]
    faux_succes_a = [r for r in rows if r["after_tool"] and not r["after_ok"]]
    print(f"  FAUX SUCCÈS (tool ok, cible ratée)  AVANT : {len(faux_succes_b)}"
          f"      APRES : {len(faux_succes_a)}")
    if faux_succes_b:
        print("    avant → " + ", ".join(r["target"] for r in faux_succes_b))
    if faux_succes_a:
        print("    apres → " + ", ".join(r["target"] for r in faux_succes_a))

    # ── ref invalide ──────────────────────────────────────────────────────
    print("\n  REF INVALIDE @e999")
    open_fresh()
    raw = browser_click("@e999", task_id=TASK)
    print(f"    APRES : {str(raw)[:110]}")

    # ── overlay ───────────────────────────────────────────────────────────
    print("\n  OVERLAY plein écran sur #b10")
    open_fresh()
    ev("""(() => { const o=document.createElement('div'); o.id='cov';
          o.style.cssText='position:fixed;inset:0;z-index:100000';
          document.body.appendChild(o); return 1; })()""")
    ev("window.__reset()")
    raw = browser_click("#b10", task_id=TASK)
    time.sleep(0.2)
    got = hits()
    print(f"    APRES : DOM={','.join(got) or '-'}  → l'overlay reçoit le clic "
          f"(détectable) : {got[:1] == ['cov']}")

    Path("/tmp/h2_008c_before_after.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n  JSON -> /tmp/h2_008c_before_after.json")
    print("═" * 104)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
