#!/usr/bin/env python3
"""H2.0-007 — investigate `state_changed = 0/50` on real clicks.

Clicks each known-case button exactly ONCE (so nothing is idempotent) and
records the resulting WorldState diff. Prints a table so we can see whether the
diff is blind, or whether the earlier run was simply clicking dead elements.

No code is modified by this script — it only observes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.setdefault("HERMES_BROWSER_ACTION_VERIFICATION", "observe")

from agent.perception.browser_observer import BrowserObserver  # noqa: E402
from agent.perception.state_diff import diff_world_states  # noqa: E402
from tools import browser_tool as bt  # noqa: E402

TASK = "h2invest"
PAGE = (Path(__file__).resolve().parent / "h2_bench_page.html").as_uri()

# Each case: (label, button ref, what a human would expect to happen)
CASES = [
    ("A dropdown/text", "@e3", "texte de statut change"),
    ("B menu React", "@e5", "3 éléments <li> apparaissent"),
    ("C modal", "@e7", "role=dialog apparaît"),
    ("D overlay", "@e9", "role=alert apparaît"),
    ("E DOM mutation", "@e11", "un div.item apparaît"),
    ("F scroll", "@e13", "pas de changement DOM attendu"),
    ("G inerte", "@e15", "AUCUN changement attendu"),
    ("H mutation différée", "@e17", "contenu apparaît après 1,2 s"),
    ("I loading", "@e19", "texte 'Chargement…' puis 'terminée'"),
    ("J visuel seul", "@e21", "couleur change, DOM identique"),
]


def main() -> int:
    bt.browser_navigate(url=PAGE, task_id=TASK)
    observer = BrowserObserver(task_id=TASK)

    print(
        f"{'cas':22} {'elems':>6} {'hash av':>10} {'hash ap':>10} "
        f"{'changed':>8} {'elemΔ':>6} {'urlΔ':>5} {'obst':>5}"
    )
    print("─" * 88)

    changed_count = 0
    for label, ref, _expect in CASES:
        before = observer.capture()
        out = bt.browser_click(ref, task_id=TASK)
        if 'success": false' in (out or ""):
            print(f"{label:22} CLIC ÉCHOUÉ  {out[:60]}")
            continue
        # Delayed cases need time to settle.
        if "différée" in label or "loading" in label:
            import time

            time.sleep(1.6)
        after = observer.capture()
        d = diff_world_states(before, after)

        hb = (before.structural_hash or "")[:8]
        ha = (after.structural_hash or "")[:8]
        elemd = (after.element_count or 0) - (before.element_count or 0)
        obstacles = d.dialogs_opened + d.overlays_added + d.errors_added

        print(
            f"{label:22} {before.element_count or 0:>3}/{after.element_count or 0:<3} "
            f"{hb:>10} {ha:>10} {str(d.changed):>8} {elemd:>+6} "
            f"{str(d.url_changed):>5} {obstacles:>5}"
        )
        if d.changed:
            changed_count += 1

    print("─" * 88)
    print(f"CAS AVEC CHANGEMENT DÉTECTÉ : {changed_count}/{len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
