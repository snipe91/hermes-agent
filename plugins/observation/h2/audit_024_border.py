#!/usr/bin/env python3
"""H2.0-024 — border audit of the label inference. READ-ONLY, no code change.

Answers one question: is the current inference complete enough for the labels
actually present in the benches, or does it still leave clearly recoverable
false FAILED?

Sources: the three bench pages (real labels) + the recorded FAILED rows from
H2.0-020 and H2.0-023 (obstacle, expectation, observation excerpt).
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
    intent_from_label,
)

PAGES = [
    ROOT / "plugins/observation/h2/h2_bench_page.html",
    ROOT / "plugins/observation/h2/h2_coverage_page.html",
    ROOT / "plugins/observation/h2/h2_click_page.html",
]


def labels_from(path: Path) -> list[str]:
    if not path.exists():
        return []
    html = path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"<button[^>]*>(.*?)</button>", html, re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = " ".join(text.split())
        if text:
            out.append(text)
    return out


def classify(label: str) -> tuple[str, str]:
    """(verdict, explanation)."""
    lowered = label.lower()
    has_verb = any(v in lowered for v in _APPEARANCE_VERBS)
    matched = [
        cat for cat, objs in _APPEARANCE_OBJECTS.items()
        if any(o in lowered for o in objs)
    ]
    inferred = _infer_appearing(label)
    if inferred:
        return "INFÈRE", inferred
    if has_verb and not matched:
        # A verb is present but no object matched. Distinguish "object exists in
        # the label but outside our vocabulary" from "no object at all".
        return "VERBE SANS OBJET CATÉGORISABLE", ""
    if not has_verb:
        return "PAS DE VERBE D'APPARITION", ""
    return "?", ""


def main() -> int:
    all_labels: list[tuple[str, str]] = []
    for page in PAGES:
        for label in labels_from(page):
            all_labels.append((page.name, label))

    print("═" * 78)
    print("1. TOUS LES LIBELLÉS RENCONTRÉS DANS LES TROIS BANCS")
    print("═" * 78)
    seen: set[str] = set()
    counts = {"INFÈRE": 0, "VERBE SANS OBJET CATÉGORISABLE": 0, "PAS DE VERBE D'APPARITION": 0}
    for page, label in all_labels:
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        verdict, extra = classify(label)
        counts[verdict] = counts.get(verdict, 0) + 1
        exp, _h, _s = intent_from_label(label)
        cat = getattr(exp, "expect_appearing", None) if exp else "—"
        print(f"  {verdict:<32} {label:<34} → {cat}")
    print()
    print(f"  TOTAL libellés distincts : {len(seen)}")
    for k, v in counts.items():
        print(f"    {k:<34} {v}")

    print()
    print("═" * 78)
    print("2. FAILED ENREGISTRÉS — H2.0-023 puis H2.0-020")
    print("═" * 78)
    for tag, path in (
        ("023", "/tmp/h2_020_wide.json"),
        ("020", "/tmp/h2_020_wide_BEFORE.json"),
    ):
        p = Path(path)
        if not p.exists():
            print(f"  ({tag}) fichier absent")
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))["rows"]
        failed = [r for r in rows if r["final_verdict"] == "failed"]
        print(f"\n  ── H2.0-{tag} : {len(failed)} FAILED ──")
        for r in failed:
            exp = str(r.get("expected") or "")
            cat = None
            # the expectation description carries the label
            m = re.search(r"via '(.+?)'", exp)
            if m:
                cat = _infer_appearing(m.group(1))
            print(f"    {r['target']:<5} obstacle={str(r.get('obstacle')):<9} "
                  f"attendu={cat}  {exp[:46]}")
            exc = r.get("observation_excerpt")
            if exc:
                print(f"          obs: {str(exc)[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
