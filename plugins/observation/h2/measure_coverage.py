#!/usr/bin/env python3
"""H2.0 — coverage matrix: which observation source sees which change, at what cost.

For each of the 10 non-idempotent cases (A→J) this script:

    1. captures every candidate layer BEFORE the click
    2. clicks once
    3. captures every layer AFTER the click
    4. records whether that layer's value CHANGED
    5. records how long each layer took

Output: a coverage matrix (layer × case) plus per-layer mean cost.

READ-ONLY EXPERIMENT. It changes no Hermes trajectory, touches no production
path, and adds no extra hash or content to the observation pipeline. It only
*measures* what is reachable through the existing agent-browser CLI.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.browser_tool import _run_browser_command  # noqa: E402

TASK = "h2cov"
PAGE = (Path(__file__).resolve().parent / "h2_coverage_page.html").as_uri()

# Buttons in document order: @e3 is the first button on the page.
CASES = [
    ("A", "@e3", "texte compteur"),
    ("B", "@e5", "menu append"),
    ("C", "@e7", "modal toggle"),
    ("D", "@e9", "overlay alert"),
    ("E", "@e11", "DOM append"),
    ("F", "@e13", "navigation hash"),
    ("G", "@e15", "statut texte"),
    ("H", "@e17", "mutation différée"),
    ("I", "@e19", "loading state"),
    ("J", "@e21", "visuel couleur"),
]

#: JS that builds a whole-page signature from text + structure.
JS_INNERTEXT = "(() => (document.body.innerText || '').trim())()"
JS_STRUCTURE = (
    "(() => { const a=[...document.body.querySelectorAll('*')]"
    ".map(e=>e.tagName+'.'+(e.className||'')+(e.getAttribute('role')||''));"
    " return JSON.stringify({n:a.length,s:a.join('|')}); })()"
)
JS_VISUAL = (
    "(() => { const r=[...document.body.querySelectorAll('*')]"
    ".filter(e=>{const s=getComputedStyle(e);return s.display!=='none'&&s.visibility!=='hidden';})"
    ".map(e=>e.tagName+':'+getComputedStyle(e).backgroundColor);"
    " return JSON.stringify({visible:r.length, colors:r.join(',')}); })()"
)
JS_OBSTACLES = (
    "(() => { const q=(s)=>document.querySelectorAll(s).length;"
    " return JSON.stringify({dialog:q('[role=dialog]'),alert:q('[role=alert]'),"
    "modal:q('[aria-modal=true]'),overlay:q('.overlay,.modal,.popup')}); })()"
)


def _run(command: str, args: list[str], timeout: int = 20):
    """Run one agent-browser command; return (payload, elapsed_ms)."""
    t0 = time.perf_counter()
    try:
        result = _run_browser_command(TASK, command, args, timeout=timeout)
    except Exception as exc:
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    return result, (time.perf_counter() - t0) * 1000.0


def _digest(result: dict) -> str:
    """Stable signature of whatever a layer returned."""
    try:
        data = result.get("data")
        if data is None:
            data = result
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()[:16]
    except Exception:
        return "err"


#: layer name -> (command, args)
LAYERS: dict[str, tuple[str, list[str]]] = {
    "snapshot -c ": ("snapshot", ["-c"]),
    "snapshot full": ("snapshot", []),
    "get text body": ("get", ["text", "body"]),
    "get html body": ("get", ["html", "body"]),
    "get url      ": ("get", ["url"]),
    "eval innerText": ("eval", [JS_INNERTEXT]),
    "eval structure": ("eval", [JS_STRUCTURE]),
    "eval visual   ": ("eval", [JS_VISUAL]),
    "eval obstacles": ("eval", [JS_OBSTACLES]),
}


def capture_all() -> tuple[dict[str, str], dict[str, float], dict[str, bool]]:
    """Capture every layer; return (digest, elapsed_ms, ok) per layer."""
    digests: dict[str, str] = {}
    times: dict[str, float] = {}
    oks: dict[str, bool] = {}
    for name, (command, args) in LAYERS.items():
        result, ms = _run(command, args)
        digests[name] = _digest(result)
        times[name] = ms
        oks[name] = bool(result.get("success", True))
    return digests, times, oks


def main() -> int:
    # Navigate once, then let the page settle.
    _run("open", [PAGE], timeout=40)
    time.sleep(0.4)

    baseline_times: dict[str, list[float]] = {k: [] for k in LAYERS}
    coverage: dict[str, dict[str, bool]] = {k: {} for k in LAYERS}
    ok_counts: dict[str, int] = {k: 0 for k in LAYERS}

    for label, ref, description in CASES:
        before, t_before, ok_before = capture_all()
        _run("click", [ref])
        if label in {"H", "I"}:
            time.sleep(1.5)  # let delayed mutations land
        else:
            time.sleep(0.15)
        # Case C toggles a modal OPEN, and an open modal swallows every
        # subsequent click — which is exactly what made the first pass of this
        # measurement report 3/10 for every layer. Close it again so D→J are
        # genuinely reachable.
        if label == "C":
            time.sleep(0.15)
            _run("click", [ref])
            time.sleep(0.15)
        if label == "D":
            # Same reasoning: the alert banner is toggled off so it does not
            # linger over the remaining cases.
            time.sleep(0.15)
            _run("click", [ref])
            time.sleep(0.15)
        after, t_after, ok_after = capture_all()

        for name in LAYERS:
            changed = before[name] != after[name]
            coverage[name][label] = changed
            baseline_times[name].append(t_before[name])
            if ok_before[name] and ok_after[name]:
                ok_counts[name] += 1
        print(f"  {label} {description:18} mesuré", flush=True)

    # ── coverage matrix ───────────────────────────────────────────────────
    letters = [c[0] for c in CASES]
    width = max(len(n) for n in LAYERS)

    print("\n" + "═" * 78)
    print("  MATRICE DE COUVERTURE — ● détecté   · aveugle")
    print("═" * 78)
    header = "  " + "couche".ljust(width) + " │ " + " ".join(letters) + " │ couv. │ coût"
    print(header)
    print("  " + "─" * (width + 2) + "┼" + "─" * (len(letters) * 2 + 1) + "┼───────┼────────")

    for name, _spec in LAYERS.items():
        marks = "  ".join("●" if coverage[name][l] else "·" for l in letters)
        hits = sum(1 for l in letters if coverage[name][l])
        ms = sum(baseline_times[name]) / max(len(baseline_times[name]), 1)
        print(f"  {name.ljust(width)} │ {marks}  │  {hits}/10 │ {ms:6.1f} ms")

    # ── combination ───────────────────────────────────────────────────────
    print("\n" + "─" * 78)
    union = {l: any(coverage[n][l] for n in LAYERS) for l in letters}
    n_union = sum(1 for l in letters if union[l])
    print(f"  UNION de toutes les couches : {n_union}/10 cas détectés")

    for subset_name, names in [
        ("snapshot seul (full)", ["snapshot full"]),
        ("snapshot + eval structure", ["snapshot full", "eval structure"]),
        ("+ innerText", ["snapshot full", "eval structure", "eval innerText"]),
        ("+ obstacles", ["snapshot full", "eval structure", "eval innerText", "eval obstacles"]),
    ]:
        covered = sum(
            1 for l in letters if any(coverage[n][l] for n in names)
        )
        cost = sum(
            sum(baseline_times[n]) / max(len(baseline_times[n]), 1) for n in names
        )
        print(f"  {subset_name:28} : {covered}/10 cas  ({cost:6.1f} ms)")

    print("\n" + "─" * 78)
    print("  BUDGET TEMPS (moyenne par appel)")
    for name in LAYERS:
        ms = sum(baseline_times[name]) / max(len(baseline_times[name]), 1)
        print(f"    {name.ljust(width)}  {ms:7.1f} ms   (succès {ok_counts[name]}/10)")
    print("═" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
