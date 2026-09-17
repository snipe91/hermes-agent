#!/usr/bin/env python3
"""H2.0-010 — determine the MINIMUM synchronisation needed before the AFTER snapshot.

No arbitrary 300 ms: we look for the smallest delay (or condition) at which the
effect of a click is reliably observable.

Case 1 — synchronous mutation  : is it visible at 0 ms?
Case 2 — deferred mutation     : setTimeout(800 ms) inside the page
Case 3 — condition-based wait  : can `wait --fn "<js>"` replace a fixed delay?
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

BASE = (Path(__file__).resolve().parent / "h2_click_page.html").as_uri()
BIN = "/Users/snipe91/.npm-global/bin/agent-browser"


def sh(*args: str, session: str = "syn"):
    return subprocess.run(
        [BIN, *args, "--session", session],
        capture_output=True, text=True, timeout=90,
    )


def out(result) -> str:
    return (result.stdout or "").strip()[:40]


def main() -> int:
    print("=" * 78)
    print("  H2.0-010 — SYNCHRONISATION MINIMALE AVANT LE SNAPSHOT AFTER")
    print("=" * 78)

    print("\n  CAS 1 — mutation SYNCHRONE (#b1) : visible a quel delai ?")
    for delay_ms in (0, 10, 25, 50, 100, 200):
        sh("open", f"{BASE}?c1={delay_ms}")
        time.sleep(0.35)
        sh("eval", "window.__reset()")
        sh("scrollintoview", "#b1")
        sh("click", "#b1")
        if delay_ms:
            time.sleep(delay_ms / 1000.0)
        r = sh("eval", "JSON.stringify(window.__hits||[])")
        print(f"    {delay_ms:5d} ms -> {out(r)}")

    print("\n  CAS 2 — mutation DIFFEREE (#h-btn, setTimeout 800 ms) AVEC scroll")
    for delay_ms in (0, 100, 300, 500, 700, 900, 1100):
        sh("open", f"{BASE}?c2={delay_ms}")
        time.sleep(0.35)
        sh("scrollintoview", "#h-btn")
        sh("click", "#h-btn")
        if delay_ms:
            time.sleep(delay_ms / 1000.0)
        r = sh("eval", "document.querySelectorAll('#h-out p').length")
        print(f"    {delay_ms:5d} ms -> {out(r)} element(s)")

    print("\n  CAS 3 — attente par CONDITION (wait --fn) sur mutation differee")
    sh("open", f"{BASE}?c3=1")
    time.sleep(0.35)
    sh("scrollintoview", "#h-btn")
    t0 = time.perf_counter()
    sh("click", "#h-btn")
    r = sh("wait", "--fn", "document.querySelectorAll('#h-out p').length > 0")
    ms = (time.perf_counter() - t0) * 1000.0
    print(f"    click + wait --fn -> retour={r.returncode} en {ms:.0f} ms")
    r2 = sh("eval", "document.querySelectorAll('#h-out p').length")
    print(f"    elements presents apres wait : {out(r2)}")

    print("\n  CAS 4 — plancher de wait --fn sur condition deja vraie")
    t0 = time.perf_counter()
    r3 = sh("wait", "--fn", 'document.readyState === "complete"')
    print(f"    wait --fn (immediat) -> retour={r3.returncode} "
          f"en {(time.perf_counter() - t0) * 1000.0:.0f} ms")

    print("\n" + "=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
