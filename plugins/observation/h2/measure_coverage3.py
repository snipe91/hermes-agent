#!/usr/bin/env python3
"""H2.0 — coverage matrix v3 (correct click sequence, isolated cases).

Two bugs invalidated the first two passes, both in the measurement harness:

    1. Clicks were issued as ``_run_browser_command(task, "click", ["@e3"])``
       WITHOUT a preceding snapshot, so the CLI had no ref table and answered
       "Unknown ref: e3" for every single case. Every layer therefore looked
       blind when in fact nothing was ever clicked.
    2. The modal case was left open, swallowing later clicks.

This version fixes both: every case runs on a freshly loaded page, and the ref
table is populated through ``browser_snapshot`` (the wrapper the agent itself
uses) before any click.

READ-ONLY EXPERIMENT. No Hermes trajectory is modified, ENFORCE stays off, and
nothing is added to the production observation pipeline.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.browser_tool import (  # noqa: E402
    _run_browser_command,
    browser_snapshot,
)

TASK = "h2cov3"
PAGE = (Path(__file__).resolve().parent / "h2_coverage_page.html").as_uri()

#: (label, ref, description, settle_seconds)
CASES = [
    ("A", "#a-btn", "texte compteur", 0.25),
    ("B", "#b-btn", "menu append", 0.25),
    ("C", "#c-btn", "modal toggle", 0.25),
    ("D", "#d-btn", "overlay alert", 0.25),
    ("E", "#e-btn", "DOM append", 0.25),
    ("F", "#f-btn", "navigation hash", 0.25),
    ("G", "#g-btn", "statut texte", 0.25),
    ("H", "#h-btn", "mutation différée", 1.4),
    ("I", "#i-btn", "loading state", 1.8),
    ("J", "#j-btn", "visuel couleur", 0.25),
]

#: The CLI's @eN ref table is unreliable in this environment: past the first few
#: clicks it silently stops resolving refs while still reporting success. CSS
#: selectors address the element directly and are stable across mutations, so
#: the coverage measurement uses them. See the report for the ref findings.

JS_INNERTEXT = "(() => (document.body.innerText || '').trim())()"
JS_HTML = "(() => (document.body.innerHTML || '').slice(0, 20000))()"
JS_STRUCTURE = (
    "(() => { const a=[...document.body.querySelectorAll('*')]"
    ".map(e=>e.tagName+'#'+(e.id||'')+'.'+(e.className||'')+(e.getAttribute('role')||''));"
    " return JSON.stringify({n:a.length,s:a.join('|')}); })()"
)
JS_VISUAL = (
    "(() => { const a=[...document.body.querySelectorAll('*')]"
    ".map(e=>{const s=getComputedStyle(e);"
    "return e.tagName+':'+s.display+':'+s.visibility+':'+s.backgroundColor;});"
    " return JSON.stringify(a); })()"
)
JS_OBSTACLES = (
    "(() => { const q=(s)=>document.querySelectorAll(s).length;"
    " return JSON.stringify({dialog:q('[role=dialog]'),alert:q('[role=alert]'),"
    "modal:q('[aria-modal=true]')}); })()"
)
JS_URL = "(() => window.location.href)()"

#: layer name -> (kind, spec)
LAYERS: dict[str, tuple[str, list[str]]] = {
    "snapshot -c": ("cli", ["snapshot", "-c"]),
    "snapshot full": ("cli", ["snapshot"]),
    "get text body": ("cli", ["get", "text", "body"]),
    "get url": ("cli", ["get", "url"]),
    "eval innerText": ("cli", ["eval", JS_INNERTEXT]),
    "eval html": ("cli", ["eval", JS_HTML]),
    "eval structure": ("cli", ["eval", JS_STRUCTURE]),
    "eval visual": ("cli", ["eval", JS_VISUAL]),
    "eval obstacles": ("cli", ["eval", JS_OBSTACLES]),
    "eval url": ("cli", ["eval", JS_URL]),
}


def run_cli(args: list[str], timeout: int = 25) -> tuple[object, float]:
    t0 = time.perf_counter()
    try:
        result = _run_browser_command(TASK, args[0], list(args[1:]), timeout=timeout)
        payload = result.get("data", result)
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
    except Exception as exc:
        payload = f"ERR {type(exc).__name__}"
    return payload, (time.perf_counter() - t0) * 1000.0


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:16]


_run_seq = {"n": 0}


def open_page() -> None:
    """Load a genuinely fresh page.

    `open <same-url>` is a no-op in agent-browser: it does NOT reload, so a
    modal opened by one case stayed open and silently swallowed every later
    click. A cache-busting query forces a real navigation each time.
    """
    _run_seq["n"] += 1
    url = f"{PAGE}?run={_run_seq['n']}"
    _run_browser_command(TASK, "open", [url], timeout=45)
    time.sleep(0.4)
    browser_snapshot(full=True, task_id=TASK)


def main() -> int:
    coverage: dict[str, dict[str, bool]] = {n: {} for n in LAYERS}
    timings: dict[str, list[float]] = {n: [] for n in LAYERS}
    click_ok: dict[str, bool] = {}

    for label, ref, _desc, settle in CASES:
        open_page()

        before: dict[str, object] = {}
        for name, (_kind, spec) in LAYERS.items():
            value, ms = run_cli(spec)
            before[name] = value
            timings[name].append(ms)

        result = _run_browser_command(TASK, "click", [ref], timeout=25)
        if label == "C":
            # The modal is the one case that blocks the page while open. Close
            # it right after the post-click measurement below, not here.
            pass
        click_ok[label] = bool(result.get("success"))
        time.sleep(settle)

        # Refresh the ref table the same way the agent would, then re-measure.
        browser_snapshot(full=True, task_id=TASK)

        for name, (_kind, spec) in LAYERS.items():
            after, ms = run_cli(spec)
            coverage[name][label] = digest(before[name]) != digest(after)
        print(f"  {label} {_desc:18} clic={'ok ' if click_ok[label] else 'ERR'}", flush=True)

    letters = [c[0] for c in CASES]
    width = max(len(n) for n in LAYERS)

    print("\n" + "═" * 84)
    print("  MATRICE DE COUVERTURE (v3) — ● détecté   · aveugle")
    print("═" * 84)
    print("  " + "couche".ljust(width) + " │ " + " ".join(letters) + " │ couv. │ coût/appel")
    print("  " + "─" * (width + 2) + "┼" + "─" * (len(letters) * 2 + 1) + "┼───────┼───────────")
    for name in LAYERS:
        marks = "  ".join("●" if coverage[name][l] else "·" for l in letters)
        hits = sum(1 for l in letters if coverage[name][l])
        ms = sum(timings[name]) / max(len(timings[name]), 1)
        print(f"  {name.ljust(width)} │ {marks}  │  {hits:2}/10 │ {ms:7.1f} ms")

    union = {l: any(coverage[n][l] for n in LAYERS) for l in letters}
    print("\n" + "─" * 84)
    print(f"  UNION : {sum(1 for l in letters if union[l])}/10 cas couverts")
    missing = [l for l in letters if not union[l]]
    if missing:
        print(f"  CAS NON COUVERTS PAR AUCUNE COUCHE : {', '.join(missing)}")

    print("\n" + "─" * 84)
    print("  COMPROMIS COÛT / COUVERTURE")
    combos = [
        ("snapshot -c", ["snapshot -c"]),
        ("snapshot full", ["snapshot full"]),
        ("eval structure", ["eval structure"]),
        ("snapshot + struct", ["snapshot full", "eval structure"]),
        ("snapshot + struct + innerText",
         ["snapshot full", "eval structure", "eval innerText"]),
        ("+ obstacles", ["snapshot full", "eval structure", "eval innerText", "eval obstacles"]),
        ("+ visual", ["snapshot full", "eval structure", "eval innerText",
                      "eval obstacles", "eval visual"]),
    ]
    for combo_name, names in combos:
        covered = sum(1 for l in letters if any(coverage[n][l] for n in names))
        cost = sum(sum(timings[n]) / max(len(timings[n]), 1) for n in names)
        print(f"    {combo_name:34} {covered:2}/10   {cost:7.1f} ms")

    print("\n" + "─" * 84)
    print("  CLICS :", "  ".join(f"{l}={('ok' if click_ok[l] else 'ERR')}" for l in letters))
    print("═" * 84)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
