#!/usr/bin/env python3
"""
Strategic Business Planner 2.0 for Hermes Agent.

Acts as the strategic CEO brain across the 3 business pillars:
1. Fitness App (SlimHack 2)
2. Website Agency (SiteDigitalPro)
3. Social Media Empire (B2B & Personal Brand)

Combines real-time metrics from OpenClaw, historical outcomes from Qdrant,
and entrepreneurial wisdom from the 66,746+ book chunks to formulate actionable plans.
"""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from memory.qdrant_reader import query_outcomes
from learning.wisdom_integrator import wisdom_integrator
from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

BUSINESS_PORTFOLIO = {
    "fitness_app": {
        "name": "SlimHack 2",
        "type": "B2C Mobile / Coaching WebApp",
        "key_metrics": ["DAU", "Retention J7/J30", "Séances complétées", "Churn mensuel"],
        "openclaw_command": "support",
        "default_target": "Atteindre 80% de rétention à J14 sur le parcours d'onboarding",
    },
    "website_agency": {
        "name": "SiteDigitalPro",
        "type": "Agence Web B2B (Artisans & PME)",
        "key_metrics": ["Leads qualifiés/semaine", "Taux de conversion devis", "Panier moyen (2490€)", "Délai livraison"],
        "openclaw_command": "prospect",
        "default_target": "50 leads ciblés BTP par semaine et 3 audits de conformité RGPD",
    },
    "social_media": {
        "name": "Social Media Empire",
        "type": "Marque de contenu B2B & Autorité",
        "key_metrics": ["Impressions LinkedIn", "Abonnés newsletter", "Taux d'engagement", "Clics offres"],
        "openclaw_command": "content",
        "default_target": "Mix 60% éducatif, 20% preuve sociale, 20% conversion",
    },
}


class StrategicPlanner:
    """Strategic CEO planner for Hermes 2.0."""

    def __init__(self):
        self.portfolio = BUSINESS_PORTFOLIO

    def weekly_business_review(self) -> Dict[str, Any]:
        """Comprehensive weekly review of all 3 businesses with wisdom-backed actions."""
        report = {
            "date": datetime.date.today().isoformat(),
            "portfolio_summary": "Revue hebdomadaire multi-business Hermes 2.0",
            "businesses": {},
            "top_priorities": [],
            "delegated_actions": [],
        }

        for biz_key, cfg in self.portfolio.items():
            outcomes = query_outcomes(query=biz_key, limit=10)
            total = len(outcomes)
            success_count = sum(1 for o in outcomes if o.get("success", True))
            success_rate = (success_count / total) if total > 0 else 1.0

            # Consult book wisdom for strategic leverage
            wisdom = wisdom_integrator.consult_wisdom(
                situation=f"Stratégie de croissance et rentabilité pour {cfg['name']} ({cfg['type']})",
                limit_lessons=2,
            )
            lessons = [l["content"][:250].replace("\n", " ") for l in wisdom.get("book_lessons", [])]

            # Formulate 2-3 concrete recommendations
            if biz_key == "fitness_app":
                recs = [
                    "Automatiser une notification de félicitations après la 3ème séance complétée pour fixer l'habitude.",
                    "Lancer un questionnaire court aux utilisateurs inactifs depuis 48h.",
                ]
                task_to_delegate = {
                    "command": "support",
                    "params": {"query": "Vérifier le statut d'onboarding des utilisateurs actifs"},
                }
            elif biz_key == "website_agency":
                recs = [
                    "Lancer la prospection ciblée sur les électriciens et plombiers en région avec pré-scan RGPD.",
                    "Proposer le paiement en 12 fois (229€/mois) comme argument d'étalement dans le devis.",
                ]
                task_to_delegate = {
                    "command": "prospect",
                    "params": {"sectors": ["btp", "menuisier", "electricien", "plombier"], "region": "France", "limit": 50},
                }
            else:
                recs = [
                    "Publier une étude de cas client sur LinkedIn mettant en avant le gain de temps opérationnel.",
                    "Préparer la newsletter hebdomadaire orientée souveraineté et conformité.",
                ]
                task_to_delegate = {
                    "command": "content",
                    "params": {"topic": "Retour d'expérience artisan digitalisation", "platform": "linkedin"},
                }

            report["businesses"][biz_key] = {
                "name": cfg["name"],
                "type": cfg["type"],
                "recent_runs": total,
                "success_rate": f"{success_rate:.0%}",
                "strategic_recommendations": recs,
                "wisdom_insights": lessons,
            }
            report["delegated_actions"].append(task_to_delegate)

        report["top_priorities"] = [
            "1. Agence Web : Lancer le batch de 50 prospects BTP et envoyer les pré-audits RGPD.",
            "2. Social Media : Publier le post d'étude de cas client validé à 10h mardi.",
            "3. Fitness App : Vérifier la conversion du parcours onboarding et lever les frictions.",
        ]

        return report

    def plan_objective(
        self,
        goal_type: str,
        target_description: str,
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        """Decompose a high-level strategic goal into delegated OpenClaw tasks."""
        gt = (goal_type or "revenue").lower().strip()
        subtasks: List[Dict[str, Any]] = []

        if "rev" in gt or "prospect" in gt or "lead" in gt or "agence" in gt:
            subtasks = [
                {
                    "title": "Daily B2B Target Prospection",
                    "schedule": "0 9 * * *",
                    "command": "prospect",
                    "params": {
                        "sectors": ["btp", "menuisier", "electricien", "plombier", "artisan"],
                        "region": "France",
                        "limit": 50,
                    },
                    "expected_outcome": "50 new qualified leads discovered per day recorded in Qdrant",
                },
                {
                    "title": "High-Priority Compliance Pre-Audit",
                    "schedule": "0 14 * * 2,4",
                    "command": "audit",
                    "params": {"url": "https://sitedigitalpro.com", "full": False},
                    "expected_outcome": "Weekly RGPD benchmark scan to qualify pain points",
                },
            ]
        elif "content" in gt or "media" in gt or "brand" in gt:
            subtasks = [
                {
                    "title": "Weekly Strategic Content Plan",
                    "schedule": "0 10 * * 1",
                    "command": "content",
                    "params": {
                        "topic": "Transformation numérique et conformité RGPD pour artisans",
                        "platform": "linkedin",
                    },
                    "expected_outcome": "Publishable LinkedIn post and newsletter brief generated",
                },
                {
                    "title": "Mid-Week Industry Case Study",
                    "schedule": "0 11 * * 3",
                    "command": "content",
                    "params": {
                        "topic": "Retour d'expérience refonte site web artisan",
                        "platform": "linkedin",
                    },
                    "expected_outcome": "Engaging social post with practical ROI numbers",
                },
            ]
        else:
            subtasks = [
                {
                    "title": "Fitness Retention & Coaching Check",
                    "schedule": "0 8 * * *",
                    "command": "support",
                    "params": {"context": target_description},
                    "expected_outcome": "Automated check on user engagement and retention",
                }
            ]

        # Extract wisdom support
        wisdom = wisdom_integrator.consult_wisdom(target_description, limit_lessons=2)
        lessons = [l["content"][:200] for l in wisdom.get("book_lessons", [])]

        return {
            "strategic_goal": {
                "type": gt,
                "description": target_description,
                "horizon_days": horizon_days,
            },
            "delegated_openclaw_tasks": subtasks,
            "wisdom_principles": lessons,
            "centralized_cron_instructions": [
                f"Schedule '{t['title']}' on Hermes cron with schedule '{t['schedule']}' executing openclaw_execute(command='{t['command']}', params={t['params']})"
                for t in subtasks
            ],
        }


planner = StrategicPlanner()


def strategic_planner_tool(
    mode: str = "review",
    goal_type: Optional[str] = None,
    description: Optional[str] = None,
    horizon_days: int = 30,
) -> str:
    """Tool entrypoint for Hermes strategic planner 2.0."""
    m = (mode or "review").strip().lower()

    if m == "review" or not description:
        res = planner.weekly_business_review()
        return json.dumps(res, ensure_ascii=False, indent=2)

    plan = planner.plan_objective(
        goal_type=goal_type or "revenue",
        target_description=description,
        horizon_days=horizon_days,
    )
    return json.dumps(plan, ensure_ascii=False, indent=2)


PLANNER_SCHEMA = {
    "name": "strategic_business_planner",
    "description": (
        "Hermes 2.0 CEO Strategic Planner. Capabilities:\n"
        "- mode='review': Comprehensive weekly audit of the 3 businesses (Fitness, Web Agency, Social Media) "
        "with recent metrics, Qdrant outcome history, and wisdom-backed recommendations.\n"
        "- mode='plan_goal': Decompose a specific business target into scheduled OpenClaw delegated tasks "
        "and entrepreneurial principles."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["review", "plan_goal"],
                "description": "Planning mode: 'review' (weekly portfolio review) or 'plan_goal' (decompose target).",
                "default": "review",
            },
            "goal_type": {
                "type": "string",
                "enum": ["revenue", "content", "support", "custom"],
                "description": "Category when planning a specific goal.",
            },
            "description": {
                "type": "string",
                "description": "Target description (required if mode='plan_goal').",
            },
            "horizon_days": {
                "type": "integer",
                "description": "Planning horizon in days (default: 30).",
                "default": 30,
            },
        },
        "required": [],
    },
}

registry.register(
    name="strategic_business_planner",
    toolset="planning",
    schema=PLANNER_SCHEMA,
    handler=lambda args, **kw: strategic_planner_tool(
        mode=args.get("mode", "review"),
        goal_type=args.get("goal_type"),
        description=args.get("description"),
        horizon_days=int(args.get("horizon_days", 30)),
    ),
    check_fn=lambda: True,
    emoji="🎯",
)
