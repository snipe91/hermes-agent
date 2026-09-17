# Connaissances Site Digital Pro — pour l'agent Hermes

> Résumé opérationnel des leçons apprises lors de la refonte complète de sitedigitalpro.com
> (juillet-septembre 2026). À injecter comme contexte de travail sur ce projet.

---

## 1. Contexte business & Positionnement de l'Offre

- **sitedigitalpro.com** = agence web (Site Digital Pro) : création et refonte de sites WordPress professionnels pour artisans et TPE (France et Québec).
- **Positionnement de valeur (dans cet ordre strict)** :
  1. *À qui on s'adresse* : Artisans, indépendants et dirigeants de TPE débordés.
  2. *Problème concret résolu* : Manque de visibilité sur Google, demandes de devis insuffisantes, conformité légale floue (RGPD en France / Loi 25 au Québec).
  3. *Ce qui est livré* : Un site sur-mesure, rapide, sécurisé, optimisé SEO/GEO, prêt à l'emploi.
  4. *Preuves de confiance* : Réalisations concrètes, méthodes transparentes, livrables documentés.
  5. *Tarif & Modalités* : Paiement transparent avec option d'étalement en 12 mensualités.
- **Paiement en 12 mensualités** = **Facilitateur d'achat** pour étaler la dépense sans peser sur la trésorerie, PAS la proposition de valeur principale.
- **Nommage des forfaits** : Exprimer l'usage et le bénéfice client (ex: Lancement / Croissance / Refonte), éviter les termes de cuisine interne (comme "Correctif" pour un client qui crée son 1er site).
- **Tarifs & Devises (décision commerciale, pas d'équivalence naïve)** :
  - France : 2 490 € (soit 12 × 207,50 € TTC/HT clairement mentionné).
  - Québec : 2 490 CAD (prix distinct justifié par la structure de coûts, taxes et support local).
  - Chaque offre affiche clairement devise, taxes applicables, montant total exact et échéancier. "12 mensualités" = exactement 12 prélèvements, pas un abonnement récurrent indéfini.
- **Ton** : Confiant, factuel et bienveillant. Zéro alarmisme, zéro fausse urgence, zéro promesse irréaliste.

## 2. Architecture & Stratégie Régionale (France / Québec)

- **Localisation explicite vs détection aveugle** :
  - Privilégier un sélecteur visible "France / Québec" où le visiteur choisit explicitement son marché.
  - Ne pas dépendre uniquement d'une API tierce géo-IP (`ipwho.is`) qui peut faillir avec les VPN, envoyer des IP visiteur à un tiers ou créer du CLS au chargement.
  - Pages d'atterrissage régionales stables avec offre dédiée : `/agence-web-france/` et `/agence-web-quebec/`.
- **Règle no-JS & Accessibilité** :
  - Chaque page doit être parfaitement compréhensible, lisible et cohérente sans JavaScript. Les textes, devises et données structurées doivent correspondre au même marché sans inversion silencieuse.
- **Stack** : WordPress 7.x + Divi 5, o2switch, LiteSpeed Cache, Rank Math, Complianz, Code Snippets.

## 3. Leçons critiques & Règles de production Hermes

1. **Contenu visible par défaut (Règle d'or de rendu)** :
   - Le contenu HTML DOIT être visible dès le premier rendu. L'animation JS est une amélioration progressive facultative.
   - Ne JAMAIS masquer un contenu essentiel du premier écran (`opacity: 0`) en dépendant d'un script ou d'un `setTimeout` de secours.
   - La stabilité visuelle (CLS < 0,1) et la vitesse LCP passent avant les effets cosmétiques.
2. **Minification & Scripts JS** :
   - Le JS déployé doit être syntaxiquement valide avant et après optimisation. Privilégier les fichiers versionnés. Maintenir `/* */` pour les commentaires dans les scripts inline comme mesure défensive éprouvée.
3. **Purge de cache ciblée & validation réelle** :
   - Purger uniquement les caches concernés par la modification (pas de purge massive intempestive).
   - Valider sur l'URL canonique sans paramètre, en navigation anonyme, mobile et bureau, avec cache froid puis chaud.
4. **Vérification d'accès WAF** :
   - Tester séparément l'accès visiteur sans cookie, navigateur normal et robots légitimes. Ne pas masquer un problème de WAF/Tiger Protect derrière un simple contournement de script local.
5. **SEO & Rédaction naturelle (Anti-dogmes)** :
   - Pas de règle rigide sur la ponctuation (les tirets cadratins ne sont pas un critère algorithmique d'interdiction). Privilégier un style naturel, direct, fluide et humain.
   - Pas de H4 artificiel obligatoire dans le footer si la sémantique ne l'exige pas.
   - Tout texte important présent dans un visuel doit obligatoirement être présent dans le HTML pour l'accessibilité et les moteurs.
6. **Achat direct & Réassurance** :
   - Achat direct Stripe maintenu pour les offres packagées claires.
   - Laisser toujours une alternative de contact/appel court pour les prospects ayant besoin de valider leur cadrage avant paiement.
   - Rendre visibles avant tout paiement : livrables précis, exclusions, conditions de démarrage, délais et frais de maintenance récurrents éventuels.
   - La séquence CRM n8n doit s'arrêter ou s'adapter immédiatement dès que le prospect répond, achète ou se désinscrit.
7. **Arbitrage des 828 pages locales avec des données réelles** :
   - Règle de gel : Aucune nouvelle série de pages locales publiée sans intention distincte, valeur métier avérée et maillage interne cohérent.
   - Suivre les données Search Console réelles (clics hors marque, requêtes de niche) plutôt qu'un score GEO théorique d'outil.
8. **Schéma Schema.org canonique** :
   - Entreprise représentée par `#organisation` (`LocalBusiness` / `ProfessionalService`).
   - `WebSite.publisher` pointant directement vers `#organisation`.
   - Fondateur représenté séparément en tant que `Person`.
9. **Vision et validation design** : Contrôler le rendu réel (contraste WCAG ≥ 4.5:1, zéro débordement mobile) avant toute mise en ligne.
10. **Protection DGCCRF / Preuve réelle** : Interdiction formelle d'inventer des histoires de clients, des avis ou des statistiques non sourcées.

## 4. Accès & identifiants (pour interventions)

- **WP REST** : Basic Auth avec email `ssclyde@hotmail.com` + mot de passe d'application.
- **Admin navigateur** : même email, mot de passe principal.
- **Snippets clés** : #22 NAP Schema, #35 JS Reveal, #36 Design System CSS, #39 GA4 Complianz, #47 CTA sémantiques.
- **Stripe** : clé `sk_live_...` (Price IDs EUR + CAD créés).

## 5. Garde-fous opérationnels pour Hermes

1. **Documentation systématique** : Chaque modification doit être justifiée par une cause racine identifiée et accompagnée de son test de validation.
2. **Correction à la source** : Corriger le code d'origine plutôt que d'empiler des surcharges CSS `!important` ou des scripts d'écrasement.
3. **Validation humaine obligatoire** : Toute modification portant sur les prix, les liens de paiement Stripe, le consentement RGPD, les redirections ou l'indexation globale nécessite une approbation explicite de l'utilisateur.
4. **Réversibilité** : Tout déploiement doit avoir une procédure de rollback immédiate (backup du snippet ou de la révision WordPress).

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

