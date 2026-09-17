"""Hermes 2.0 — action intent.

``browser_click(ref="@e5")`` carries no statement of purpose: a ref is an opaque
handle. That is why the H2.0-006 real run produced 100 % UNKNOWN — the verifier
had nothing to verify against. This module supplies the missing expectation,
without ever guessing loosely enough to manufacture a VERIFIED.

Inference order, strictly:

    1. EXPLICIT      the caller passed an ExpectedTransition
    2. ACTION_CONTEXT a statement of intent already travelling with the action
    3. ELEMENT_PROPS  the target's own accessibility properties (its label)
    4. DETERMINISTIC  a tool whose effect is knowable from its arguments alone
    5. (nothing)      -> expected_transition is None -> the verdict stays UNKNOWN

Rule that must never be relaxed: a weak inference may never become a VERIFIED.
Level 3 (label-derived) inference is deliberately conservative — it only ever
produces an expectation strong enough to be *falsified* (e.g. "this label says
the DOM should change"), never one that can only be confirmed by optimism.

No LLM call is made here. Ever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.verification.evidence import ExpectedTransition


class IntentSource(str, Enum):
    """Where an expectation came from. This is the evidence provenance."""

    EXPLICIT = "explicit"
    ACTION_CONTEXT = "action_context"
    ELEMENT_PROPS = "element_props"
    DETERMINISTIC = "deterministic"
    NONE = "none"


@dataclass(frozen=True)
class ActionIntent:
    """A best-effort statement of what an action is *for*.

    ``expected_transition`` is the only field the verifier consumes. When it is
    ``None``, the action is opaque and the verdict must remain UNKNOWN.
    """

    action_type: str
    target: str = ""
    intent: str = ""
    expected_transition: ExpectedTransition | None = None
    risk_level: str = "medium"
    source: str = IntentSource.NONE.value

    @property
    def has_expectation(self) -> bool:
        if self.expected_transition is None:
            return False
        try:
            return bool(self.expected_transition.has_any_claim())
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target": self.target,
            "intent": self.intent,
            "source": self.source,
            "risk_level": self.risk_level,
            "has_expectation": self.has_expectation,
        }


# ── level 3: derive an expectation from the target's own label ────────────
#: Verbs that assert a state change. Deliberately a closed list: an unknown
#: label yields NO expectation rather than a vague one.
_MUTATION_VERBS = (
    "ouvrir",
    "ouvre",
    "afficher",
    "affiche",
    "ajouter",
    "ajoute",
    "charger",
    "charge",
    "créer",
    "cree",
    "créer",
    "enregistrer",
    "valider",
    "confirmer",
    "envoyer",
    "appliquer",
    "démarrer",
    "lancer",
    "soumettre",
    "toggle",
    "open",
    "show",
    "display",
    "add",
    "load",
    "create",
    "save",
    "submit",
    "confirm",
    "apply",
    "start",
    "run",
    "expand",
    "collapse",
)

#: Verbs asserting navigation. Kept separate because they imply a URL change,
#: which is a much stronger and more checkable claim than "something changed".
_NAVIGATION_VERBS = (
    "aller",
    "go",
    "naviguer",
    "navigate",
    "ouvrir la page",
    "suivant",
    "next",
    "précédent",
    "previous",
    "retour",
    "back",
    "continuer",
    "continue",
)

#: Labels that explicitly promise NO effect. Used to avoid a false FAILED.
_INERT_MARKERS = (
    "ne rien faire",
    "sans effet",
    "aucun changement",
    "do nothing",
    "no-op",
)

#: Verbs that ANNOUNCE something appearing on screen. Kept separate from
#: ``_MUTATION_VERBS``: bringing an element into view is a stronger, more
#: specific claim than "something changed".
_APPEARANCE_VERBS = (
    "afficher",
    "affiche",
    "ouvrir",
    "ouvre",
    "montrer",
    "montre",
    "déplier",
    "deplier",
    "révéler",
    "reveler",
    "show",
    "display",
    "open",
    "expand",
)

#: Closed vocabulary: which element a label may declare as appearing. Aligned
#: with the four obstacle categories the verifier understands
#: (dialog / overlay / error / blocking). A label whose object is absent here is
#: NOT categorisable — the inference must return None rather than guess.
_APPEARANCE_OBJECTS: dict[str, tuple[str, ...]] = {
    "dialog": (
        "modal",
        "modale",
        "popup",
        "pop-up",
        "dialogue",
        "boîte de dialogue",
        "boite de dialogue",
    ),
    "overlay": (
        "bandeau",
        "bannière",
        "banniere",
        "banner",
        "overlay",
        "cookie",
        "consentement",
    ),
    "error": ("erreur", "error", "message d'erreur", "message d erreur"),
    "blocking": ("captcha", "recaptcha", "vérification", "verification"),
}


def _infer_appearing(text: str | None) -> str | None:
    """Category a label explicitly announces as appearing, or ``None``.

    Rule: an appearance VERB **and** a categorisable OBJECT. A verb alone
    ("Afficher", "Ouvrir") or an object outside the closed vocabulary
    ("un élément", "le menu") yields ``None`` — the inference never invents a
    category, because a fabricated one would authorise an obstacle nobody asked
    for.

    The caller's explicit expectation always takes precedence: this function is
    only reached when nothing was declared.
    """
    lowered = (text or "").lower()
    if not any(verb in lowered for verb in _APPEARANCE_VERBS):
        return None
    for category, objects in _APPEARANCE_OBJECTS.items():
        if any(obj in lowered for obj in objects):
            return category
    return None


def label_from_snapshot(snapshot_text: str, ref: str) -> str:
    """Extract the accessible label of ``ref`` from an accessibility snapshot.

    Snapshot lines look like::

        - button "Ouvrir le menu" [ref=e5]

    Args:
        snapshot_text: The raw ``snapshot`` string from ``browser_snapshot``.
        ref: A ref in ``browser_click`` form, e.g. ``@e5``.

    Returns:
        The label, or ``""`` when the ref is absent or unparsable.
    """
    if not snapshot_text or not ref:
        return ""
    want = ref.lstrip("@")
    if not want:
        return ""
    pattern = re.compile(
        r'-\s*\w+\s+"(.*?)"\s+\[[^\]]*?ref=' + re.escape(want) + r"[\],]",
        re.MULTILINE,
    )
    match = pattern.search(snapshot_text)
    if match:
        return match.group(1).strip()

    # Fall back to a looser match: role "label" ... ref=eN
    loose = re.compile(re.escape(want) + r"\]", re.MULTILINE)
    for line in snapshot_text.splitlines():
        if loose.search(line):
            inner = re.search(r'"(.*?)"', line)
            if inner:
                return inner.group(1).strip()
    return ""


def intent_from_label(label: str) -> tuple[ExpectedTransition | None, str, str]:
    """Derive an expectation from an element's label.

    Returns:
        ``(expected_transition, human_intent, confidence_source)``. The
        transition is ``None`` when the label asserts nothing checkable.
    """
    text = (label or "").strip().lower()
    if not text:
        return None, "", IntentSource.NONE.value

    if any(marker in text for marker in _INERT_MARKERS):
        # A button that promises nothing must not be graded as if it did.
        return None, "control labelled as inert", IntentSource.ELEMENT_PROPS.value

    if any(verb in text for verb in _NAVIGATION_VERBS):
        return (
            ExpectedTransition(
                description=f"navigation via {label!r}",
                expect_url_change=True,
            ),
            f"navigate via {label!r}",
            IntentSource.ELEMENT_PROPS.value,
        )

    if any(verb in text for verb in _MUTATION_VERBS):
        return (
            ExpectedTransition(
                description=f"state change via {label!r}",
                expect_dom_change=True,
                # Fallback only: reached when the caller declared nothing. An
                # ambiguous label yields None, which authorises no obstacle.
                expect_appearing=_infer_appearing(text),
            ),
            f"DOM change via {label!r}",
            IntentSource.ELEMENT_PROPS.value,
        )

    # Unknown label: no claim. UNKNOWN beats a guess.
    return None, "", IntentSource.NONE.value


def build_intent(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    *,
    expected: Any = None,
    snapshot_text: str = "",
    risk_level: str = "medium",
) -> ActionIntent:
    """Infer an :class:`ActionIntent` for one action.

    Args:
        tool_name: The tool being run.
        tool_args: Its arguments.
        expected: An expectation supplied by the caller — highest precedence.
        snapshot_text: Accessibility snapshot text, used for label lookup.
        risk_level: Already-resolved risk, carried through.

    Returns:
        An intent whose ``expected_transition`` is ``None`` when nothing was
        inferred. Callers must treat that as UNKNOWN, not as success.
    """
    args = tool_args or {}
    target = str(args.get("ref") or args.get("url") or args.get("selector") or "")[:200]

    # ── 1. EXPLICIT ───────────────────────────────────────────────────────
    if expected is not None and getattr(expected, "has_any_claim", lambda: False)():
        return ActionIntent(
            action_type=tool_name,
            target=target,
            intent=getattr(expected, "description", "") or "explicit expectation",
            expected_transition=expected,
            risk_level=risk_level,
            source=IntentSource.EXPLICIT.value,
        )

    # ── 4. DETERMINISTIC (arguments alone determine the effect) ───────────
    if tool_name == "browser_navigate":
        url = str(args.get("url") or "")
        if url:
            return ActionIntent(
                action_type=tool_name,
                target=url[:200],
                intent=f"navigate to {url[:80]}",
                expected_transition=ExpectedTransition(
                    description="navigation",
                    expect_url_change=True,
                ),
                risk_level=risk_level,
                source=IntentSource.DETERMINISTIC.value,
            )

    # ── 3. ELEMENT_PROPS (the target's own label) ─────────────────────────
    if tool_name in {"browser_click", "browser_press"} and args.get("ref"):
        label = label_from_snapshot(snapshot_text, str(args["ref"]))
        transition, human, source = intent_from_label(label)
        if transition is not None:
            return ActionIntent(
                action_type=tool_name,
                target=target,
                intent=human,
                expected_transition=transition,
                risk_level=risk_level,
                source=source,
            )

    # ── 5. opaque: no expectation, verdict must stay UNKNOWN ──────────────
    return ActionIntent(
        action_type=tool_name,
        target=target,
        intent="",
        expected_transition=None,
        risk_level=risk_level,
        source=IntentSource.NONE.value,
    )
