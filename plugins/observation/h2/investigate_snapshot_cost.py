#!/usr/bin/env python3
"""H2.0-009 — where does the ~401 ms snapshot-AFTER actually go?

Purely investigative. No production file is touched, no optimisation is
applied, and window.__hit is used ONLY as a benchmark instrument.

Method
------
The CLI is a native binary that talks to a daemon over IPC. So the cost of any
command is:

    fixed   = process launch + IPC + daemon round-trip
    variable = the command's own work (CDP query, serialisation, ref table)

To separate them we time a command that does almost nothing (`get url`) against
the snapshot variants. The delta is the snapshot's own cost.

Measured
--------
  get url                minimal command  -> the fixed floor
  get title              minimal command  -> cross-check the floor
  snapshot -c            compact snapshot
  snapshot               full snapshot     <- what H2.0 uses for AFTER
  eval "<tiny js>"       JS round-trip
  eval "<innerText>"     JS round-trip with real payload
  eval "<structure>"     JS round-trip with bigger payload
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
TASK = "h2009"
N = 15

CMDS: list[tuple[str, list[str]]] = [
    ("get url          (minimal)",  ["get", "url"]),
    ("get title        (minimal)",  ["get", "title"]),
    ("eval '1'         (minimal)",  ["eval", "1"]),
    ("snapshot -c      (compact)",  ["snapshot", "-c"]),
    ("snapshot         (FULL)",     ["snapshot"]),
    ("eval innerText",              ["eval", "(() => (document.body.innerText || '').length)()"]),
    ("eval structure",              ["eval", "(() => document.body.querySelectorAll('*').length)()"]),
]


def timeit(command: str, args: list[str]) -> tuple[float, int]:
    """Return (elapsed_ms, payload_bytes)."""
    t0 = time.perf_counter()
    result = _run_browser_command(TASK, command, args, timeout=25)
    ms = (time.perf_counter() - t0) * 1000.0
    try:
        size = len(json.dumps(result.get("data", result), default=str, ensure_ascii=False))
    except Exception:
        size = 0
    return ms, size


def main() -> int:
    _run_browser_command(TASK, "open", [f"{BASE}?i=1"], timeout=45)
    time.sleep(0.5)

    print("═" * 92)
    print("  H2.0-009 — VENTILATION DU COÛT (même page, même session)")
    print("═" * 92)
    print(f"  {'commande':28} {'moy':>8} {'p50':>8} {'min':>8} {'max':>8} {'payload':>9}")
    print("  " + "─" * 84)

    results: dict[str, dict] = {}
    for label, args in CMDS:
        samples: list[float] = []
        sizes: list[int] = []
        for _ in range(N):
            ms, size = timeit(args[0], args[1:])
            samples.append(ms)
            sizes.append(size)
        results[label] = {
            "mean": statistics.mean(samples),
            "p50": statistics.median(samples),
            "min": min(samples),
            "max": max(samples),
            "bytes": int(statistics.mean(sizes)),
        }
        r = results[label]
        print(f"  {label:28} {r['mean']:8.1f} {r['p50']:8.1f} {r['min']:8.1f} "
              f"{r['max']:8.1f} {r['bytes']:9d}")

    # ── separation: fixed floor vs snapshot's own work ────────────────────
    floor = min(
        results["get url          (minimal)"]["mean"],
        results["get title        (minimal)"]["mean"],
    )
    full = results["snapshot         (FULL)"]["mean"]
    compact = results["snapshot -c      (compact)"]["mean"]

    print("\n" + "─" * 92)
    print("  SÉPARATION DU COÛT")
    print(f"    plancher fixe (lancement CLI + IPC + daemon) ... {floor:7.1f} ms")
    print(f"    snapshot FULL .................................. {full:7.1f} ms")
    print(f"      → part fixe .................................. {floor:7.1f} ms  "
          f"({floor / full:.0%})")
    print(f"      → part propre au snapshot .................... {full - floor:7.1f} ms  "
          f"({(full - floor) / full:.0%})")
    print(f"    snapshot COMPACT ............................... {compact:7.1f} ms")
    print(f"      → delta compact vs full ...................... {full - compact:7.1f} ms")

    # ── what the AFTER snapshot actually has to pay for ───────────────────
    print("\n" + "─" * 92)
    print("  CE QUE LE SNAPSHOT AFTER PAIE, DÉCOMPOSÉ")
    print(f"    1. lancement du binaire CLI + IPC .............. ~{floor * 0.6:6.1f} ms (estimé)")
    print(f"    2. requête CDP Accessibility.getFullAXTree ..... voir delta ci-dessous")
    print(f"    3. construction de la table de refs ............ voir delta ci-dessous")
    print(f"    4. sérialisation + transport du payload ........ "
          f"{results['snapshot         (FULL)']['bytes']:d} o")
    print(f"    part CDP + refs + sérialisation (2+3+4) ........ {full - floor:6.1f} ms")

    Path("/tmp/h2_009_costs.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n  JSON -> /tmp/h2_009_costs.json")
    print("═" * 92)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
