#!/usr/bin/env python3
"""
Strategic Business Planner for Hermes Agent.

Enables Hermes to act as the autonomous leader:
- Sets high-level objectives (revenue, content, compliance audits)
- Decomposes them into actionable task definitions for OpenClaw
- Formulates execution schedules and parameters for cron centralisation
"""

import json
import logging
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


class StrategicPlanner:
    """Strategic goal decomposition engine for Hermes."""

    def plan_objective(
        self,
        goal_type: str,
        target_description: str,
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        """Decompose a high-level strategic goal into delegated OpenClaw tasks."""
        gt = (goal_type or "revenue").lower().strip()
        subtasks: List[Dict[str, Any]] = []

        if "rev" in gt or "prospect" in gt or "lead" in gt:
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
        elif "support" in gt or "qa" in gt or "quality" in gt:
            subtasks = [
                {
                    "title": "Knowledge Base & Agent Status Check",
                    "schedule": "0 8 * * *",
                    "command": "status",
                    "params": {},
                    "expected_outcome": "Status report on all 11 active business agents and integrations",
                }
            ]
        else:
            subtasks = [
                {
                    "title": "General Task Execution",
                    "schedule": "0 9 * * 1-5",
                    "command": "status",
                    "params": {"goal": target_description},
                    "expected_outcome": "Routine operational check",
                }
            ]

        return {
            "strategic_goal": {
                "type": gt,
                "description": target_description,
                "horizon_days": horizon_days,
            },
            "delegated_openclaw_tasks": subtasks,
            "centralized_cron_instructions": [
                f"Schedule '{t['title']}' on Hermes cron with schedule '{t['schedule']}' executing openclaw_execute(command='{t['command']}', params={t['params']})"
                for t in subtasks
            ],
        }


planner = StrategicPlanner()


def strategic_planner_tool(
    goal_type: str,
    description: str,
    horizon_days: int = 30,
) -> str:
    """Tool entrypoint for Hermes strategic planner."""
    if not description:
        return tool_error("description of the goal is required.")

    plan = planner.plan_objective(
        goal_type=goal_type,
        target_description=description,
        horizon_days=horizon_days,
    )
    return json.dumps(plan, ensure_ascii=False, indent=2)


PLANNER_SCHEMA = {
    "name": "strategic_business_planner",
    "description": (
        "Decompose a high-level strategic business objective into concrete delegated tasks "
        "for the OpenClaw execution engine, complete with optimal Hermes cron schedules and parameters. "
        "Helps Hermes act as the strategic leader without manual micromanagement."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal_type": {
                "type": "string",
                "enum": ["revenue", "content", "support", "custom"],
                "description": "Category of the goal (revenue/prospection, content/social, support/qa).",
            },
            "description": {
                "type": "string",
                "description": "Specific business goal (e.g. 'Générer 200 leads qualifiés artisans ce mois', 'Publier 8 posts LinkedIn B2B').",
            },
            "horizon_days": {
                "type": "integer",
                "description": "Planning horizon in days (default: 30).",
                "default": 30,
            },
        },
        "required": ["goal_type", "description"],
    },
}

registry.register(
    name="strategic_business_planner",
    toolset="planning",
    schema=PLANNER_SCHEMA,
    handler=lambda args, **kw: strategic_planner_tool(
        goal_type=args.get("goal_type", "revenue"),
        description=args.get("description", ""),
        horizon_days=int(args.get("horizon_days", 30)),
    ),
    check_fn=lambda: True,
    emoji="🎯",
)
