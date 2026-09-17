#!/usr/bin/env python3
"""H2.0-020 — wide benchmark + stability repetitions.

Replicates the middleware chain exactly (observer → verify_action →
escalate_unknown) but records what the ledger does not keep: the raw analysis
text and the extracted obstacle, per case.

Usage:
    python bench_020.py wide        # ~50 clicks, full verdict distribution
    python bench_020.py stability   # @e5/@e9/@e13 x5, phrasing variability

Read-only: no config change, no state.db write, no production edit.
"""

from __future__ import annotations

import json
import re
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import tools.browser_tool as bt  # noqa: E402
from agent.perception.browser_observer import BrowserObserver  # noqa: E402
from agent.perception.intent import build_intent  # noqa: E402
from agent.perception.vision_escalation import (  # noqa: E402
    EscalationPolicy,
    RiskLevel,
    escalate_unknown,
)
from agent.verification.action_verifier import verify_action  # noqa: E402

BASE = (Path(__file__).resolve().parent / "h2_bench_page.html").as_uri()
TASK = "bench020"


def refs_of() -> list[str]:
    """The snapshot text carries the refs inline: ``[ref=e5]``."""
    snap = json.loads(bt.browser_snapshot(full=True, task_id=TASK))
    return re.findall(r"\[ref=(e\d+)\]", snap.get("snapshot") or "")


def snapshot_text() -> str:
    snap = json.loads(bt.browser_snapshot(full=True, task_id=TASK))
    return snap.get("snapshot") or ""


def run_one(target: str, observer: BrowserObserver) -> dict:
    """One click, full chain, everything recorded."""
    snap_txt = snapshot_text()
    inferred = build_intent(
        "browser_click", {"ref": target},
        snapshot_text=snap_txt, risk_level="medium",
    )
    expected = inferred.expected_transition

    before = observer.capture()
    t0 = time.perf_counter()
    raw = bt.browser_click(target, task_id=TASK)
    action_ms = (time.perf_counter() - t0) * 1000.0
    after = observer.capture()

    success = '"success": true' in str(raw)
    row: dict = {
        "target": target,
        "tool_reported_success": success,
        "expected": getattr(expected, "description", None),
        "action_ms": round(action_ms, 1),
        "state_changed": bool(before.url != after.url or before.element_count != after.element_count),
    }

    ev = verify_action(
        before=before, after=after, expected=expected,
        tool_name="browser_click", tool_args={"ref": target},
        tool_success=success, task_id=TASK,
    )
    row["initial_verdict"] = ev.outcome.value
    row["unknown_reason"] = getattr(ev, "unknown_reason", "none") or "none"

    if ev.outcome.value == "unknown":
        t1 = time.perf_counter()
        ev2, obs, _decision = escalate_unknown(
            evidence=ev, risk=RiskLevel.MEDIUM, expected=expected,
            policy=EscalationPolicy(), task_id=TASK,
        )
        row["vision_ms"] = round((time.perf_counter() - t1) * 1000.0, 1)
        row["escalated"] = True
        if obs is not None:
            row["obstacle"] = obs.obstacle
            row["source"] = obs.source
            row["observation_excerpt"] = obs.observation[:260].replace("\n", " ")
        row["final_verdict"] = ev2.outcome.value
    else:
        row["escalated"] = False
        row["final_verdict"] = ev.outcome.value

    return row


def summarise(rows: list[dict]) -> dict:
    def count(key, val):
        return sum(1 for r in rows if r.get(key) == val)

    verdicts = {}
    for r in rows:
        verdicts[r["final_verdict"]] = verdicts.get(r["final_verdict"], 0) + 1
    escalated = [r for r in rows if r.get("escalated")]
    vl = [r["vision_ms"] for r in escalated if r.get("vision_ms")]
    obstacles = {}
    for r in escalated:
        o = r.get("obstacle")
        obstacles[str(o)] = obstacles.get(str(o), 0) + 1
    false_failed = [
        r for r in rows
        if r["final_verdict"] == "failed" and r.get("obstacle") is None
    ]
    return {
        "n": len(rows),
        "verdicts": verdicts,
        "escalated": len(escalated),
        "vision_latency_mean_ms": round(st.mean(vl), 0) if vl else None,
        "obstacles_extracted": obstacles,
        "failed_without_obstacle": len(false_failed),
        "unknown_reasons": {
            k: count("unknown_reason", k)
            for k in {r.get("unknown_reason") for r in rows}
        },
    }


def wide() -> int:
    bt.browser_navigate(BASE, task_id=TASK)
    time.sleep(0.6)
    refs = refs_of()
    print(f"  refs : {len(refs)}")
    observer = BrowserObserver(task_id=TASK)

    rows = []
    for i in range(50):
        row = run_one(refs[i % len(refs)], observer)
        rows.append(row)
        if (i + 1) % 10 == 0:
            print(f"  ... {i + 1}/50")

    out = summarise(rows)
    Path("/tmp/h2_020_wide.json").write_text(
        json.dumps({"rows": rows, "summary": out}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("\n  ── RÉSUMÉ ──")
    print(f"  n={out['n']} · verdicts={out['verdicts']}")
    print(f"  escalades={out['escalated']} · vision moy={out['vision_latency_mean_ms']} ms")
    print(f"  obstacles extraits : {out['obstacles_extracted']}")
    print(f"  FAILED sans obstacle (faux FAILED) : {out['failed_without_obstacle']}")
    print(f"  raisons UNKNOWN : {out['unknown_reasons']}")
    return 0


def stability() -> int:
    targets = ["@e5", "@e9", "@e13"]
    reps = 5
    rows = []
    for t in targets:
        for r in range(reps):
            bt.browser_navigate(BASE, task_id=TASK)
            time.sleep(0.45)
            bt._run_browser_command(TASK, "scrollintoview", [t], timeout=15)
            observer = BrowserObserver(task_id=TASK)
            row = run_one(t, observer)
            row["rep"] = r + 1
            rows.append(row)
            print(f"  {t} rep{r + 1} : obstacle={row.get('obstacle')!r} "
                  f"verdict={row['final_verdict']} "
                  f"success={row['tool_reported_success']}")

    Path("/tmp/h2_020_stability.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n  ── STABILITÉ ──")
    for t in targets:
        sub = [r for r in rows if r["target"] == t]
        ob = [str(r.get("obstacle")) for r in sub]
        vd = [r["final_verdict"] for r in sub]
        print(f"  {t} : obstacles={ob}")
        print(f"       verdicts={vd} · FAILED={vd.count('failed')}/{len(vd)}")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "wide"
    raise SystemExit(wide() if mode == "wide" else stability())
