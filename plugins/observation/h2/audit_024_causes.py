#!/usr/bin/env python3
"""H2.0-024 (suite) — classify every label and every FAILED precisely.

READ-ONLY. Distinguishes:
  · labels naming a categorisable object but escaping the appearance-verb list
  · FAILED where the expected category WAS observed but not exempted
  · FAILED from a genuinely unexpected obstacle
  · FAILED with no intent available
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent.perception.intent import (  # noqa: E402
    _APPEARANCE_OBJECTS,
    _APPEARANCE_VERBS,
    _infer_appearing,
)
from agent.perception.vision_escalation import obstacle_category  # noqa: E402

PAGES = [
    ROOT / "plugins/observation/h2/h2_bench_page.html",
    ROOT / "plugins/observation/h2/h2_coverage_page.html",
    ROOT / "plugins/observation/h2/h2_click_page.html",
]
VERBS_OTHER = (
    "basculer", "toggle", "planifier", "schedule", "changer", "change",
    "avancer", "incrementer", "incrémenter", "ouvrir la section",
)


def labels() -> list[str]:
    out: list[str] = []
    for path in PAGES:
        if not path.exists():
            continue
        for m in re.finditer(r"<button[^>]*>(.*?)</button>", path.read_text(encoding="utf-8"), re.DOTALL | re.IGNORECASE):
            text = " ".join(re.sub(r"<[^>]+>", "", m.group(1)).split())
            if text and text.lower() not in {x.lower() for x in out}:
                out.append(text)
    return out


def main() -> int:
    print("=" * 78)
    print("3. LIBELLÉS NOMMANT UN OBJET CATÉGORISABLE MAIS ÉCHAPPANT AU VOCABULAIRE")
    print("=" * 78)
    escaped: list[tuple[str, str, str]] = []
    for label in labels():
        lowered = label.lower()
        objs = [c for c, words in _APPEARANCE_OBJECTS.items() if any(w in lowered for w in words)]
        has_app_verb = any(v in lowered for v in _APPEARANCE_VERBS)
        if objs and not has_app_verb:
            other = [v for v in VERBS_OTHER if v in lowered]
            escaped.append((label, objs[0], other[0] if other else "?"))
    if not escaped:
        print("  AUCUN.")
    for label, cat, verb in escaped:
        print(f"  {label:<26} objet catégorisable = {cat:<9} verbe = {verb:<10} → inféré: {_infer_appearing(label)}")

    print()
    print("=" * 78)
    print("5. CLASSEMENT DE CHAQUE FAILED PAR CAUSE")
    print("=" * 78)
    for tag, path in (("023", "/tmp/h2_020_wide.json"), ("020", "/tmp/h2_020_wide_BEFORE.json")):
        p = Path(path)
        if not p.exists():
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))["rows"]
        print(f"\n  ── H2.0-{tag} ──")
        causes = {"attendu_observe_non_exempte": 0, "inattendu": 0, "sans_intention": 0, "autre": 0}
        for r in rows:
            if r["final_verdict"] != "failed":
                continue
            m = re.search(r"via '(.+?)'", str(r.get("expected") or ""))
            inferred = _infer_appearing(m.group(1)) if m else None
            observed = obstacle_category(r.get("obstacle"))
            if inferred and observed == inferred:
                cause = "attendu_observe_non_exempte"
            elif inferred and observed and observed != inferred:
                cause = "inattendu"
            elif not inferred:
                cause = "sans_intention"
            else:
                cause = "autre"
            causes[cause] += 1
            print(f"    {r['target']:<5} inféré={str(inferred):<8} observé={str(observed):<9} → {cause}")
        print(f"    BILAN : {causes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
