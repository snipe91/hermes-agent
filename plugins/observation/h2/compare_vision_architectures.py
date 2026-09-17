#!/usr/bin/env python3
"""H2.0-016 — compare the two observation architectures on the SAME UNKNOWN case.

A) GEMINI via the auxiliary path  — a synchronous textual analysis
B) DEEPSEEK via the native path   — the image goes to the main model

Same screenshot, same question (H2.0's own default question), same UNKNOWN case.
Nothing is written: this only reads APIs. No config is touched.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import tools.browser_tool as bt  # noqa: E402

BASE = (Path(__file__).resolve().parent / "h2_coverage_page.html").as_uri()
TASK = "cmp016"

# H2.0's own default question, verbatim.
Q = (
    "Describe precisely what is visible on this page right now: any heading, "
    "error message, modal, banner or blocking element. Do not judge whether "
    "anything succeeded."
)


def screenshot() -> Path:
    """Produce the screenshot H2.0 would use, via the same call it makes."""
    bt.browser_navigate(BASE, task_id=TASK)
    time.sleep(0.5)
    # an UNKNOWN case: a click whose effect the accessibility snapshot misses
    bt._run_browser_command(TASK, "scrollintoview", ["#g-btn"], timeout=15)
    bt._run_browser_command(TASK, "click", ["#g-btn"], timeout=25)
    time.sleep(0.4)
    res = bt.browser_vision("screenshot", annotate=False, task_id=TASK)
    if isinstance(res, dict):
        p = (res.get("meta") or {}).get("screenshot_path")
    else:
        d = json.loads(res)
        p = d.get("screenshot_path") or (d.get("meta") or {}).get("screenshot_path")
    return Path(p)


def ask_gemini(b64: str) -> tuple[float | None, str | None]:
    key = Path(os.path.expanduser("~/.hermes/secrets/gemini_api_key.txt")).read_text().strip()
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-3.6-flash:generateContent?key={key}")
    body = {"contents": [{"parts": [
        {"text": Q},
        {"inline_data": {"mime_type": "image/png", "data": b64}},
    ]}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        return (time.perf_counter() - t0) * 1000, d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return None, f"ERR {type(e).__name__}: {str(e)[:120]}"


def ask_deepseek(b64: str) -> tuple[float | None, str | None]:
    key = None
    env = Path(os.path.expanduser("~/.hermes/.env"))
    if env.exists():
        m = re.search(r"DEEPSEEK_API_KEY=(\S+)", env.read_text())
        if m:
            key = m.group(1)
    if not key:
        return None, "no DEEPSEEK_API_KEY found"
    body = {"model": "deepseek-v4-flash", "max_tokens": 400, "messages": [{
        "role": "user", "content": [
            {"type": "text", "text": Q},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ]}]}
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        return (time.perf_counter() - t0) * 1000, d["choices"][0]["message"]["content"]
    except Exception as e:
        return None, f"ERR {type(e).__name__}: {str(e)[:120]}"


def parse_quality(text: str) -> dict:
    """What the verifier could actually extract from this text."""
    if not text:
        return {"parseable": False}
    low = text.lower()
    elements = re.findall(r"\b(button|heading|counter|banner|modal|dialog|input|link)\b", low)
    obstacle = None
    for marker in ("modal", "dialog", "banner", "blocking", "overlay", "error message"):
        if marker in low:
            obstacle = marker
            break
    return {
        "parseable": True,
        "len": len(text),
        "elements_hint_count": len(set(elements)),
        "elements_hints": sorted(set(elements))[:6],
        "obstacle_hint": obstacle,
        "hedging": any(h in low for h in ("might", "perhaps", "unclear", "not sure", "cannot")),
    }


def main() -> int:
    sp = screenshot()
    print("=" * 96)
    print("  H2.0-016 — A) GEMINI auxiliaire  vs  B) DEEPSEEK natif")
    print("=" * 96)
    print(f"  screenshot : {sp.name}  ({sp.stat().st_size} o)")
    print(f"  question   : {Q[:70]}…")
    print("  " + "─" * 92)

    b64 = base64.b64encode(sp.read_bytes()).decode()

    ms_a, txt_a = ask_gemini(b64)
    ms_b, txt_b = ask_deepseek(b64)

    for label, ms, txt in (("A) GEMINI", ms_a, txt_a), ("B) DEEPSEEK", ms_b, txt_b)):
        print(f"\n  {label}")
        print(f"    latence : {ms:.0f} ms" if ms else "    latence : échec")
        print(f"    réponse : {str(txt)[:260].replace(chr(10), ' ')}")
        q = parse_quality(txt or "")
        print(f"    exploitable par le verifier : {q}")

    print("\n" + "=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
