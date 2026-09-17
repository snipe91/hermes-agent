---
name: fitness-app-growth
description: Stratégies de croissance, rétention et engagement pour l'application fitness SlimHack 2
triggers: ["fitness", "app", "slimhack", "croissance", "utilisateurs", "churn", "retention"]
---

# Fitness App Growth Skill (SlimHack 2)

Ce skill guide Hermes pour analyser, accélérer et pérenniser la croissance de l'application fitness SlimHack 2.

## 1. Métriques Clés (North Star Metrics)
- **DAU / WAU** (Daily / Weekly Active Users) : Fréquence de connexion.
- **Taux de complétion des séances** : % de séances démarrées qui arrivent à terme.
- **Rétention J7, J14, J30** : Objectif cible > 65% à J14.
- **Churn mensuel** : Seuil d'alerte > 8%.

## 2. Principes Psychologiques & Habitudes (Issus des Livres)
1. **La règle de la 3ème séance** : L'ancrage d'habitude se joue dans les 10 premiers jours. Tout utilisateur ayant validé 3 séances a 4x plus de chances de rester actif après 30 jours.
2. **Réduction drastique de la friction cognitive** : Moins de 3 clics entre l'ouverture de l'app et le démarrage du premier exercice.
3. **Boucle de feedback immédiate** : Félicitation personnalisée et visuelle dès la fin d'une séance (dopamine hit).

## 3. Protocoles d'Action & Relances
### Utilisateur Inactif 48h
- Déclencher via OpenClaw une relance bienveillante orientée résultat : *"Pas le temps aujourd'hui ? Même 5 minutes d'étirement comptent pour garder le rythme."*

### Utilisateur en Risque de Churn (Inactif > 6 jours)
- Proposer une réadaptation du programme ou une séance ultra-courte (10 min) pour briser la culpabilité de l'abandon.

## 4. Délégation OpenClaw
Pour exécuter les actions relatives au fitness :
- `openclaw_execute(command="support", params={"query": "Relances onboarding SlimHack"})`
- `openclaw_execute(command="content", params={"topic": "Conseil nutrition et motivation sportive", "platform": "push"})`
