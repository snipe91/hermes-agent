# Playbook SEO, Rédaction Web & Lead Gen — Hermes Agent

> **Source :** Méthode opérationnelle "Rédiger pour le web et générer des leads en illimité"  
> **Cibles :** `sitedigitalpro.com`, `rgpd-audit.com` / `rgpd-audit-pro`, et tout site client / projet web.  
> **Rôle pour Hermes :** Directives stratégiques et opérationnelles pour la création de contenu SEO, l'acquisition de trafic et la conversion en leads qualifiés.

---

## 1. Le Processus de Rédaction SEO en 9 Étapes

Pour tout article, page pilier, landing page ou étude de cas généré par Hermes :

```
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│ 1. Intention & Cible    │ ──> │ 2. Recherche SERP       │ ──> │ 3. Analyse Mots-Clés    │
│ (À quoi sert le contenu)│     │ (Intention réelle)      │     │ (Outils & volume)       │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
             │
             ▼
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│ 4. Analyse Concurrence  │ ──> │ 5. Plan & Cœur de Sujet │ ──> │ 6. Phase de Rédaction   │
│ (Faire mieux que le top)│     │ (Structure H2/H3/FAQ)   │     │ (Sans jargon / Anti-IA) │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
             │
             ▼
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│ 7. Optimisation On-Page │ ──> │ 8. Publication & Cache  │ ──> │ 9. Déclinaison Réseaux  │
│ (Titre, meta, URL, mesh)│     │ (Indexation Search Cons)│     │ (LinkedIn, Carrousels)  │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
```

1. **Cadrage & Cible :** À quoi sert ce contenu ? Pour qui exactement (ex. artisan débordé, patron de TPE, agence) ? Pourquoi nous sommes légitimes pour l'écrire (qui je suis + angle d'expertise) ?
2. **Intention de Recherche :** Analyser le 1er écran Google. Est-ce informationnel, commercial, comparatif ou transactionnel ?
3. **Analyse Mots-Clés (Outils) :** Identifier le mot-clé principal + 3-5 variantes sémantiques et questions fréquentes (PAA).
4. **Analyse SERP Concurrentielle :** Identifier les faiblesses des 3 premiers résultats et faire objectivement plus complet, plus clair, plus actionnable (données concrètes, tableaux, templates).
5. **Plan & Cœur du Contenu :** Construire le squelette (H1, H2, H3) sans sauter de niveaux de titres (règle audit SORANK).
6. **Rédaction :** Rédiger au style direct ("vous"), clair, factuel, sans verbiage IA, sans tirets cadratins inutiles dans la prose.
7. **Optimisation On-Page :**
   - Balise Titre (< 60 car.) contenant le mot-clé au début.
   - Meta-description (< 155 car.) avec proposition de valeur et call-to-action.
   - URL courte et explicite (ex: `/audit-loi-25/`).
   - Maillage interne (2-3 liens vers pages services / forfaits).
   - Balisage Schema.org (Article, FAQPage, Organization).
8. **Publication :** Mise en ligne, vérification du rendu, purge du cache et soumission Search Console.
9. **Déclinaison Sociale (Repurposing) :** Transformer l'article en 1 carrousel LinkedIn/Instagram (via `gemini-carousel`) et 2 posts d'accroche (via `hook-generator`).

---

## 2. Système de Conversion & Relance Automatique des Leads

Le trafic SEO ne sert à rien s'il n'est pas capté et relancé :

### A. Génération de Leads On-Site
* **Lead Magnet immédiat :** Diagnostic gratuit, audit express en 3 clics, checklist PDF ou comparateur tarifaire.
* **CTA clair & visible :** Un seul appel à l'action principal par page (ex. *"Faire auditer mon site"* ou *"Voir les forfaits en 12 mensualités"*).
* **Signaux de confiance :** Témoignages clients, mentions légales, conformité RGPD, badge de sécurité SSL.

### B. Relance Automatique (Workflow CRM + n8n)
* **Emailing automatisé :** Séquence d'accueil (Welcome sequence) en 3 à 5 emails répondant à chaque objection client :
  1. *Email 1 (Immédiat)* : Livraison du diagnostic / valeur promise.
  2. *Email 2 (J+2)* : Pourquoi un site invisible et non conforme coûte plus cher qu'un forfait (factuel, pas d'alarmisme).
  3. *Email 3 (J+4)* : La solution du paiement en 12 mensualités pour étaler la dépense.
  4. *Email 4 (J+7)* : Étude de cas concrète / retour d'expérience avant-après.
  * **Arrêt immédiat** : La séquence n8n doit obligatoirement s'arrêter ou pivoter dès qu'un prospect répond, prend rendez-vous, commande ou demande sa désinscription.
* **Séquence de Réactivation pour Leads Froids (> 90 jours) :**
  - Campagne de relance ciblée sur les besoins saisonniers ou mises à jour légales.
  - Séquence de **6 emails ciblés** avec des offres progressives (ex: audit approfondi offert, remise sur refonte, diagnostic Loi 25 d'urgence).

---

## 3. Diversification des Canaux d'Acquisition

Ne pas dépendre uniquement du SEO Google standard :

1. **Brand Search (Recherche de Marque) :**
   - Faire en sorte que les prospects cherchent directement `"Site Digital Pro"` ou `"RGPD Audit Pro"` sur Google. C'est le signal de confiance le plus puissant pour l'algorithme de Google.
2. **Réseaux Sociaux Organiques & Carrousels :**
   - LinkedIn pour le B2B et les décideurs TPE.
   - Instagram / Carrousels visuels pour les artisans et indépendants.
3. **Newsletters Thématiques :**
   - Envoyer 1 newsletter bimensuelle informative (veille légale Loi 25 / RGPD, conseils web).
4. **Articles Invités & Publications Médias :**
   - Guest posts sur des blogs d'entrepreneurs, comptables, juristes et médias professionnels pour obtenir des backlinks d'autorité.
5. **Preuve Sociale Multimédia :**
   - Interviews et témoignages clients (format vidéo court + transcription écrite pour le blog).

---

## 4. Analyse, Ajustement & Amélioration Continue

* **Suivi des métriques réelles (pas de score d'outil abstrait) :**
  - Google Analytics 4 : conversions réelles, passages de l'offre au paiement, prises de contact.
  - Search Console : clics hors marque, requêtes de niche qualifiées, statut d'indexation.
* **Mise à jour régulière :** Ré-optimiser les pages existantes qui se positionnent entre la position 5 et 20 pour les propulser dans le Top 3.
* **Veille concurrentielle :** Analyser les nouveaux contenus publiés par les concurrents du secteur et combler les lacunes sémantiques.

---

## 5. Automatisation & Synergie IA (La Règle d'Or)

* **Automatiser tout ce qui peut l'être :** Workflows n8n, triggers webhooks, génération de carrousels via Gemini, classification de leads.
* **Exploitation des LLM par Hermes :** Utiliser les modèles (Claude, Gemini, DeepSeek, GPT) avec les compétences spécialisées (`gemini-carousel`, `hook-generator`, `post-formatter`, `humanizer-blanco`) pour garantir une exécution rapide avec zéro défaut.

---

## 6. Gouvernance des 828 Pages Locales & Arbitrage par la Donnée

* **Règle de gel des nouvelles créations** : Aucune nouvelle série de pages métiers × villes n'est déployée sans preuve d'une intention de recherche distincte, d'un contenu à forte valeur ajoutée et d'un plan de maillage interne bidirectionnel.
* **Maillage fluide et non unilatéral** :
  - Prestation $\leftrightarrow$ Page métier $\leftrightarrow$ Pages locales pertinentes $\to$ Réalisation / Devis.
  - Les pages piliers doivent également pointer vers les pages locales représentatives (pas de maillage ascendant strict à sens unique).
* **Protocole de consolidation des pages proches** :
  1. Comparer les requêtes réelles (Search Console) et le volume de trafic.
  2. Si cannibalisation avérée : choisir l'URL dominante, fusionner les contenus utiles, et mettre en place une redirection 301 vers la page canonique.
  3. Zéro désindexation massive ni redirection aveugle vers l'accueil.
