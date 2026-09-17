"""Hermes 2.0 — Vision Escalation Engine.

Resolves UNKNOWN verdicts *conditionally*, using the existing ``browser_vision``
tool as a backend. Never called per action by default.

Responsibility split (enforced, not just documented)::

    VISION   = OBSERVER   -> produces a structured VisionObservation
    VERIFIER = JUDGE      -> decides whether that observation satisfies
                             the ExpectedTransition

    The vision model may report "I see a Settings menu on screen".
    It may NOT conclude "so the objective succeeded". Only the judge may.

Hard rule:
    UNKNOWN never becomes VERIFIED merely because the model *thinks* the action
    worked. Escalation can only move UNKNOWN -> FAILED (proven contradiction)
    or UNKNOWN -> VERIFIED **through an explicit claim being matched**, which
    requires an ExpectedTransition to exist in the first place.

Reality check against the codebase (verified, not assumed):
    - ``browser_vision(question, annotate=False, task_id=None)`` returns a JSON
      string: ``{"success": bool, "analysis": str, "screenshot_path": str}``,
      or ``{"success": False, "error": str, ...}`` on failure.
    - Whether it attaches the screenshot natively or routes to an auxiliary
      vision LLM is decided by ``_should_use_native_vision_fast_path()``
      (tools/vision_tools.py). We only *read* that decision.
    - The auxiliary path calls ``call_llm(task="vision", max_tokens=2000,
      timeout=auxiliary.vision.timeout)`` and records usage via
      ``record_aux_usage``. We do not reimplement any of it.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from agent.verification.evidence import (
    ActionEvidence,
    ExpectedTransition,
    Outcome,
)

logger = logging.getLogger(__name__)


# ── risk ──────────────────────────────────────────────────────────────────
class RiskLevel(str, Enum):
    """How much is at stake if we get this action's verdict wrong."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _RISK_ORDER[self]


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

# Ordered risk vocabulary, for callers that want to express a hint.
_ACTION_RISK_HINTS: dict[str, RiskLevel] = {
    # Read-only browser actions: cheap to get wrong.
    "browser_snapshot": RiskLevel.LOW,
    "browser_get_images": RiskLevel.LOW,
    # Navigation is medium by default (recoverable, but a wrong page wastes turns).
    "browser_navigate": RiskLevel.MEDIUM,
    # Clicking can submit, delete, purchase — unknown ref, so medium by default.
    "browser_click": RiskLevel.MEDIUM,
    "browser_type": RiskLevel.MEDIUM,
    "browser_press": RiskLevel.MEDIUM,
}


def infer_risk_level(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
) -> RiskLevel:
    """Best-effort risk guess for a browser action.

    Deliberately conservative and *documented as a guess*: the tool schema
    carries no risk metadata, so there is no authoritative source. Callers
    that know the stakes should pass an explicit ``RiskLevel`` instead.

    Args:
        tool_name: Name of the action.
        tool_args: Its arguments (unused today, kept for forward compatibility).

    Returns:
        A ``RiskLevel``. Unknown tools default to MEDIUM — never LOW, so an
        unrecognised action cannot silently skip escalation.
    """
    return _ACTION_RISK_HINTS.get((tool_name or "").strip(), RiskLevel.MEDIUM)


# ── policy ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class EscalationPolicy:
    """When — and whether — to spend a vision call on an UNKNOWN verdict.

    Attributes:
        min_risk: Lowest risk level that justifies a vision call.
        max_calls_per_session: Hard cap on vision calls for a session.
        escalate_on_obstacle: Escalate when an obstacle is suspected.
        escalate_on_dom_contradiction: Escalate when DOM signals contradict.
        diagnose_failures: Also escalate on FAILED (off by default — a proven
            failure needs no diagnosis, and this is the main cost guard).
        min_confidence: Vision observations below this confidence stay UNKNOWN.
        respect_availability: Skip escalation when vision is unavailable.
    """

    min_risk: RiskLevel = RiskLevel.MEDIUM
    max_calls_per_session: int = 10

    escalate_on_obstacle: bool = True
    escalate_on_dom_contradiction: bool = True
    diagnose_failures: bool = False

    min_confidence: float = 0.5
    respect_availability: bool = True

    def allows(self, risk: RiskLevel) -> bool:
        """Whether this risk level clears the configured bar."""
        return risk.rank >= self.min_risk.rank


@dataclass(frozen=True)
class EscalationDecision:
    """The outcome of the policy check — before any vision call is made."""

    needed: bool
    reason: str
    risk: RiskLevel

    def to_dict(self) -> dict[str, Any]:
        return {"needed": self.needed, "reason": self.reason, "risk": self.risk.value}


# ── structured observation (the OBSERVER side) ────────────────────────────
@dataclass(frozen=True)
class VisionObservation:
    """What the vision backend reported — observation only, never a verdict.

    Attributes:
        observation: The raw textual analysis.
        elements: UI elements the analysis appears to mention.
        obstacle: A detected blocking element, if any (modal, captcha, error…).
            Kept as the FIRST entry of ``obstacles`` for backward compatibility.
        obstacles: Every obstacle the analysis reports. The scalar ``obstacle``
            cannot represent "the expected banner is here AND a captcha appeared",
            so the full set is carried here.
        confidence: How much to trust this observation (0..1). Derived from
            hedging language, because ``browser_vision`` returns free text with
            no self-reported score. Neutral when there is no signal.
        source: ``native`` / ``auxiliary`` / ``unavailable``.
        contradictions: Signals that conflict with the expectation.
        screenshot_path: Persisted screenshot, when produced.
        error: Set when the observation itself failed.
    """

    observation: str = ""
    elements: tuple[str, ...] = ()
    obstacle: str | None = None
    obstacles: tuple[str, ...] = ()
    confidence: float = 0.5
    source: str = "unavailable"
    contradictions: tuple[str, ...] = ()
    screenshot_path: str | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        """True when the observation carries usable content."""
        return self.error is None and bool(self.observation.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation,
            "elements": list(self.elements),
            "obstacle": self.obstacle,
            "obstacles": list(self.obstacles),
            "confidence": self.confidence,
            "source": self.source,
            "contradictions": list(self.contradictions),
            "screenshot_path": self.screenshot_path,
            "error": self.error,
            "available": self.available,
        }


# ── escalation policy ─────────────────────────────────────────────────────
def decide_escalation(
    *,
    evidence: ActionEvidence,
    risk: RiskLevel,
    policy: EscalationPolicy | None = None,
    vision_available: bool = True,
    calls_used: int = 0,
) -> EscalationDecision:
    """Decide whether an evidence record deserves a vision call.

    Only UNKNOWN is a candidate (unless ``diagnose_failures`` is on). VERIFIED
    and FAILED short-circuit — spending vision on a settled verdict is exactly
    the waste this layer exists to prevent.
    """
    policy = policy or EscalationPolicy()

    # Settled verdicts never escalate by default.
    if evidence.outcome is Outcome.VERIFIED:
        return EscalationDecision(False, "already verified", risk)
    if evidence.outcome is Outcome.FAILED and not policy.diagnose_failures:
        return EscalationDecision(False, "already failed (diagnosis disabled)", risk)

    if not policy.allows(risk):
        return EscalationDecision(
            False,
            f"risk {risk.value} below threshold {policy.min_risk.value}",
            risk,
        )

    if calls_used >= policy.max_calls_per_session:
        return EscalationDecision(
            False,
            f"vision budget exhausted ({calls_used}/{policy.max_calls_per_session})",
            risk,
        )

    if policy.respect_availability and not vision_available:
        return EscalationDecision(False, "vision unavailable", risk)

    # Obstacles are the strongest signal that text snapshots cannot explain.
    obstacles_suspected = bool(
        evidence.diff
        and (
            evidence.diff.dialogs_opened
            or evidence.diff.overlays_added
            or evidence.diff.errors_added
        )
    )
    if obstacles_suspected and policy.escalate_on_obstacle:
        return EscalationDecision(True, "obstacle suspected after action", risk)

    # DOM signals contradicting the expectation.
    if evidence.diff is not None and policy.escalate_on_dom_contradiction:
        if (
            evidence.expected is not None
            and evidence.expected.expect_dom_change is True
        ):
            if not evidence.diff.accessibility_changed:
                return EscalationDecision(
                    True, "expected DOM change absent — needs visual confirmation", risk
                )

    if evidence.before is not None and not evidence.before.observed_ok:
        return EscalationDecision(True, "before-state observation was incomplete", risk)

    if evidence.after is not None and not evidence.after.observed_ok:
        return EscalationDecision(True, "after-state observation failed", risk)

    # Default: the verdict is simply under-determined.
    return EscalationDecision(True, "verdict under-determined", risk)


# ── the observer (calls the EXISTING browser_vision backend) ──────────────
#: Error signatures that PROVE no vision backend exists. When one of these is
#: seen, the answer cannot change within the process lifetime, so we stop
#: paying ~370 ms per click to rediscover it.
_PROVIDER_MISSING_MARKERS = (
    "no llm provider configured",
    "run: hermes setup",
    "no provider configured",
    "no api key",
)

#: Latched once a call has proven no provider exists.
_VISION_UNAVAILABLE = False
_VISION_UNAVAILABLE_REASON = ""


def mark_vision_unavailable(reason: str) -> None:
    """Latch vision as definitively unavailable for this process."""
    global _VISION_UNAVAILABLE, _VISION_UNAVAILABLE_REASON
    _VISION_UNAVAILABLE = True
    _VISION_UNAVAILABLE_REASON = (reason or "")[:200]
    logger.info("H2 vision latched unavailable: %s", _VISION_UNAVAILABLE_REASON)


def reset_vision_availability() -> None:
    """Clear the latch (tests, or after a config change)."""
    global _VISION_UNAVAILABLE, _VISION_UNAVAILABLE_REASON
    _VISION_UNAVAILABLE = False
    _VISION_UNAVAILABLE_REASON = ""


def vision_unavailable_reason() -> str:
    """Why vision is known to be unavailable, or ""."""
    return _VISION_UNAVAILABLE_REASON


def is_provider_missing_error(message: str) -> bool:
    """Whether an error message proves no vision provider is configured."""
    text = (message or "").lower()
    return any(marker in text for marker in _PROVIDER_MISSING_MARKERS)


def vision_is_available() -> bool:
    """Best-effort check that a vision path exists.

    Returns False immediately once a previous call has *proven* no provider
    exists — that is the fix for H2.0-006's 370 ms/click of wasted attempts.

    When availability is merely unknown, this stays optimistic (True) so the
    first call can settle the question. It never claims absence without proof.
    """
    if _VISION_UNAVAILABLE:
        return False

    try:
        from agent.auxiliary_client import _read_main_provider

        provider = (_read_main_provider() or "").strip()
        if provider.lower() in {"", "auto"}:
            # Nothing explicitly chosen: resolution may still succeed, but we
            # cannot prove it here. Stay optimistic; the first call settles it.
            pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("vision availability: provider probe failed (%s)", exc)

    try:
        from tools.vision_tools import _should_use_native_vision_fast_path

        if _should_use_native_vision_fast_path():
            return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("vision availability: native probe failed (%s)", exc)

    try:
        from tools.browser_tool import _get_vision_model

        # No explicit model configured is fine: call_llm routes to the default
        # auxiliary provider. We cannot prove absence, so we do not claim it.
        _get_vision_model()
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("vision availability: aux probe failed (%s)", exc)
        return False


# Hedging markers: the model is telling us it is unsure.
_HEDGE_RE = re.compile(
    r"(?i)\b(?:je ne (?:vois|peux|sais)|impossible de|pas clair|peut-être|"
    r"probablement|il semble|difficile à dire|incertain|unsure|cannot tell|"
    r"unclear|maybe|possibly|might be)\b"
)

_OBSTACLE_RE = re.compile(
    r"(?i)\b(captcha|recaptcha|hcaptcha|cloudflare|vérification|verification challenge|"
    r"modale|modal|popup|pop-up|fenêtre contextuelle|overlay|bandeau|banner|"
    r"cookies?|consentement|erreur|error|404|500|page introuvable|not found|"
    r"accès refusé|access denied|session expirée)\b"
)

# An obstacle keyword inside a NEGATED clause asserts its ABSENCE:
#   "No modal dialog is open."  ->  no obstacle
#   "Aucune modale n'est ouverte." -> no obstacle
# The extractor must never invert a sentence's meaning, so negation is checked
# in the clause that carries the keyword — not globally across the analysis.
_NEGATION_RE = re.compile(
    r"(?i)\b(no|not|never|without|none|neither|nor|absent|nothing|"
    r"aucun|aucune|aucuns|aucunes|pas|sans|non|ni|jamais|rien)\b"
)

# A keyword that follows a label separator NAMES a thing instead of reporting it:
#   "C — modal",  "D: overlay",  "**C — modal**"
_LABEL_BEFORE_RE = re.compile(r"(?:—|–|\||:)\s*\**\s*$")

# A clause that enumerates the page's own labelled sections is descriptive prose
# about the page's structure, not a report about its current state:
#   "- **C — modal:** button "Afficher le modal""
_SECTION_ENUM_RE = re.compile(r"(?:\*\*)?\s*\b[A-J]\b\s*(?:\*\*)?\s*[—–:]")

# UI labels are quoted. A keyword inside quotes is the NAME of a control, not a
# statement that the thing is on screen:  button "Afficher le modal"
_QUOTE_CHARS = ('"', "«", "“", "‘", "`")

# Models organise their report with markdown headings. A heading names the
# CATEGORY it is about, it does not assert that anything is on screen:
#   "## Modals, banners, error messages, blocking elements"
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")

# Obstacle keywords are read per clause. Without this, "No error, but a modal is
# open" would let the negation of `error` swallow the asserted `modal`.
_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?;])\s+"                                              # sentence end
    r"|\n+"                                                        # line break
    r"|\s+[-•*]\s+"                                                # bullet
    r"|,?\s*\b(?:but|however|mais|toutefois|cependant|néanmoins)\b\s*"  # contrast
    r"|\s+\bet\b\s+|\s+\band\b\s+",                                # coordination
    re.IGNORECASE,
)


def _clauses(text: str) -> list[str]:
    """Split an analysis into clauses that each carry their own polarity."""
    return [c for c in (part.strip() for part in _CLAUSE_SPLIT_RE.split(text)) if c]


def _inside_quotes(clause: str, pos: int) -> bool:
    """True when the character at ``pos`` sits inside a quoted run.

    UI labels are quoted, so ``button "Afficher le modal"`` names a control
    rather than reporting that a modal is on screen.
    """
    before = clause[:pos]
    return any(before.count(q) % 2 == 1 for q in _QUOTE_CHARS)


def _extract_obstacles(text: str) -> tuple[str, ...]:
    """Return EVERY obstacle keyword that is genuinely *reported*, in order.

    Same rules as before — a clause is skipped entirely when it enumerates the
    page's own labelled sections, and inside a clause a keyword is skipped when
    it is negated, quoted (a control's name) or merely labels a section — but
    the result is now collected rather than truncated to the first match, so an
    observation can carry "the expected banner is here AND a captcha appeared".
    """
    found: list[str] = []
    for clause in _clauses(text):
        # Headings name a category; section enumerations describe structure.
        # Neither is a statement about the page's current state.
        if _HEADING_RE.match(clause) or _SECTION_ENUM_RE.search(clause):
            continue
        for match in _OBSTACLE_RE.finditer(clause):
            keyword = match.group(0).lower()
            before = clause[: match.start()]
            after = clause[match.end():]
            # Negation, before or immediately after the keyword.
            if _NEGATION_RE.search(before) or _NEGATION_RE.search(after[:40]):
                continue
            # Inside quotes: a control's name, not a report.
            if _inside_quotes(clause, match.start()):
                continue
            # Nominal/label mention, not a report.
            if _LABEL_BEFORE_RE.search(before):
                continue
            if keyword not in found:
                found.append(keyword)
    return tuple(found)


def _extract_obstacle(text: str) -> str | None:
    """The first genuinely reported obstacle keyword, if any.

    Thin wrapper kept for backward compatibility; callers that need the whole
    picture use :func:`_extract_obstacles`.
    """
    found = _extract_obstacles(text)
    return found[0] if found else None


#: Closed vocabulary. An obstacle keyword belongs to exactly one category, and a
#: category outside this mapping does not exist: nothing may authorise it.
#: The first three mirror WorldState's ``dialogs``/``overlays``/``errors``;
#: ``blocking`` is vision-only (a CDP supervisor never reports it as such).
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dialog": ("modale", "modal", "popup", "pop-up", "fenêtre contextuelle"),
    "overlay": ("overlay", "bandeau", "banner", "cookie", "cookies", "consentement"),
    "error": ("erreur", "error", "404", "500", "page introuvable", "not found"),
    "blocking": (
        "captcha",
        "recaptcha",
        "hcaptcha",
        "cloudflare",
        "vérification",
        "verification challenge",
        "accès refusé",
        "access denied",
        "session expirée",
    ),
}

OBSTACLE_CATEGORIES: tuple[str, ...] = tuple(_CATEGORY_KEYWORDS)


def obstacle_category(keyword: str | None) -> str | None:
    """Map an obstacle keyword to one of the four closed categories.

    Returns ``None`` for an unknown keyword: the vocabulary is closed, so an
    unrecognised word must never be treated as belonging to a category (which
    would let an arbitrary string authorise an obstacle).
    """
    if not keyword:
        return None
    needle = keyword.strip().lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if needle in keywords:
            return category
    return None

_ELEMENT_RE = re.compile(
    r"(?i)\b(?:bouton|button|menu|champ|field|input|lien|link|onglet|tab|"
    r"case|coche|checkbox|titre|heading|tableau|table|liste|list)\b"
)


def _parse_observation(
    analysis: str,
    *,
    source: str,
    screenshot_path: str | None,
) -> VisionObservation:
    """Turn free-text analysis into a structured observation.

    Everything here is heuristic and labelled as such: ``browser_vision``
    returns prose, not JSON, and we must not fabricate a confidence score the
    model never produced.
    """
    text = (analysis or "").strip()

    hedge = _HEDGE_RE.search(text) is not None
    # Honest scale: no self-reported score exists, so we only distinguish
    # "the model hedged" from "the model made a plain statement".
    confidence = 0.4 if hedge else 0.7

    obstacles = _extract_obstacles(text)
    obstacle = obstacles[0] if obstacles else None

    elements = tuple(sorted({m.group(0).lower() for m in _ELEMENT_RE.finditer(text)}))

    contradictions: list[str] = []
    if hedge:
        contradictions.append("model expressed uncertainty")
    if obstacle:
        contradictions.append(f"obstacle detected: {obstacle}")

    return VisionObservation(
        observation=text,
        elements=elements,
        obstacle=obstacle,
        obstacles=obstacles,
        confidence=confidence,
        source=source,
        contradictions=tuple(contradictions),
        screenshot_path=screenshot_path,
    )


_AUX_OBSERVER_MAX_TOKENS = 2000


def _observe_envelope_synchronously(
    payload: dict[str, Any],
    *,
    question: str,
    aux_runner: Callable[..., Any] | None = None,
) -> VisionObservation | None:
    """Describe a native-fast-path screenshot with a synchronous auxiliary LLM.

    The native fast path hands the image to the CONVERSATION and returns a
    multimodal envelope; the main model describes it on its NEXT turn. H2.0
    verifies inside the same action and can never read that turn, so it would
    otherwise receive a placeholder and the verifier could only conclude
    "inconclusive".

    Here H2.0 reads the envelope itself and asks the main model — already the
    vision-capable provider, and the cheapest synchronous option — for a textual
    analysis of the very same image. ``browser_vision`` and the native fast path
    are NOT modified: this is purely H2.0's own interpretation of the envelope.

    Returns ``None`` whenever no usable analysis can be obtained — a missing
    screenshot, a failed call, or an EMPTY response. An empty answer is never
    turned into an observation: that would manufacture proof.
    """
    screenshot_path = payload.get("screenshot_path")
    if not screenshot_path:
        return None

    try:
        import base64
        from pathlib import Path as _Path

        raw = _Path(str(screenshot_path)).read_bytes()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("aux observer: screenshot unreadable (%s)", exc)
        return None

    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    runner = aux_runner
    call_kwargs: dict[str, Any] = {
        "task": "vision",
        "messages": messages,
        # DeepSeek is a reasoning model: it spends the budget on reasoning
        # before emitting content, and a small max_tokens yields finish_reason
        # "length" with an EMPTY string. Measured safe from ~600; we reuse the
        # budget the existing auxiliary path already uses.
        "max_tokens": _AUX_OBSERVER_MAX_TOKENS,
        "temperature": 0.1,
        "timeout": 120.0,
    }
    if runner is None:
        try:
            from agent.auxiliary_client import call_llm

            runner = call_llm
            # Pin the observer to the main provider rather than letting
            # auxiliary.vision (configured for a different backend) decide.
            from agent.auxiliary_client import _read_main_model, _read_main_provider

            provider = _read_main_provider()
            if provider:
                call_kwargs["provider"] = provider
            model = _read_main_model()
            if model:
                call_kwargs["model"] = model
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("aux observer: call_llm unavailable (%s)", exc)
            return None

    try:
        response = runner(**call_kwargs)
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.debug("aux observer: analysis call failed (%s)", exc)
        return None

    if not text:
        # Empty output is a non-observation. Falling through keeps the honest
        # placeholder rather than inventing an analysis.
        logger.debug("aux observer: model returned no content")
        return None

    return _parse_observation(
        text, source="auxiliary", screenshot_path=str(screenshot_path)
    )


def observe_with_vision(
    *,
    question: str,
    task_id: str = "default",
    annotate: bool = False,
    runner: Callable[..., Any] | None = None,
    aux_runner: Callable[..., Any] | None = None,
) -> VisionObservation:
    """Capture one visual observation via the existing browser_vision tool.

    This is the ONLY place the escalation layer touches the browser. It performs
    no judgement whatsoever.

    Args:
        question: What to ask about the page visually.
        task_id: Session isolation.
        annotate: Overlay numbered labels on interactive elements.
        runner: Injection seam for tests; defaults to ``browser_vision``.

    Returns:
        A ``VisionObservation``. Failures are reported, never raised.
    """
    if runner is None:
        try:
            from tools.browser_tool import browser_vision

            runner = browser_vision
        except Exception as exc:
            return VisionObservation(
                source="unavailable",
                error=f"browser_vision import failed: {exc}",
            )

    try:
        raw = runner(question=question, annotate=annotate, task_id=task_id)
    except Exception as exc:
        logger.warning("observe_with_vision: call raised (%s)", exc)
        return VisionObservation(source="unavailable", error=str(exc))

    payload = _parse_vision_result(raw)

    if isinstance(payload, dict) and payload.get("kind") == "native_envelope":
        # The multimodal fast path hands the screenshot to the CONVERSATION and
        # the main model describes it on its next turn. H2.0 verifies inside the
        # same action and never sees that turn, so it asks an auxiliary LLM for a
        # synchronous textual analysis of the same image. The native path itself
        # is untouched — this is H2.0's own reading of the envelope.
        synchronous = _observe_envelope_synchronously(
            payload, question=question, aux_runner=aux_runner
        )
        if synchronous is not None:
            return synchronous

        # No usable analysis: record the fact without inventing one.
        return VisionObservation(
            observation="(screenshot attached natively to the conversation)",
            source="native",
            screenshot_path=payload.get("screenshot_path"),
        )

    if not payload.get("success"):
        error = str(payload.get("error") or "vision analysis failed")

        # Distinguish "there is no vision backend wired up" from "the backend
        # ran and failed". The former is unavailability, not a failed analysis:
        # it is proven, permanent for this process, and must be latched so we
        # stop paying ~370 ms per click to rediscover it.
        if is_provider_missing_error(error):
            mark_vision_unavailable(error)
            source = "unavailable"
        else:
            source = "auxiliary"

        return VisionObservation(
            source=source,
            error=error,
            screenshot_path=payload.get("screenshot_path"),
        )

    return _parse_observation(
        str(payload.get("analysis") or ""),
        source="native" if payload.get("native") else "auxiliary",
        screenshot_path=payload.get("screenshot_path"),
    )


def _parse_vision_result(raw: Any) -> dict[str, Any]:
    """Normalise browser_vision's return into a dict."""
    if isinstance(raw, dict):
        # Native fast path returns a multimodal tool-result envelope instead of
        # a plain JSON payload; detect it by shape rather than guessing.
        if "content" in raw or "parts" in raw or raw.get("type") == "image":
            # browser_vision parks the path under ``meta``
            # (``meta["screenshot_path"] = str(screenshot_path)``), not at the
            # root — reading only the root loses it and the observation ends up
            # without a screenshot to analyse.
            meta = raw.get("meta")
            meta_path = meta.get("screenshot_path") if isinstance(meta, dict) else None
            return {
                "kind": "native_envelope",
                "screenshot_path": (
                    raw.get("screenshot_path") or raw.get("path") or meta_path
                ),
            }
        return raw

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"success": False, "error": "invalid vision JSON"}
        if isinstance(parsed, dict):
            return parsed

    return {"success": False, "error": "unexpected vision response type"}


# ── the judge (VERIFIER side) ─────────────────────────────────────────────
def judge_observation(
    *,
    observation: VisionObservation,
    expected: ExpectedTransition | None,
    policy: EscalationPolicy | None = None,
) -> tuple[Outcome, list[str]]:
    """Decide whether a visual observation satisfies the expectation.

    This is where the responsibility boundary lives: the observer said what it
    saw; this function alone turns it into a verdict.

    Hard rule enforced here:
        If there is no ``expected`` (or it carries no claim), the result is
        UNKNOWN — **even if the vision model is confident the action worked**.
        A model's opinion is not a specification.

    Returns:
        ``(Outcome, reasons)``.
    """
    policy = policy or EscalationPolicy()

    # ── the rule that must never be broken ────────────────────────────────
    if expected is None or not expected.has_any_claim():
        return Outcome.UNKNOWN, [
            "no expected transition to judge against — a vision opinion cannot "
            "substitute for a specification"
        ]

    if not observation.available:
        return Outcome.UNKNOWN, [
            f"vision observation unusable ({observation.error or 'empty'})"
        ]

    if observation.confidence < policy.min_confidence:
        return Outcome.UNKNOWN, [
            f"vision confidence {observation.confidence:.2f} below "
            f"{policy.min_confidence:.2f}"
        ]

    text = observation.observation.lower()
    violations: list[str] = []
    satisfactions: list[str] = []

    # Obstacle claims. An expected category is a QUALIFIED EXCEPTION: it is
    # tolerated only when actually observed, and only for itself — every other
    # reported obstacle remains a violation while expect_no_obstacles holds.
    # It is never a switch: expect_appearing="overlay" does not mean "ignore
    # overlays".
    expected_category = expected.expect_appearing
    observed = observation.obstacles or (
        (observation.obstacle,) if observation.obstacle else ()
    )
    observed_categories = {
        category for category in (obstacle_category(o) for o in observed) if category
    }
    tolerated = {expected_category} if expected_category else set()

    if expected_category and expected_category in observed_categories:
        satisfactions.append(f"expected {expected_category} appeared")

    unexpected = sorted(observed_categories - tolerated)
    if expected.expect_no_obstacles and unexpected:
        violations.append(f"vision reports an obstacle: {', '.join(unexpected)}")

    # URL claims, judged against what the vision actually described
    if expected.expect_url_contains is not None:
        needle = expected.expect_url_contains.lower()
        if needle in text:
            satisfactions.append(f"vision mentions {needle!r}")
        else:
            # Absence of the string in prose is weak evidence: stay silent
            # rather than call it a violation.
            pass

    if expected.expect_url_missing is not None:
        needle = expected.expect_url_missing.lower()
        if needle in text:
            violations.append(f"vision mentions forbidden {needle!r}")

    # Explicit contradictions from the observer. A contradiction naming the
    # tolerated category IS the expected element, not a violation — otherwise
    # the extractor's own "obstacle detected: …" note would both defeat the
    # exemption and block the satisfaction it is supposed to produce.
    unresolved: list[str] = []
    for c in observation.contradictions:
        if "obstacle detected" not in c:
            unresolved.append(c)
            continue
        keyword = c.split(":", 1)[1].strip() if ":" in c else ""
        if obstacle_category(keyword) in tolerated:
            # The expected element was observed: this is the satisfaction, not
            # a contradiction to hold against the action.
            continue
        if c not in violations:
            violations.append(c)
        unresolved.append(c)

    if violations:
        return Outcome.FAILED, violations + satisfactions

    if satisfactions and not unresolved:
        return Outcome.VERIFIED, satisfactions

    # Something was seen but nothing decisive: never upgrade on ambiguity.
    return Outcome.UNKNOWN, [
        "vision produced no decisive evidence for the expected transition"
    ] + unresolved


# ── pipeline ──────────────────────────────────────────────────────────────
def escalate_unknown(
    *,
    evidence: ActionEvidence,
    risk: RiskLevel,
    expected: ExpectedTransition | None = None,
    policy: EscalationPolicy | None = None,
    question: str | None = None,
    task_id: str = "default",
    vision_available: bool | None = None,
    calls_used: int = 0,
    runner: Callable[..., Any] | None = None,
) -> tuple[ActionEvidence, VisionObservation | None, EscalationDecision]:
    """Try to resolve an UNKNOWN verdict with a single, conditional vision call.

    Args:
        evidence: The UNKNOWN evidence from ``ActionVerifier``.
        risk: How much is at stake.
        expected: The claim to judge against (defaults to the evidence's own).
        policy: Escalation policy.
        question: Question for the vision model; a sensible default is built
            from the expectation when omitted.
        task_id: Session isolation.
        vision_available: Override the availability probe.
        calls_used: Vision calls already spent this session.
        runner: Injection seam for tests.

    Returns:
        ``(evidence, observation_or_None, decision)``. ``evidence`` is a new
        record when the verdict changed, otherwise the input unchanged. The
        observation is returned even on failure so callers can log it.
    """
    policy = policy or EscalationPolicy()
    expected = expected if expected is not None else evidence.expected

    if vision_available is None:
        vision_available = vision_is_available()

    decision = decide_escalation(
        evidence=evidence,
        risk=risk,
        policy=policy,
        vision_available=vision_available,
        calls_used=calls_used,
    )

    if not decision.needed:
        return evidence, None, decision

    question = question or _default_question(expected)
    observation = observe_with_vision(question=question, task_id=task_id, runner=runner)

    outcome, reasons = judge_observation(
        observation=observation, expected=expected, policy=policy
    )

    resolved = _reissue(
        evidence,
        outcome=outcome,
        reasons=reasons,
        observation=observation,
        decision=decision,
    )
    return resolved, observation, decision


def _default_question(expected: ExpectedTransition | None) -> str:
    """Build a neutral, observation-only question for the vision model.

    The prompt asks what is *visible*. It deliberately never asks "did it
    work?", which would invite the model to adjudicate — the judge's job.
    """
    if expected is None or not expected.description:
        return (
            "Describe precisely what is visible on this page right now: any "
            "heading, error message, modal, banner or blocking element. "
            "Do not judge whether anything succeeded."
        )
    return (
        f"Describe precisely what is visible on this page right now. "
        f"Context: the expected outcome was: {expected.description}. "
        f"Report any heading, error message, modal, banner or blocking element "
        f"you can see. Do not judge whether the objective succeeded — only "
        f"describe what is on screen."
    )


def _reissue(
    evidence: ActionEvidence,
    *,
    outcome: Outcome,
    reasons: list[str],
    observation: VisionObservation,
    decision: EscalationDecision,
) -> ActionEvidence:
    """Return a copy of the evidence with the escalated verdict recorded."""
    metadata = dict(evidence.metadata)
    metadata["escalation"] = decision.to_dict()
    metadata["vision_source"] = observation.source
    metadata["vision_confidence"] = observation.confidence
    if observation.screenshot_path:
        metadata["screenshot_path"] = observation.screenshot_path

    return ActionEvidence(
        task_id=evidence.task_id,
        tool_name=evidence.tool_name,
        tool_args=dict(evidence.tool_args),
        tool_success=evidence.tool_success,
        before=evidence.before,
        after=evidence.after,
        diff=evidence.diff,
        expected=evidence.expected,
        outcome=outcome,
        reasons=tuple(reasons),
        vision_used=True,
        metadata=metadata,
    )


@dataclass
class VisionBudget:
    """Tracks vision calls so a session cannot burn unbounded spend.

    Simple by design: the escalation layer has no session store of its own, so
    callers own the instance and thread it through.

    Note:
        ``max_calls`` here and ``EscalationPolicy.max_calls_per_session`` are
        two views of the same limit. Use ``as_policy()`` to build a policy that
        cannot disagree with the budget — passing an independent policy is the
        one way a caller can accidentally bypass the cap.
    """

    max_calls: int = 10
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def used(self) -> int:
        return len(self.calls)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_calls

    def record(self, *, risk: RiskLevel, reason: str, outcome: Outcome) -> None:
        self.calls.append({
            "risk": risk.value,
            "reason": reason,
            "outcome": outcome.value,
        })

    def as_policy(self, **overrides: Any) -> EscalationPolicy:
        """Return an ``EscalationPolicy`` whose cap matches this budget.

        Any keyword argument overrides the corresponding policy field, so
        callers can raise the risk bar without desynchronising the cap.
        """
        overrides.setdefault("max_calls_per_session", self.max_calls)
        return EscalationPolicy(**overrides)
