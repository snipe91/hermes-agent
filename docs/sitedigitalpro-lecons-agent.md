# Connaissances Site Digital Pro — pour l'agent Hermes

> Résumé opérationnel des leçons apprises lors de la refonte complète de sitedigitalpro.com
> (juillet-septembre 2026). À injecter comme contexte de travail sur ce projet.

---

## 1. Contexte business

- **sitedigitalpro.com** = agence web (Site Digital Pro) : création/refonte de sites WordPress conformes **RGPD (France)** et **Loi 25 (Québec)**, pour TPE/artisans.
- **Marché** : francophone FR + Québec. Pas de ville précise.
- **Forfaits** (prix identiques € et $ CA) : Correctif 2490 / Construction 3990 / Refonte 6690 / Urgence 9999. Mensualités : 208 / 333 / 558 / comptant.
- **Paiement en 12 mensualités sans frais** = argument central (trésorerie des TPE).
- **Ton** : confiant et factuel, PAS alarmiste, PAS de fausse urgence. Règle absolue utilisateur.

## 2. Architecture du site

- **Stack** : WordPress 7.x + Divi 5, o2switch (mutualisé + WAF Tiger Protect), LiteSpeed Cache, Rank Math, Complianz, Code Snippets.
- **Pages refondues en "sdp-apple"** (design sombre premium) : home, forfaits, portfolio, contact, à-propos. Chaque page = un module Code Divi avec `#sdp-apple` + aurora + particules + bascule géo.
- **Bascule FR/QC** : `data-geo="fr"/"qc"` + géo-IP via `ipwho.is` + sessionStorage. Devise même chiffre (€ ↔ $ CA).
- **Liens de paiement** : Stripe Payment Links, 2 jeux (EUR + CAD), basculés par `data-stripe-eur/cad`.

## 3. Leçons critiques (à ne jamais répéter)

1. **Minifier LiteSpeed casse les `//`** dans les scripts inline → toujours `/* */`.
2. **Code Snippets "Enregistrer" peut désactiver** → vérifier + activer après.
3. **Cache LiteSpeed persistant** → purger après chaque modif, tester avec `?cb=`.
4. **Les crawlers SEO détectent de faux mots concaténés** sur les spans data-geo cachés (ne pas "corriger" le H1 réel).
5. **GSAP scroll-reveal peut laisser opacity:0** → fallback setTimeout anti-bug.
6. **Les uploads WP changent de dossier au changement de mois** (2026/08 → 2026/09).
7. **Tirets cadratins (—) = marqueur IA** pénalisant → les remplacer par virgules dans la prose.
8. **Textes en français obligatoires dans les images générées par IA** (kie.ai).
9. **Vision pour vérifier le design** : claude-vision-mcp + OpenRouter (google/gemini-3.5-flash).
10. **qwen3:8b INVENTE des histoires de clients** quand on lui demande du "style narratif" → risque fausse preuve DGCCRF. Jamais de prompt qui invite à créer des anecdotes clients. Les posts narratifs (style Norry/Melina) doivent partir de FAITS RÉELS fournis (refonte du site, décisions internes, plateformes construites) : donner les faits dans le prompt, interdire explicitement toute invention.
11. **Style Melina Ramos (Norry)** = tranche de vie avec arc narratif (situation → incident → leçon), voix "je", humour, zéro structure marketing. Ne PAS confondre avec "histoire de client fictive". Règle : si l'histoire n'est pas vraie, c'est interdit.

## 4. Accès & identifiants (pour interventions)

- **WP REST** : Basic Auth avec email `ssclyde@hotmail.com` + mot de passe d'application (le login `snipe91` n'existe pas comme username).
- **Admin navigateur** : même email, mot de passe principal. WAF bloque le login automatisé → session navigateur.
- **Snippets clés** : #42 Footer, #43 Blog, #44 À-propos, #46 Contraste liens, #47 CTA sémantiques.
- **Stripe** : clé `sk_live_...` (dans rgpd-audit-pro/.env.local). Price IDs EUR + CAD créés.

## 5. État du site (sept 2026)

- **Fait** : home/forfaits/portfolio/contact/à-propos refondus premium + bilingue + Stripe + correctifs audit SORANK (tirets, HN, contrastes, CTA).
- **Reste potentiel** : LCP mobile critique (6.79s) — optimiser images + scripts bloquants. Ajouter formats Q&R pour GEO. E-E-A-T (backlinks, profils auteurs).

## 6. Process de travail recommandé

1. Tester sur le live avec cache-bust.
2. Vérifier le rendu par la vision (capture + description).
3. Calculer les contrastes réels (ne pas deviner).
4. Purger le cache après chaque changement de snippet/page.
5. Mettre à jour PROGRESS.md + ce fichier au fil de l'eau.

## 7. Playbook SEO & Lead Gen (Rédiger pour convertir)

- **Workflow en 9 étapes** : Cadrage cible → Intention SERP → Mots-clés → Analyse concurrence → Plan H2/H3 → Rédaction sans jargon → Optimisation on-page (schema, titre, meta) → Publication → Déclinaison carrousels/réseaux.
- **Relance Leads Automatique** : Séquence CRM n8n 4 emails (répondre aux objections, mensualités 12x) + séquence de réactivation à 90j/6 mois (6 emails offres progressives).
- **Notoriété & E-E-A-T** : Viser les recherches de marque Google (*Brand Search*), interviews/témoignages clients, articles invités et carrousels.
- *Voir le playbook complet :* [`hermes-agent/docs/seo-leadgen-playbook.md`](file:///Users/snipe91/Downloads/free-claude-code/hermes-agent/docs/seo-leadgen-playbook.md)

## 8. Playbook B2B Growth, Sales & Scaling (Valentin Thomy — Offbound)

- **Fondation & Bottleneck** : Traiter séquentiellement Trafic → Marketing/Conversion → Produit/Delivery. Règle du goulot d'étranglement unique.
- **Offre Hybride (DFY + DWY + DIY)** : Maximise le ticket moyen et supprime la friction tout en maintenant une haute scalabilité.
- **Protocole de Closing B2B** : Vente consultative en 2 appels (R1 Découverte & Qualification chiffrée du coût de l'inaction + R2 Closing).
- **Isolation des objections** : "Au-delà du budget, est-ce que tout est clair et voulez-vous bosser avec nous ?" → Traitement du cashflow (12 mensualités) vs confiance dans la méthode.
- **Outreach Haute Conversion** : Premier message focalisé uniquement sur le *taux de réponse* (Soft CTA + ressource offerte), zéro catalogue, zéro lien de prise de rendez-vous agressif.
- **Rétention & Onboarding 5 étoiles** : Formule `Satisfaction = Résultats - Attentes`. Loom personnalisé sous 48h, Quick Win à J+7 et offboarding systématique avec pivot d'upsell vers le consulting/accompagnement.
- **Recrutement & SOP** : Déléguer les micro-tâches répétitives (Virtual Assistant dès 5-10h/sem) et documenter chaque tâche récurrente (> 2 fois) sous forme de SOP Notion/Loom.
- *Voir le playbook complet :* [`hermes-agent/docs/b2b-growth-scaling-playbook.md`](file:///Users/snipe91/Downloads/free-claude-code/hermes-agent/docs/b2b-growth-scaling-playbook.md)
- *Voir la matrice des 34 canaux & Personal Branding :* [`hermes-agent/docs/b2b-acquisition-branding-mastery.md`](file:///Users/snipe91/Downloads/free-claude-code/hermes-agent/docs/b2b-acquisition-branding-mastery.md)
- *Voir l'encyclopédie Vente, Offre, Acquisition & Agents IA (Clay) :* [`hermes-agent/docs/b2b-fullstack-sales-acquisition-encyclopedia.md`](file:///Users/snipe91/Downloads/free-claude-code/hermes-agent/docs/b2b-fullstack-sales-acquisition-encyclopedia.md)

