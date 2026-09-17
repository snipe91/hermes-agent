#!/usr/bin/env python3
"""H2.0-022 Phase D — evaluate the proposed label-inference rules.

READ-ONLY: the rules below live in this script only. `intent_from_label()` is
NOT modified. This measures what the rules WOULD decide.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.perception.intent import intent_from_label  # noqa: E402

# ── RÈGLES PROPOSÉES (locales, non branchées) ────────────────────────────
_APPEARANCE_VERBS = (
    "afficher", "affiche", "ouvrir", "ouvre", "montrer", "montre",
    "déplier", "deplier", "révéler", "reveler",
    "show", "display", "open", "expand",
)

_APPEARANCE_OBJECTS: dict[str, tuple[str, ...]] = {
    "dialog": (
        "modal", "modale", "popup", "pop-up",
        "dialogue", "boîte de dialogue", "boite de dialogue",
    ),
    "overlay": (
        "bandeau", "bannière", "banniere", "banner", "overlay", "cookie", "consentement",
    ),
    "error": ("erreur", "error", "message d'erreur", "message d erreur"),
    "blocking": ("captcha", "recaptcha", "vérification", "verification"),
}


def infer_appearing(text: str | None) -> str | None:
    """Category the label explicitly announces, or None when it is ambiguous.

    Rule: an appearance VERB **and** a categorisable OBJECT. A verb alone
    ("Afficher", "Ouvrir") or an object outside the closed vocabulary
    ("un élément", "le menu") yields None — the inference never invents.
    """
    t = (text or "").lower()
    if not any(verb in t for verb in _APPEARANCE_VERBS):
        return None
    for category, objects in _APPEARANCE_OBJECTS.items():
        if any(obj in t for obj in objects):
            return category
    return None


CAS: list[tuple[str, str | None]] = [
    # explicites -> catégorie attendue
    ("Afficher le bandeau", "overlay"),
    ("Afficher un bandeau", "overlay"),
    ("Afficher une bannière", "overlay"),
    ("Afficher le cookie banner", "overlay"),
    ("Display the banner", "overlay"),
    ("Ouvrir le modal", "dialog"),
    ("Afficher le modal", "dialog"),
    ("Ouvrir la modale", "dialog"),
    ("Montrer la popup", "dialog"),
    ("Open the modal", "dialog"),
    ("Afficher un message d'erreur", "error"),
    ("Show the error message", "error"),
    ("Afficher un captcha", "blocking"),
    # ambigus -> None obligatoire
    ("Ajouter un élément", None),
    ("Afficher", None),
    ("Ouvrir", None),
    ("Ouvrir le menu", None),
    ("Ajouter au menu", None),
    ("Bouton simple", None),
    ("Charger l'élément", None),
    ("Lancer l'action lente", None),
    ("Ne rien faire", None),
    ("Aller à la section G", None),
    ("Ouvrir un panneau", None),
    ("Expand the panel", None),
    ("Toggle the drawer", None),
]


def main() -> int:
    ok = bad = 0
    print("  LIBELLÉ                        INFÉRÉ     ATTENDU    OK   dom_change  no_obstacles")
    for label, want in CAS:
        got = infer_appearing(label)
        exp, _human, _src = intent_from_label(label)
        dom = getattr(exp, "expect_dom_change", None) if exp else None
        no_obs = getattr(exp, "expect_no_obstacles", None) if exp else None
        mark = "✓" if got == want else "✗"
        if got == want:
            ok += 1
        else:
            bad += 1
        print(
            f"  {label:<30} {str(got):<10} {str(want):<10} {mark}    "
            f"{str(dom):<11} {no_obs}"
        )
    print()
    print(f"  RÉSULTAT : {ok} conformes / {bad} écarts  (sur {len(CAS)} libellés)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
