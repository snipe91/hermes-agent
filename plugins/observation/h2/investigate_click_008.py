#!/usr/bin/env python3
"""H2.0-008 — why do some browser_click calls never reach the page?

Ground truth is the DOM itself: ``window.__hits`` is appended by a capture-phase
click listener, so a click only counts as "executed" if the page observed it.
``{"success": true}`` from the tool is NOT evidence and is compared against it.

This script investigates ONLY. It changes nothing in production, adds no
perception layer, and touches neither the verifier, the middleware, nor
browser_vision.

Tests:
  T1  10 different buttons, fresh page each
  T2  same button 10 times, one page
  T3  snapshot before each click
  T4  scrollIntoView() before click
  T5  fresh page for each click (explicit)
  T6  reference click by @ref instead of CSS selector
"""

from __future__ import annotations

import json
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

#: The failing element from H2.0-007 (a button far down the page).
FAR = "#b10"
NEAR = "#b1"


class Browser:
    """Thin wrapper so each trial gets its own task/session when needed."""

    def __init__(self, task: str) -> None:
        self.task = task

    def open(self, fresh: bool) -> None:
        url = f"{BASE}?t={time.time_ns()}" if fresh else BASE
        _run_browser_command(self.task, "open", [url], timeout=45)
        time.sleep(0.35)

    def eval(self, js: str):
        result = _run_browser_command(self.task, "eval", [js], timeout=25)
        data = result.get("data") or {}
        return data.get("result") if isinstance(data, dict) else None

    def reset(self) -> None:
        self.eval("window.__reset()")

    def hits(self) -> list[str]:
        raw = self.eval("JSON.stringify(window.__hits || [])")
        try:
            return json.loads(raw) if isinstance(raw, str) else []
        except Exception:
            return []

    def probe(self, sel: str) -> dict:
        raw = self.eval(f"window.__probe({json.dumps(sel)})")
        try:
            return json.loads(raw) if isinstance(raw, str) else {}
        except Exception:
            return {}

    def click_css(self, sel: str) -> dict:
        return _run_browser_command(self.task, "click", [sel], timeout=25)

    def click_ref(self, ref: str) -> dict:
        return _run_browser_command(self.task, "click", [ref], timeout=25)

    def snapshot(self) -> str:
        return browser_snapshot(full=True, task_id=self.task)


ROWS: list[dict] = []


def record(
    test: str,
    target: str,
    tool_success: bool,
    received: str,
    probe: dict,
    note: str = "",
) -> None:
    """Collect one matrix row."""
    center = probe.get("center") or {}
    viewport = probe.get("viewport") or {}
    scroll = probe.get("scroll") or {}
    rows = {
        "test": test,
        "target": target,
        "tool_success": tool_success,
        "dom": received,
        "coords": f"{center.get('x')},{center.get('y')}",
        "viewport": f"{viewport.get('w')}x{viewport.get('h')}",
        "scroll": f"{scroll.get('x')},{scroll.get('y')}",
        "at_point": probe.get("elementFromPoint"),
        "in_vp": probe.get("inViewport"),
        "disp": probe.get("display"),
        "vis": probe.get("visibility"),
        "pe": probe.get("pointerEvents"),
        "note": note,
    }
    ROWS.append(rows)


# ── T1: 10 different buttons, fresh page each ─────────────────────────────
def t1() -> None:
    print("  T1 — 10 boutons differents, page fraiche", flush=True)
    browser = Browser("h2008_t1")
    for i in range(1, 11):
        sel = f"#b{i}"
        browser.open(fresh=True)
        browser.reset()
        probe = browser.probe(sel)
        result = browser.click_css(sel)
        time.sleep(0.25)
        hits = browser.hits()
        record("T1", sel, bool(result.get("success")), ",".join(hits) or "-", probe)


# ── T2: same button 10 times, one page ────────────────────────────────────
def t2() -> None:
    print("  T2 — meme bouton 10 fois, une page", flush=True)
    browser = Browser("h2008_t2")
    browser.open(fresh=True)
    browser.reset()
    probe = browser.probe(NEAR)
    for _ in range(10):
        result = browser.click_css(NEAR)
        time.sleep(0.15)
        hits = browser.hits()
        record("T2", NEAR, bool(result.get("success")), f"{len(hits)} clics", probe)


# ── T3: snapshot before each click ────────────────────────────────────────
def t3() -> None:
    print("  T3 — snapshot avant chaque clic (10 refs)", flush=True)
    browser = Browser("h2008_t3")
    browser.open(fresh=True)
    browser.reset()
    refs = ["@e3", "@e4", "@e5", "@e6", "@e7", "@e8", "@e9", "@e10", "@e11", "@e12"]
    for ref in refs:
        browser.snapshot()
        browser.reset()
        probe = browser.probe(NEAR)
        result = browser.click_ref(ref)
        time.sleep(0.2)
        hits = browser.hits()
        record("T3", ref, bool(result.get("success")), ",".join(hits) or "-", probe)


# ── T4: scrollIntoView before click ───────────────────────────────────────
def t4() -> None:
    print("  T4 — scrollIntoView() avant clic", flush=True)
    browser = Browser("h2008_t4")
    for i in (1, 5, 10):
        sel = f"#b{i}"
        browser.open(fresh=True)
        browser.reset()
        probe_before = browser.probe(sel)
        browser.eval(f"document.querySelector('{sel}').scrollIntoView({{block:'center'}})")
        time.sleep(0.3)
        probe_after = browser.probe(sel)
        result = browser.click_css(sel)
        time.sleep(0.25)
        hits = browser.hits()
        record(
            "T4",
            sel,
            bool(result.get("success")),
            ",".join(hits) or "-",
            probe_after,
            note=f"avant: in_vp={probe_before.get('inViewport')} scroll={probe_before.get('scroll', {}).get('y')}",
        )


# ── T5: fresh page for each click, far element only ───────────────────────
def t5() -> None:
    print("  T5 — page fraiche par clic, element bas de page", flush=True)
    browser = Browser("h2008_t5")
    for i in range(3):
        browser.open(fresh=True)
        browser.reset()
        probe = browser.probe(FAR)
        result = browser.click_css(FAR)
        time.sleep(0.25)
        hits = browser.hits()
        record("T5", FAR, bool(result.get("success")), ",".join(hits) or "-", probe,
               note=f"essai {i + 1}")


# ── T6: wrapper path (browser_click) on a far element ─────────────────────
def t6() -> None:
    print("  T6 — browser_click() sur element bas de page", flush=True)
    browser = Browser("h2008_t6")
    for i in range(3):
        browser.open(fresh=True)
        browser.reset()
        browser.snapshot()
        probe = browser.probe(FAR)
        raw = browser_click("@e12", task_id=browser.task)
        time.sleep(0.25)
        hits = browser.hits()
        record("T6", "@e12", '"success": true' in str(raw), ",".join(hits) or "-", probe)


def main() -> int:
    _run_browser_command("h2008_t1", "open", [BASE], timeout=45)
    t1()
    t2()
    t3()
    t4()
    t5()
    t6()

    print("\n" + "═" * 132)
    print("  MATRICE H2.0-008 — browser_click : succes outil vs clic DOM reel")
    print("═" * 132)
    head = ("test", "cible", "tool_ok", "DOM_recu", "coords", "viewport", "scroll",
            "at_point", "in_vp", "disp", "vis", "pe")
    widths = (5, 7, 7, 11, 11, 10, 10, 10, 6, 7, 8, 8)
    print("  " + " ".join(h.ljust(w) for h, w in zip(head, widths)))
    print("  " + "─" * 126)
    for r in ROWS:
        vals = (
            r["test"], r["target"], str(r["tool_success"])[:5], r["dom"][:11],
            r["coords"], r["viewport"], r["scroll"], str(r["at_point"])[:10],
            str(r["in_vp"])[:5], r["disp"][:7], r["vis"][:8], r["pe"][:8],
        )
        print("  " + " ".join(str(v).ljust(w) for v, w in zip(vals, widths)))
        if r["note"]:
            print(f"        ↳ {r['note']}")

    # ── verdict ───────────────────────────────────────────────────────────
    print("\n" + "─" * 132)
    all_ok = [r for r in ROWS if r["tool_success"]]
    dom_ok = [r for r in ROWS if r["dom"] not in ("-", "") and not r["dom"].startswith("0 ")]
    print(f"  appels dont tool_success=True .......... {len(all_ok)}/{len(ROWS)}")
    print(f"  appels dont le DOM a recu le clic ...... {len(dom_ok)}/{len(ROWS)}")
    print(f"  ECART (tool dit oui, DOM dit non) ...... {len(all_ok) - len(dom_ok)}")

    by_test: dict[str, list[bool]] = {}
    for r in ROWS:
        got = r["dom"] not in ("-", "")
        by_test.setdefault(r["test"], []).append(got)
    print("\n  TAUX DE CLIC REEL PAR TEST :")
    for test, got in sorted(by_test.items()):
        print(f"    {test} : {sum(got)}/{len(got)}")
    print("═" * 132)
    Path("/tmp/h2_008_matrix.json").write_text(
        json.dumps(ROWS, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("  matrice JSON -> /tmp/h2_008_matrix.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
