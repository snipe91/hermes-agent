#!/usr/bin/env python3
"""
Continuous Improvement & Skill Evolver for Hermes Agent.

Audits execution performance across the ecosystem using recorded outcomes in Qdrant,
detects failure/success patterns, and consults entrepreneur book wisdom to propose
actionable skill refinements and operational optimizations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from memory.qdrant_reader import query_outcomes
from learning.wisdom_integrator import wisdom_integrator
from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


class ContinuousImprovement:
    """Evaluates task execution history and recommends operational evolution."""

    def analyze_performance(self, task_filter: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """Analyze recent outcomes from Qdrant to compute performance metrics."""
        outcomes = query_outcomes(query=task_filter or "task execution", limit=limit)
        if not outcomes:
            return {
                "success": True,
                "message": "Pas assez d'outcomes récents enregistrés dans Qdrant.",
                "tasks_analyzed": 0,
                "skills_evaluated": {},
            }

        # Group by task type
        task_stats: Dict[str, Dict[str, Any]] = {}
        for item in outcomes:
            name = item.get("task", "unknown")
            is_ok = bool(item.get("success", True))
            if name not in task_stats:
                task_stats[name] = {"total": 0, "success": 0, "failures": 0, "recent_samples": []}
            task_stats[name]["total"] += 1
            if is_ok:
                task_stats[name]["success"] += 1
            else:
                task_stats[name]["failures"] += 1
            if len(task_stats[name]["recent_samples"]) < 3:
                task_stats[name]["recent_samples"].append({
                    "success": is_ok,
                    "metadata": item.get("metadata"),
                    "timestamp": item.get("timestamp"),
                })

        evaluations: Dict[str, Any] = {}
        for name, stats in task_stats.items():
            rate = stats["success"] / stats["total"] if stats["total"] > 0 else 0.0
            status = "stable"
            recommendation = "Continuer l'exécution nominale."
            wisdom_note = None

            if rate < 0.40 and stats["total"] >= 2:
                status = "degraded"
                wisdom = wisdom_integrator.consult_wisdom(f"résoudre échec récurrent sur la tâche {name}", limit_lessons=2)
                rules = [r.get("rule_text") for r in wisdom.get("codified_rules", [])]
                lessons = [l.get("content", "")[:200] for l in wisdom.get("book_lessons", [])]
                recommendation = f"Ajuster les paramètres ou le prompt de '{name}'. Taux de succès critique ({rate:.0%})."
                wisdom_note = {"rules": rules, "book_excerpts": lessons}
            elif rate > 0.80 and stats["total"] >= 3:
                status = "high_performing"
                recommendation = f"Amplifier la fréquence de '{name}' pour maximiser les résultats (Taux {rate:.0%})."

            evaluations[name] = {
                "total_runs": stats["total"],
                "success_rate": f"{rate:.1%}",
                "status": status,
                "recommendation": recommendation,
                "wisdom_guidance": wisdom_note,
            }

        return {
            "success": True,
            "tasks_analyzed": len(outcomes),
            "skills_evaluated": evaluations,
            "summary": (
                f"{len(evaluations)} types de tâches analysés sur {len(outcomes)} runs récents. "
                f"{sum(1 for e in evaluations.values() if e['status'] == 'degraded')} nécessitent une attention."
            ),
        }


evolver = ContinuousImprovement()


def continuous_improvement_tool(task_filter: Optional[str] = None, limit: int = 30) -> str:
    """Tool entrypoint for Hermes to audit skill performance and trigger self-improvement."""
    report = evolver.analyze_performance(task_filter=task_filter, limit=limit)
    return json.dumps(report, ensure_ascii=False, indent=2)


IMPROVEMENT_SCHEMA = {
    "name": "continuous_skill_improvement",
    "description": (
        "Audit ecosystem task performance across past Qdrant execution outcomes. "
        "Identifies failing workflows (< 40% success) and high-performing ones (> 80%), "
        "and injects entrepreneur wisdom recommendations to guide autonomous self-correction."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_filter": {
                "type": "string",
                "description": "Optional filter for specific task types (e.g., 'prospect', 'content', 'audit').",
            },
            "limit": {
                "type": "integer",
                "description": "Number of recent outcomes to audit (default: 30).",
                "default": 30,
            },
        },
        "required": [],
    },
}

registry.register(
    name="continuous_skill_improvement",
    toolset="learning",
    schema=IMPROVEMENT_SCHEMA,
    handler=lambda args, **kw: continuous_improvement_tool(
        task_filter=args.get("task_filter"),
        limit=int(args.get("limit", 30)),
    ),
    check_fn=lambda: True,
    emoji="🔄",
)
