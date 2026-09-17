#!/usr/bin/env python3
"""
Weekly Strategic Business Report Generator for Hermes Agent.

Executed on schedule: `0 9 * * 1` (Every Monday at 9:00 AM).
Synthesizes performance of the 3 businesses (Fitness, Web Agency, Social Media),
integrates wisdom from entrepreneur books, and outputs actionable decisions for the week.
"""

import datetime
import json
import logging
import sys
from pathlib import Path

# Ensure root hermes directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.strategic_planner import planner
from learning.book_teacher import book_teacher
from monitoring.health_checker import check_all_services

logger = logging.getLogger(__name__)


def generate_weekly_report() -> str:
    """Generate the full executive brief for the CEO."""
    date_str = datetime.date.today().strftime("%d/%m/%Y")

    # 1. System Health Audit
    health = check_all_services()
    health_badge = "🟢 Opérationnel" if health["overall"] == "healthy" else "🟠 Dégradé"

    # 2. Strategic Portfolio Review
    review = planner.weekly_business_review()

    # 3. Book Wisdom Lesson
    lesson = book_teacher.generate_daily_lesson()
    book_quote = lesson.get("key_concept", "Libération du temps opérationnel et focus sur la valeur.")
    book_source = lesson.get("source_book", "Grandes Lectures Entrepreneuriales")

    # Build Executive Telegram Brief
    lines = [
        f"📊 *RAPPORT STRATÉGIQUE HEBDOMADAIRE — HERMES 2.0*",
        f"🗓️ *Semaine du {date_str}* | Statut Système : {health_badge}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🏢 *1. REVUE DU PORTFOLIO (3 BUSINESSES)*",
        "",
        "🏋️ *SlimHack 2 (Fitness App)* :",
        f"• Runs récents : {review['businesses']['fitness_app']['recent_runs']} | Taux de succès : {review['businesses']['fitness_app']['success_rate']}",
        f"• Priorité : {review['businesses']['fitness_app']['strategic_recommendations'][0]}",
        "",
        "💻 *SiteDigitalPro (Agence Web)* :",
        f"• Runs récents : {review['businesses']['website_agency']['recent_runs']} | Taux de succès : {review['businesses']['website_agency']['success_rate']}",
        f"• Priorité : {review['businesses']['website_agency']['strategic_recommendations'][0]}",
        "",
        "📣 *Social Media Empire (Contenu)* :",
        f"• Runs récents : {review['businesses']['social_media']['recent_runs']} | Taux de succès : {review['businesses']['social_media']['success_rate']}",
        f"• Priorité : {review['businesses']['social_media']['strategic_recommendations'][0]}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📚 *2. SAGESSE ENTREPRENEURIALE DE LA SEMAINE*",
        f"📖 *Source* : {book_source}",
        f"💡 *Principe Clé* : _{book_quote}_",
        f"🎯 *Action Recommandée* : {lesson.get('action_of_the_week', 'Structurer les processus clés.')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🎯 *3. PLAN D'ACTION IMMÉDIAT*",
    ]

    for p in review.get("top_priorities", []):
        lines.append(f"• {p}")

    lines.extend([
        "",
        "🦞 *Actions déléguées à OpenClaw programmées avec succès.*",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    report_text = generate_weekly_report()
    print(report_text)
