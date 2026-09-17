---
name: website-agency-operations
description: Pilotage opérationnel et commercial de l'agence web SiteDigitalPro (création de site, refonte, audits RGPD, devis)
triggers: ["agence", "sitedigitalpro", "site web", "artisan", "prospection", "devis", "rgpd"]
---

# Website Agency Operations Skill (SiteDigitalPro)

Ce skill formalise la méthodologie d'Hermes pour piloter l'agence web SiteDigitalPro avec rigueur, rentabilité et satisfaction client maximale.

## 1. Modèle Économique & Offre
- **Pack Clé en Main** : 2 490 € (ou 2 490 $ CAD pour le marché québécois).
- **Facilité de trésorerie** : Paiement étalé en 12 mensualités (ex: 229 €/mois) via Stripe.
- **Positionnement de valeur** : Site rapide (<1s LCP), 100% conforme RGPD/Loi 25, optimisé SEO local et GEO (IA search).

## 2. Playbook Prospection & Qualification
1. **Extraction de cibles** :
   - Secteurs prioritaires : Artisans BTP (menuisiers, électriciens, plombiers, couvreurs, maçons).
   - Zone : France métropolitaine & Québec.
2. **Pré-scan de conformité non-intrusif** :
   - Lancer un audit RGPD rapide via OpenClaw : `openclaw_execute(command="audit", params={"url": target_url})`.
   - Relever les failles réelles : absence de politique de confidentialité, bannières cookies manquantes, lenteurs mobiles.
3. **Approche commerciale humaine** :
   - Zéro agressivité commerciale. Toujours apporter de la valeur d'abord : *"Voici 2 points de conformité légale faciles à corriger sur votre site actuel."*

## 3. Déroulement d'un Projet Client
- **Phase 1 : Cadrage (Jour 1)** : Validation des contenus, logo, coordonnées et charte graphique.
- **Phase 2 : Assemblage (Jours 2 à 4)** : Montage avec amélioration progressive (lisible sans JS, pas de contenu masqué).
- **Phase 3 : Conformité & SEO (Jour 5)** : Balisage Schema.org, sitemap, mentions légales et tests Google PageSpeed.
- **Phase 4 : Livraison & Propriété (Jour 7)** : Recette client et remise des accès complets.

## 4. Délégation OpenClaw
- Prospection quotidienne : `openclaw_execute(command="prospect", params={"sectors": ["btp", "menuisier", "electricien"], "limit": 50})`
- Audit d'un prospect : `openclaw_execute(command="audit", params={"url": "https://artisan-exemple.fr", "full": false})`
