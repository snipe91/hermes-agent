#!/usr/bin/env python3
"""
Unit tests for Strategic Planner 2.0 in Hermes Agent.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from agent.strategic_planner import StrategicPlanner, strategic_planner_tool


class TestStrategicPlanner2:
    @patch("agent.strategic_planner.query_outcomes")
    @patch("agent.strategic_planner.wisdom_integrator.consult_wisdom")
    def test_weekly_business_review_structure(self, mock_wisdom, mock_outcomes):
        mock_outcomes.return_value = [
            {"task": "fitness_app", "success": True},
            {"task": "fitness_app", "success": False},
        ]
        mock_wisdom.return_value = {
            "codified_rules": [],
            "book_lessons": [{"content": "Focus sur l'acquisition client par la valeur.", "source": "Challenge Scaling"}],
        }

        planner = StrategicPlanner()
        review = planner.weekly_business_review()

        assert "fitness_app" in review["businesses"]
        assert "website_agency" in review["businesses"]
        assert "social_media" in review["businesses"]
        assert len(review["top_priorities"]) == 3
        assert len(review["delegated_actions"]) == 3

    @patch("agent.strategic_planner.wisdom_integrator.consult_wisdom")
    def test_plan_goal_mode(self, mock_wisdom):
        mock_wisdom.return_value = {
            "codified_rules": [],
            "book_lessons": [{"content": "Standardiser les livrables.", "source": "Hormozi 100M Offers"}],
        }

        planner = StrategicPlanner()
        plan = planner.plan_objective(
            goal_type="revenue",
            target_description="Générer 100 leads qualifiés",
            horizon_days=30,
        )

        assert plan["strategic_goal"]["type"] == "revenue"
        assert len(plan["delegated_openclaw_tasks"]) >= 1
        assert "0 9 * * *" in plan["delegated_openclaw_tasks"][0]["schedule"]

    @patch.object(StrategicPlanner, "weekly_business_review")
    def test_tool_entrypoint_review(self, mock_review):
        mock_review.return_value = {"status": "ok", "businesses": {}}
        out = strategic_planner_tool(mode="review")
        data = json.loads(out)
        assert data["status"] == "ok"
