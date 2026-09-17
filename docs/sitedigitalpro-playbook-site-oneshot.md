# PLAYBOOK — Créer un site WordPress/Divi premium "one-shot" sans erreur

> Guide exhaustif consolidé de la refonte sitedigitalpro.com (2026).
> Objectif : créer un site complet (design premium sombre, bilingue FR/QC, SEO/GEO, conformité,
> paiement) **du premier coup**, avec le moins d'erreurs possible — en pensant mobile ET desktop.
> Applicable à toute landing de service (TPE/artisan/conformité).

---

## PHASE 0 — AVANT DE CODER (les 10 minutes qui évitent 10 heures)

### 0.1 Comprendre le projet (ne jamais sauter)
1. **Business en 1 phrase** : qui on aide, quel problème concret on résout, quels livrables précis, comment on prouve la qualité.
2. **Marché / Localisation** : France seule ou France + Québec ? (→ sélecteur de région visible prioritaire sur l'IP).
3. **Pages** : accueil, forfaits/services, portfolio/réalisations, contact, à-propos, blog, pages légales.
4. **Funnel & Objectif** : clarifier la proposition de valeur métier en premier lieu, avec l'option de paiement échelonné en facilitateur.
5. **CTA & Conversion équilibrée** : 
   - Achat direct (Stripe) pour les forfaits packagés à périmètre clair.
   - Voie de contact/échange facultative (audit gratuit, appel court) pour les projets nécessitant un cadrage préalable.
   - Ne pas faire du formulaire une étape obligatoire pour un achat immédiat, mais afficher les livrables et conditions avant le paiement.
6. **Ton validé avec le client** : confiant, factuel et bienveillant. Zéro pression, zéro fausse urgence, zéro promesse irréaliste.
7. **Conformité & Clarté** : RGPD (FR) / Loi 25 (QC) = cadre légal clair, pas une menace alarmiste. Exactitude des chiffres sourcés.

### 0.2 Design system AVANT tout code
Définir AVANT d'écrire une ligne :
- **Palette** (monochrome + 1 accent) : `#000` fond, `#1d1d1f` cartes, `#2c2c2e` bordures,
  `#f5f5f7` texte principal, `#a1a1aa` secondaire, accent `#2997ff→#0a84ff` dégradé.
- **Typo** : Inter variable (UI) + éventuellement mono pour labels. Échelle clamp().
- **Signature visuelle** : aurora/glow + grille subtile + particules (voir section Effets).
- **Composants réutilisables** : boutons, cartes, badges, cartes prix. Les définir UNE fois.
- **Easing** : `cubic-bezier(.16,1,.3,1)` partout.

---

## PHASE 1 — ARCHITECTURE DE LA PAGE (structure gagnante)

### 1.1 Les sections d'une landing service (ordre éprouvé)
1. **Hero plein écran** : badge/eyebrow + H1 (proposition de valeur métier) + sous-titre (bénéfice concret) + 2 CTA
   (primaire = réserver / forfaits, secondaire = voir les réalisations) + 3 points de réassurance
   (✓ livrables clairs · ✓ accompagnement dédié · ✓ étalement en 12 mensualités).
2. **Preuve de besoin** (factuel) : chiffres sourcés, cadre légal sans dramatisation.
3. **Comparatif** : "le site bricolé ✗ vs fait proprement ✓" (argument de vente clé).
4. **Ce qu'on livre** : 3-4 cartes bénéfices orientées résultat.
5. **Forfaits/Prix** : cartes transparentes avec prix total, échéancier exact (12 × 207,50 €), taxes et liens d'action (1× / 12×).
6. **Crédibilité / Pourquoi nous** (E-E-A-T) : expertise, preuves vérifiables.
7. **Processus** : 3-4 étapes numérotées simples.
8. **CTA final** : récapitulatif des livrables + contact / appel de cadrage.

### 1.2 Structure des titres (SEO) — AUCUN saut
- 1 seul **H1** (le hero). Les H2 = sections. H3 = sous-blocs. H4 = titres footer/colonnes.
- **Interdit** : H3 → H5 sans H4 (trou pénalisé). Hiérarchie stricte H1>H2>H3>H4.
- Vérifier sur le rendu final : `grep -oE '<h[1-6]'` → compter.

---

## PHASE 2 — DESIGN SYSTEM COMPLET (mobile + desktop)

### 2.1 Le fond premium (ne JAMAIS laisser un noir plat)
Un fond `#000` uni = "fade/terne/moche" aux yeux des utilisateurs. Il faut 3 couches :
1. **Aurora** (halos colorés flous animés) — injecté en `<div>` JS (le `body::before` est masqué par `#page-container` opaque sur Divi).
2. **Grille subtile** (lignes 1px, opacité 0.03-0.04, masquée en radial).
3. **Particules constellation** (canvas léger, 30-40 particules, liens entre proches).
```
html body #page-container, .et_pb_section { background: transparent !important }  // POUR VOIR L'AURORA
```
**Performance** : tout en `transform`/`opacity`, pause hors viewport (IntersectionObserver),
désactivé si `prefers-reduced-motion`, particules off sur `pointer: coarse` (mobile).

### 2.2 Composants (définitions réutilisables)
**Boutons** (`.sdp-btn`) :
- Primaire : fond `#2997ff`, texte **blanc**, radius 980px (pilule), hover `translateY(-3px) scale(1.04)` + glow.
- Secondaire : fond `rgba(255,255,255,.06)`, bordure `rgba(255,255,255,.15)`, texte blanc.
- **⚠️ Le CSS global `a {color:#38bdf8}` du thème override les `color` inline** → forcer :
  `#app a.btn[style*="background:#2997ff"], #app a.btn[style*="background:#dc2626"] { color:#fff !important }`.
- Effet shine (pseudo-élément qui balaie au hover) en bonus.

**Cartes** : fond `#1d1d1f`, bordure `#2c2c2e`, radius 24-28px, hover `-6px` + glow bleu.
**Cartes prix** : même + badge "Recommandé" position absolute (titre avec `padding-right:90px` pour pas chevaucher).
**Badges/eyebrow** : pilule `rgba(41,151,255,.1)` + texte `#2997ff`, lettre-espacement large.

### 2.3 Couleurs = contrastes AA (TOUJOURS calculer, jamais deviner)
| Usage | Couleur | Fond | Ratio |
|---|---|---|---|
| Texte principal | `#f5f5f7` | `#1d1d1f` | 15+:1 ✓ |
| Texte secondaire | `#a1a1aa` | `#1d1d1f` | 6.5:1 ✓ |
| Texte tertiaire | `#86868b` | `#1d1d1f` | 4.6:1 ✓ |
| Liens | `#7dd3fc` | sombre | 9:1 ✓ |
| Labels formulaire | `#e2e8f0` | `#1d1d1f` | 13.6:1 ✓ |
| Bouton blanc sur `#2997ff` | blanc | `#2997ff` | 3.02:1 ⚠️ (boutons gras, borderline) |
| Bouton blanc sur `#dc2626` | blanc | `#dc2626` | 4.83:1 ✓ |
- **Boutons gras (bold) grands** = AA à 3:1 acceptable (WCAG large text) mais viser ≥4.5 si possible.
- Ne jamais mettre de texte `#38bdf8` (bleu ciel) sur fond `#2997ff` (bleu) = 1.41:1 INVISIBLE.
- Ne jamais `#94a3b8`/gris moyen sur sombre pour du texte important.

### 2.4 Grilles RESPONSIVE (le piège #1)
- **Mettre `grid-template-columns` en CSS PUR** dans le `<style>`, PAS en inline.
  Sinon le style inline bat le `@media` → grille reste 3 colonnes sur mobile.
```css
#app .grid { grid-template-columns: repeat(3, 1fr); }
@media (max-width: 900px) { #app .grid { grid-template-columns: 1fr; } }  // ou repeat(2,1fr)
```
- **Choix des colonnes** : 3 cartes → 3 cols desktop / 1 mobile. 4 cartes → 2×2 desktop / 1 mobile.
  3 cartes + bandeau = ne PAS mettre le bandeau en 4e carte orpheline (utiliser pleine largeur).
- Règle générale : desktop 2-3 colonnes, tablette 2, mobile 1.

---

## PHASE 3 — EFFETS / ANIMATIONS (CWV-safe)

### 3.1 Règles d'or performance
1. Animer **UNIQUEMENT `transform`/`opacity`** (compositor GPU), jamais `top/left/box-shadow/filter` en boucle.
2. **`prefers-reduced-motion: reduce`** → tout couper (obligatoire a11y).
3. Canvas/particules : **pause hors viewport**, off sur mobile tactile.
4. IntersectionObserver + `requestAnimationFrame` (jamais setInterval).

### 3.2 Rendu & Animations — Contenu visible par défaut (Règle d'or CWV)
Le contenu HTML **DOIT être visible par défaut** dès le premier affichage (`opacity: 1; transform: none;`).
L'animation ne doit être qu'une **amélioration progressive** appliquée uniquement lorsque les scripts et observateurs sont prêts.
- **Règle stricte** : Ne jamais masquer le contenu en inline ou en CSS initial (`opacity: 0`) dans l'espoir qu'un script ou un timer de secours (`setTimeout(..., 2500)`) vienne l'afficher. Si le script échoue, est bloqué ou tarde, la page reste vide pour le visiteur et détruit le LCP/FCP.
- Le premier écran (above-the-fold) ne doit attendre **aucune animation** pour être lisible.
- La stabilité visuelle (CLS < 0,1) et la vitesse du LCP priment sur tous les effets cosmétiques.

### 3.3 Les effets qui valorisent l'expérience (validés)
- **Hero** : transition subtile et non bloquante.
- **Boutons** : hover lift + glow doux.
- **Cartes** : hover lift + bordure qui s'illumine.
- **Particules & Aurora** : Canvas/CSS d'arrière-plan uniquement en amélioration visuelle, paused hors viewport, off sur mobile.
- Voir `references/animation-techniques-premium.md` pour les recettes complètes.

---

## PHASE 4 — LOCALISATION RÉGIONALE (France & Québec)

### 4.1 Sélecteur explicite vs Détection aveugle
- **Le choix explicite prime** : Proposer un sélecteur visible "France / Québec" dans le header et le footer.
- **Pages d'entrée régionales stables** : S'appuyer sur `/agence-web-france/` et `/agence-web-quebec/` comme piliers avec offres et devises natives.
- **Limites de la géo-IP** : Ne pas dépendre d'un appel tiers navigateur (`ipwho.is`) pour modifier silencieusement des prix ou masquer des textes. La géo-IP peut uniquement suggérer un marché, jamais forcer une bascule de prix non consentie (risque de CLS, erreurs VPN et fuite de l'IP visiteur).
- **Règle no-JS & Accessibilité** : Chaque page doit rester 100% compréhensible, accessible et achetable sans JavaScript activé.

### 4.2 Adaptation réelle par marché (pas une simple traduction)
- **France** : Cadre RGPD, CNIL, TVA applicable, étalement en 12 mensualités.
- **Québec** : Cadre Loi 25, CAI, taxes provinciales/fédérales (TPS/TVQ), étalement en 12 versements.
- **Tarifs distincts** : 2 490 € et 2 490 CAD sont deux décisions tarifaires distinctes justifiées par la structure de coûts, les frais Stripe et la fiscalité locale (et non une équivalence monétaire naïve).

### 4.3 Sémantique & Crawlers
- Veiller à ce que l'arbre d'accessibilité et le balisage Schema.org correspondent fidèlement au marché ciblé sans générer d'ambiguïté pour les robots d'indexation.

---

## PHASE 5 — LES PIÈGES TECHNIQUES (WordPress/Divi/LiteSpeed)

### 5.1 Module Code vs Texte
- **Module Code** : HTML/CSS/JS passe tel quel. À utiliser.
- **Module Texte** : `wpautop` + `wp_kses_post` retire les `<script>`. À éviter pour du code.

### 5.2 Scripts inline + minifier LiteSpeed = le piège #1
Le minifier JS de LiteSpeed **supprime les newlines mais GARDE les commentaires `//`**.
Un `//` dans un script inline avale tout le reste → script mort (pageerror "Unexpected end of input").
- **TOUJOURS `/* */`** dans les scripts inline.
- Valider : `node --check` sur le script minifié (newlines retirées).

### 5.3 Cache (LiteSpeed + o2switch)
- Le cache sert l'**ancienne version** → tu corriges, rien ne change, tu crois avoir échoué.
- **Après chaque modif** : purger (`litespeed_type=purge_all` + `purge_all_cssjs`) + tester `?cb=`.
- Un problème qui "revient" = cache qui sert l'ancien. Purger AVANT de re-corriger.

### 5.4 Code Snippets
- `save_snippet_activate` **crée mais n'active PAS** (reste inactive). Toujours vérifier + activer.
- "Enregistrer" (save) peut **désactiver** un snippet actif.
- **Vérifier l'id du snippet** avant d'éditer (facile de confondre #46/#47).
- Les snippets ne sont **pas en REST** → éditer via admin navigateur (CodeMirror `.setValue()` + save).

### 5.5 REST API WordPress
- Auth : Basic Auth avec **email** (le username login n'existe pas forcément) + mot de passe d'application.
- **Les uploads changent de dossier au changement de mois** (08→09). Après upload, récupérer l'URL
  réelle via `/wp-json/wp/v2/media/{id}?fields=source_url`. Ne jamais supposer le chemin.
- Écrire `content` d'un bloc Divi : utiliser le pattern `<!-- wp:divi/placeholder -->` + HTML + `<!-- /wp:divi/placeholder -->`.
- PUT d'une page : `{content, status}` avec le raw complet.
- Désinstaller plugin : d'abord `POST /plugins/{slug}` status inactive, puis DELETE.

### 5.6 WAF o2switch
- Bloque le login automatisé wp-admin (Tiger Protect). Session navigateur requise.
- Bloque les gros POST curl. Utiliser fetch navigateur + nonce si besoin.

---

## PHASE 6 — CONTENU / COPYWRITING (conversion)

### 6.1 Les formules qui convertissent (Jim Edwards + Brunson)
- **Bullets Feature+Bénéfice+Sens** : "Audit ciblé **pour savoir exactement où vous en êtes — fini le flou juridique**".
- **Récap avant CTA** : "Vous recevez : l'audit, la conformité, le rapport, l'accompagnement" juste avant le bouton.
- **Écriture "vous"**, pas "nous". Phrases courtes. Zéro jargon (TPE ne comprend pas le jargon juridique).
- **1 CTA principal clair** par section, répété aux bons endroits.
- **Headline orientée résultat** : "Un site conforme RGPD, pensé pour votre métier et pour votre trésorerie"
  (pas "Nous créons des sites conformes").
- **Ton confiant/factuel** pour TPE (validé) — pas d'alarmisme, pas de fausse urgence, pas de prix barrés énormes.

### 6.2 Anti-marqueurs IA
- **Zéro tiret cadratrin (—) dans la prose** (marqueur IA détecté par les outils anti-IA).
  Remplacer par virgules / deux-points / point. (OK dans les séparateurs de prix.)
- Zéro emoji excessif. Zéro "game-changer/révolutionnaire". Style naturel.
- Texte en **français obligatoire** dans toutes les images générées.

---

## PHASE 7 — PAIEMENT (Stripe, zéro friction)

### 7.1 Stripe Payment Links = la solution lazy
- `POST api.stripe.com/v1/prices` (currency, unit_amount) → `POST /v1/payment_links` (line_items[0][price]).
- **Un lien par option** : chaque forfait a "1 fois" + "12×". Donner le CHOIX au client.
- **2 devises = 2 séries** (EUR + CAD). Bascule client par `data-stripe-eur`/`data-stripe-cad`.
```html
<a href="...EUR..." data-stripe-eur="...EUR..." data-stripe-cad="...CAD...">Payer en 1 fois</a>
```
```js
// dans applyGeo :
document.querySelectorAll('[data-stripe-eur]').forEach(a => {
  a.href = qc ? a.getAttribute('data-stripe-cad') : a.getAttribute('data-stripe-eur');
  a.textContent = qc ? a.textContent.replace('€','$ CA') : a.textContent.replace('$ CA','€');
});
```
- **Abonnements** : `-d "recurring[interval]=month"` SÉPARÉ (concaténer dans un seul -d → erreur).
- Redirection après paiement : `after_completion[redirect][url]=/contact/?paid=ok`.

### 7.2 UX paiement & Réassurance
- Le CTA d'un forfait permet **l'achat direct**, sans imposer de formulaire pour les clients prêts à commander.
- Prévoir obligatoirement une **voie d'échange facultative** (bouton "Poser une question" ou "Réserver un appel de cadrage de 15 min") pour les prospects ayant un doute sur l'éligibilité de leur projet.
- **Transparence avant Stripe** : afficher clairement les livrables inclus, les éventuelles exclusions, les éléments à fournir par le client, le calendrier estimé et les conditions de propriété du site.
- **Séquence de relance CRM (n8n)** : stopper ou adapter la séquence dès qu'un prospect répond, prend rendez-vous, achète ou se désinscrit.

---

## PHASE 8 — ACCESSIBILITÉ + SEO (vérifs finales)

### 8.1 Accessibilité checklist
- [ ] Contenu lisible et complet sans JavaScript (amélioration progressive).
- [ ] Contrastes ≥ 4.5:1 (texte normal), ≥ 3:1 (grand/gras). CALCULER.
- [ ] Zones tactiles ≥ 44px (loi de Fitts) — boutons, liens nav.
- [ ] `prefers-reduced-motion` respecté.
- [ ] 1 seul H1, hiérarchie sémantique cohérente sans saut artificiel.
- [ ] Labels de formulaire visibles (`#e2e8f0`, pas de gris illisible).
- [ ] Alt descriptifs sur les images de contenu.
- [ ] CTA : `aria-label` descriptif sur les liens d'action, SANS `role="button"` forcé sur les balises `<a>`.
- [ ] Menu mobile doté de `hidden` / `inert` et `aria-controls` quand fermé (aucun lien tabbable hors écran).
- [ ] Zéro overflow horizontal (test mobile 390px).

### 8.2 SEO/GEO
- Title < 60 caractères, meta-description 140-160 par marché.
- Fichier `/llms.txt`, sitemap propre, robots.txt autorisant les moteurs légitimes.
- Schéma JSON-LD canonique `#organisation` avec `WebSite.publisher` et fondateur séparé en `Person`.
- Formats Q&R structurés (Quoi/Comment/Pourquoi) et faits sourcés.
- Images WebP/AVIF avec dimensions HTML `width` et `height` (stabilité CLS et vitesse LCP).
- Aucun contenu bloqué derrière une animation non chargée.

---

## PHASE 9 — PROCESS DE LIVRAISON (anti-erreur)

### 9.1 Le flux validé
1. **Brief** → 2. **Maquette HTML locale** (fichier .html autonome) → 3. **Test navigateur**
   desktop 1440 + mobile 390 (overflow, contrastes, effets, 0 erreur console) →
   4. **Validation vision** (capture + description : bugs visuels, textes illisibles) →
   5. **Intégration WP** (PUT REST) → 6. **Purge cache** → 7. **Vérif live cache-bust** →
   8. **Vérif vision finale**.

### 9.2 Checklist finale avant "c'est bon"
- [ ] 0 erreur console (hors préexistants identifiés)
- [ ] 0 overflow horizontal desktop + mobile
- [ ] Reveals tous visibles (fallback anti-bug)
- [ ] Contrats calculés (pas devinés)
- [ ] Hiérarchie HN propre
- [ ] 0 tiret cadratrin dans la prose
- [ ] Textes FR/QC corrects, devises basculent
- [ ] Liens Stripe fonctionnent (1× et 12×, € et $ CA)
- [ ] Cache purgé, version fraîche servie
- [ ] Capture vision finale : design premium, rien de moche

### 9.3 Quand un utilisateur dit "ça ne marche pas" / "c'est toujours pareil"
**NE PAS re-corriger le même code.** Vérifier dans l'ordre :
1. Le cache sert-il l'ancien ? (cache-bust `?cb=`)
2. Le snippet est-il actif ? (Code Snippets)
3. Le bon fichier/page a-t-il été modifié ? (id correct)
4. Le script est-il mort ? (commentaire `//` minifié)
5. Le navigateur a-t-il son propre cache ? (Cmd+Shift+R)

---

## RÉFÉRENCES COMPLÈTES (skill divi-wordpress-builder)
- `references/divi-technical-gotchas.md` — pièges Divi/WP de base.
- `references/divi5-architecture.md` — architecture Divi 5.
- `references/lecons-terrain-sitedigitalpro.md` — 46 leçons terrain détaillées.
- `references/animation-techniques-premium.md` — recettes effets + design system.
- `references/seo-geo.md`, `seo-book-andrieu-2020.md` — SEO profond.
- `references/performance-pagespeed.md` — checklist CWV.
- `references/ux-ui-design-system.md`, `design-brief-process.md` — design.
- `references/header-footer-patterns.md`, `security-legal.md`.
