#!/usr/bin/env python3
"""H2.0-008b — compare click strategies before touching any production file.

Variants measured (all on the same bench page, same 10 buttons):

    V0  click seul                    (current Hermes behaviour)
    V1  scrollintoview puis click     (architecture A: Hermes does the scroll)
    V2  scrollintoview conditionnel   (A optimised: only when out of viewport)
    V3  scroll (page) puis click      (fallback if ref-based scroll is unreliable)

Criteria per variant:
    taux de clic reellement recu par la cible
    comportement des refs @eN
    comportement des selecteurs CSS
    clics deja dans le viewport
    ref invalide
    overlays / modals
    cout de latence

Ground truth remains window.__hits (capture-phase listener). tool_success is
recorded only to be COMPARED against it, never trusted.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.browser_tool import _run_browser_command, browser_snapshot  # noqa: E402

BASE = (Path(__file__).resolve().parent / "h2_click_page.html").as_uri()
TASK = "h2008b"


def ev(js: str):
    r = _run_browser_command(TASK, "eval", [js], timeout=25)
    d = r.get("data") or {}
    return d.get("result") if isinstance(d, dict) else None


def open_fresh() -> None:
    _run_browser_command(TASK, "open", [f"{BASE}?r={time.time_ns()}"], timeout=45)
    time.sleep(0.35)
    browser_snapshot(full=True, task_id=TASK)   # populate the ref table


def reset() -> None:
    ev("window.__reset()")


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


def cli(*args: str) -> dict:
    return _run_browser_command(TASK, args[0], list(args[1:]), timeout=25)


def v0(sel: str) -> dict:
    """click seul (comportement actuel de Hermes)."""
    return cli("click", sel)


def v1(sel: str) -> dict:
    """scrollintoview inconditionnel puis click (architecture A)."""
    cli("scrollintoview", sel)
    return cli("click", sel)


def v2(sel: str) -> tuple[dict, bool]:
    """scrollintoview seulement si hors viewport (A optimise)."""
    p = probe(sel)
    did_scroll = not p.get("inViewport", True)
    if did_scroll:
        cli("scrollintoview", sel)
    return cli("click", sel), did_scroll


VARIANTS = {
    "V0 click seul": v0,
    "V1 scroll+click": v1,
}


def run_target(variant_name: str, sel: str, fresh: bool = True) -> dict:
    """One trial: returns whether the DOM received the click, plus timings."""
    if fresh:
        open_fresh()
    reset()
    before = probe(sel)
    t0 = time.perf_counter()
    fn = VARIANTS[variant_name]
    result = fn(sel)
    ms = (time.perf_counter() - t0) * 1000.0
    time.sleep(0.25)
    got = hits()
    after = probe(sel)
    return {
        "variant": variant_name,
        "target": sel,
        "tool_ok": bool(result.get("success")),
        "dom_hit": got[0] if got else "-",
        "hit_ok": bool(got and got[0] == sel.lstrip("#")),
        "in_vp_before": before.get("inViewport"),
        "scroll_before": (before.get("scroll") or {}).get("y"),
        "scroll_after": (after.get("scroll") or {}).get("y"),
        "at_point_before": before.get("elementFromPoint"),
        "latency_ms": round(ms, 1),
    }


def main() -> int:
    rows: list[dict] = []

    print("═" * 100)
    print("  H2.0-008b — COMPARAISON DES STRATEGIES DE CLIC")
    print("═" * 100)

    # ── A. hors viewport (le cas casse) ───────────────────────────────────
    print("\n  A. CIBLES HORS VIEWPORT (#b9, #b10)")
    for sel in ("#b9", "#b10"):
        for variant in VARIANTS:
            row = run_target(variant, sel)
            rows.append(row)
            print(f"     {variant:16} {sel:6} tool_ok={str(row['tool_ok']):5} "
                  f"DOM={row['dom_hit']:5} recu={str(row['hit_ok']):5} "
                  f"in_vp={row['in_vp_before']} lat={row['latency_ms']:.0f}ms")

    # ── B. dans le viewport (non-regression) ──────────────────────────────
    print("\n  B. CIBLES DANS LE VIEWPORT (#b1, #b5) — non-regression")
    for sel in ("#b1", "#b5"):
        for variant in VARIANTS:
            row = run_target(variant, sel)
            rows.append(row)
            print(f"     {variant:16} {sel:6} tool_ok={str(row['tool_ok']):5} "
                  f"DOM={row['dom_hit']:5} recu={str(row['hit_ok']):5} "
                  f"in_vp={row['in_vp_before']} lat={row['latency_ms']:.0f}ms")

    # ── C. refs @eN ───────────────────────────────────────────────────────
    print("\n  C. REFS @eN (snapshot prealable) — @e12 = bouton 10, hors viewport")
    for variant in VARIANTS:
        open_fresh()
        reset()
        ref = "@e12"
        before = probe("#b10")
        t0 = time.perf_counter()
        if variant == "V1 scroll+click":
            cli("scrollintoview", ref)
        result = cli("click", ref)
        ms = (time.perf_counter() - t0) * 1000.0
        time.sleep(0.25)
        got = hits()
        row = {
            "variant": variant, "target": ref,
            "tool_ok": bool(result.get("success")),
            "dom_hit": got[0] if got else "-",
            "hit_ok": bool(got and got[0] == "b10"),
            "in_vp_before": before.get("inViewport"),
            "scroll_before": (before.get("scroll") or {}).get("y"),
            "scroll_after": (probe("#b10").get("scroll") or {}).get("y"),
            "at_point_before": before.get("elementFromPoint"),
            "latency_ms": round(ms, 1),
        }
        rows.append(row)
        print(f"     {variant:16} {ref:6} tool_ok={str(row['tool_ok']):5} "
              f"DOM={row['dom_hit']:5} recu={str(row['hit_ok']):5} "
              f"lat={row['latency_ms']:.0f}ms")

    # ── D. ref invalide ───────────────────────────────────────────────────
    print("\n  D. REF INVALIDE @e999 — echec propre attendu")
    for variant in VARIANTS:
        open_fresh()
        reset()
        t0 = time.perf_counter()
        if variant == "V1 scroll+click":
            cli("scrollintoview", "@e999")
        result = cli("click", "@e999")
        ms = (time.perf_counter() - t0) * 1000.0
        got = hits()
        print(f"     {variant:16} tool_ok={str(bool(result.get('success'))):5} "
              f"DOM={','.join(got) or '-'} lat={ms:.0f}ms "
              f"err={str(result.get('error'))[:34]}")

    # ── E. overlay / modal ────────────────────────────────────────────────
    print("\n  E. OVERLAY — un div plein ecran au-dessus du bouton")
    for variant in VARIANTS:
        open_fresh()
        reset()
        ev("""(() => { const o=document.createElement('div');
              o.id='cov'; o.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100000';
              document.body.appendChild(o); return 1; })()""")
        t0 = time.perf_counter()
        if variant == "V1 scroll+click":
            cli("scrollintoview", "#b10")
        result = cli("click", "#b10")
        ms = (time.perf_counter() - t0) * 1000.0
        time.sleep(0.2)
        got = hits()
        print(f"     {variant:16} tool_ok={str(bool(result.get('success'))):5} "
              f"DOM={','.join(got) or '-'} lat={ms:.0f}ms")

    # ── F. latence moyenne ────────────────────────────────────────────────
    print("\n" + "═" * 100)
    print("  LATENCE MOYENNE PAR VARIANTE (cibles dans le viewport)")
    for variant in VARIANTS:
        vals = [r["latency_ms"] for r in rows
                if r["variant"] == variant and r["target"] in ("#b1", "#b5")]
        if vals:
            print(f"    {variant:16} {statistics.mean(vals):7.1f} ms  (n={len(vals)})")

    print("\n  TAUX DE CLIC RECU PAR LA CIBLE")
    for variant in VARIANTS:
        sub = [r for r in rows if r["variant"] == variant]
        ok = sum(1 for r in sub if r["hit_ok"])
        print(f"    {variant:16} {ok}/{len(sub)}")

    Path("/tmp/h2_008b_compare.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n  JSON -> /tmp/h2_008b_compare.json")
    print("═" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
