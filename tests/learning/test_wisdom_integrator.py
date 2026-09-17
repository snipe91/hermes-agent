#!/usr/bin/env python3
"""
Unit tests for Wisdom Integrator, Book Teacher, and Continuous Improvement in Hermes Agent.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from learning.wisdom_integrator import WisdomIntegrator, consult_wisdom_tool
from learning.book_teacher import BookTeacher, daily_lesson_tool
from learning.continuous_improvement import ContinuousImprovement, continuous_improvement_tool


class TestWisdomIntegrator:
    @patch("urllib.request.urlopen")
    def test_search_books_parses_chunks(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "result": [
                {
                    "score": 0.88,
                    "payload": {
                        "_content": "Pour augmenter la rétention, réduisez la friction.",
                        "source": "Scaling Challenge",
                        "category": "marketing",
                    },
                }
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        integrator = WisdomIntegrator()
        lessons = integrator.search_books("rétention client", limit=2)

        assert len(lessons) == 1
        assert "réduisez la friction" in lessons[0]["content"]
        assert lessons[0]["source"] == "Scaling Challenge"

    @patch.object(WisdomIntegrator, "search_books")
    @patch.object(WisdomIntegrator, "search_rules")
    def test_consult_wisdom_combines(self, mock_rules, mock_books):
        mock_rules.return_value = [{"rule_text": "SI friction ALORS simplifier PARCE QUE rétention"}]
        mock_books.return_value = [{"content": "Extrait livre", "source": "Livre 1"}]

        integrator = WisdomIntegrator()
        res = integrator.consult_wisdom("problème de churn")

        assert len(res["codified_rules"]) == 1
        assert len(res["book_lessons"]) == 1
        assert "RÈGLES D'ACTION CODIFIÉES" in res["recommendation_prompt"]


class TestBookTeacher:
    @patch.object(BookTeacher, "sample_book_chunk")
    def test_generate_daily_lesson(self, mock_chunk):
        mock_chunk.return_value = {
            "content": "La clarté bat la persuasion dans 9 cas sur 10.",
            "source": "100M Offers",
            "category": "sales",
        }

        teacher = BookTeacher()
        lesson = teacher.generate_daily_lesson()

        assert lesson["success"] is True
        assert lesson["source_book"] == "100M Offers"
        assert "fitness_app" in lesson["business_applications"]
        assert "website_agency" in lesson["business_applications"]
        assert "social_media" in lesson["business_applications"]
        assert "Telegram" in lesson or "telegram_message" in lesson


class TestContinuousImprovement:
    @patch("learning.continuous_improvement.query_outcomes")
    def test_analyze_performance_flags_degraded(self, mock_outcomes):
        mock_outcomes.return_value = [
            {"task": "audit_rgpd", "success": False},
            {"task": "audit_rgpd", "success": False},
            {"task": "content_post", "success": True},
            {"task": "content_post", "success": True},
            {"task": "content_post", "success": True},
        ]

        ci = ContinuousImprovement()
        report = ci.analyze_performance()

        assert report["success"] is True
        skills = report["skills_evaluated"]
        assert "audit_rgpd" in skills
        assert skills["audit_rgpd"]["status"] == "degraded"
        assert skills["content_post"]["status"] == "high_performing"
