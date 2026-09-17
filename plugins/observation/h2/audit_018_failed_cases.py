#!/usr/bin/env python3
"""H2.0-018 — reconstruct the FAILED cases from the ledger.

Full dossier for one case: expectation handed to the verifier, the exact text
DeepSeek returned, the parsed obstacle, and the judge's decision + reasons.

Read-only: no production file changes, no config change, no state.db write.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import tools.browser_tool as bt  # noqa: E402
from agent.perception import vision_escalation as ve  # noqa: E402
from agent.perception.browser_observer import BrowserObserver  # noqa: E402
from agent.perception.intent import build_intent  # noqa: E402

BASE = (Path(__file__).resolve().parent / "h2_bench_page.html").as_uri()
TASK = "audit018"

# The three distinct FAILED targets from the ledger: @e5, @e9, @e13
TARGETS = ["@e5", "@e9", "@e13"]


def dossier(target: str) -> dict:
    """Reconstruct one click's full chain and return the dossier."""
    bt.browser_navigate(BASE, task_id=TASK)
    time.sleep(0.5)

    snap = json.loads(bt.browser_snapshot(full=True, task_id=TASK))
    snapshot_text = snap.get("snapshot") or ""
    refs = snap.get("refs") or {}
    label = refs.get(target.lstrip("@")) or refs.get(target) or "?"

    observer = BrowserObserver(task_id=TASK)
    before = observer.capture()

    # the exact expectation H2.0 infers for this click
    inferred = build_intent(
        "browser_click", {"ref": target},
        snapshot_text=snapshot_text, risk_level="medium",
    )
    expected = inferred.expected_transition

    raw = bt.browser_click(target, task_id=TASK)
    time.sleep(0.35)
    after = observer.capture()

    obs = ve.observe_with_vision(
        question=ve._default_question(expected), task_id=TASK
    )

    outcome = reasons = None
    if expected is not None:
        outcome, reasons = ve.judge_observation(observation=obs, expected=expected)

    return {
        "target": target,
        "label": label,
        "click_raw": str(raw)[:90],
        "expected": expected,
        "expected_desc": getattr(expected, "description", None),
        "expect_no_obstacles": getattr(expected, "expect_no_obstacles", None),
        "before_count": before.element_count,
        "after_count": after.element_count,
        "url_changed": before.url != after.url,
        "observation": obs,
        "outcome": outcome,
        "reasons": reasons,
    }


def main() -> int:
    dossiers = []
    for t in TARGETS:
        print("=" * 92)
        d = dossier(t)
        dossiers.append(d)
        print(f"  CAS {d['target']}  label={d['label']!r}")
        print(f"  clic brut        : {d['click_raw']}")
        print(f"  expected         : {d['expected']}")
        print(f"    description    : {d['expected_desc']!r}")
        print(f"    no_obstacles   : {d['expect_no_obstacles']}")
        print(f"  before/after     : {d['before_count']} -> {d['after_count']} "
              f"· url_changed={d['url_changed']}")
        obs = d["observation"]
        print(f"  observation      : source={obs.source} obstacle={obs.obstacle!r} "
              f"conf={obs.confidence} available={obs.available}")
        print(f"  TEXTE (extrait)  : {obs.observation[:420].replace(chr(10), ' ')}")
        print(f"  JUDGE            : {d['outcome']}")
        print(f"  REASONS          : {d['reasons']}")

    Path("/tmp/h2_018_dossiers.json").write_text(
        json.dumps(
            [{k: (str(v) if k == "observation" else v) for k, v in d.items()}
             for d in dossiers],
            ensure_ascii=False, indent=1, default=str,
        ),
        encoding="utf-8",
    )
    print("\n  JSON -> /tmp/h2_018_dossiers.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
