# Issue upstream — vercel-labs/agent-browser

**Titre** : `click` does not scroll the target into view; returns `success: true` when the click lands on `<body>`

---

## Version

`agent-browser` **0.24.0** (darwin-arm64), installed via npm global.

## Summary

`agent-browser click <target>` does not bring the target into the viewport before
dispatching the click. When the target sits below the viewport height, the click
is dispatched to `<body>` instead of the element — and the CLI still reports
success.

`scrollintoview <target>` before `click` fixes it completely.

## Reproduction

Minimal page: 10 identical buttons stacked vertically, plus a capture-phase
listener recording every click that actually reaches the page:

```js
window.__hits = [];
document.addEventListener('click', e => window.__hits.push(e.target.id), true);
```

Viewport is **1280×577**. Buttons sit at y = 128, 187, 246, 305, 364, 423, 482,
541, **600, 659**.

```bash
agent-browser open file:///…/h2_click_page.html
agent-browser snapshot            # refs e1…e11
agent-browser eval "JSON.stringify(window.__hits)"   # []
agent-browser click "#b9"         # y=600, just past the viewport
agent-browser eval "JSON.stringify(window.__hits)"   # ["HTML"]  ← body, not b9
```

| target | y | in viewport | clicked element | CLI result |
|---|---|---|---|---|
| `#b1` … `#b8` | 128 – 541 | yes | the button | success |
| `#b9` | 600 | **no** | `<body>` | **success** |
| `#b10` | 659 | **no** | `<body>` | **success** |
| `#b9` + `scrollintoview` first | 600 | no → scrolled | **the button** | success |

`elementFromPoint()` at the target's centre returns `BODY` for exactly the cases
that fail, and the element's computed `display`, `visibility` and
`pointer-events` are all normal (`block` / `visible` / `auto`) — so this is not
an overlay, not a hidden element, and not a ref-resolution problem.

## Impact

An agent that clicks and then checks `success` will believe the action worked.
With 10 targets on one page, **2 were silently missed**; with the fix, **5/5
were reached**. In a real workflow this produces confidently wrong behaviour
rather than an error.

## Question

**Is the absence of auto-scroll intentional?**

- If **intentional**, could `click` grow an opt-in flag (e.g. `--scroll-into-view`)
  or an `agent-browser.json` key so callers can request Playwright's usual
  `scrollIntoViewIfNeeded` behaviour without an extra round-trip? Today the only
  option on `click` is `--new-tab`, and none of the ~30 documented config keys
  covers scrolling.
- If **unintentional**, would you consider scrolling before dispatch in `click`
  itself? That would let every caller stop paying a second round-trip (~275-380 ms
  measured) for something a click is normally expected to handle.

## Environment

```
agent-browser 0.24.0
macOS 26.6.2 (darwin-arm64)
headless Chromium, viewport 1280x577
local file:// page, no network involved
```

Happy to provide the minimal HTML page or a scripted reproduction if useful.
