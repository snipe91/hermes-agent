#!/usr/bin/env python3
"""
Unit tests for Hermes-OpenClaw integration components:
- tools/openclaw_tool.py
- memory/qdrant_reader.py
- monitoring/health_checker.py
- agent/strategic_planner.py
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from agent.strategic_planner import StrategicPlanner
from memory.qdrant_reader import get_embedding, qdrant_outcomes_tool, query_outcomes
from monitoring.health_checker import check_all_services, ping_service
from tools.openclaw_tool import openclaw_execute


class TestOpenClawTool:
    def test_openclaw_execute_requires_command(self):
        res = openclaw_execute(command="")
        assert "is required" in res

    @patch("urllib.request.urlopen")
    def test_openclaw_execute_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "success": True,
            "command": "prospect",
            "result": {"leads": 50},
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        out = openclaw_execute(command="prospect", params={"limit": 50})
        data = json.loads(out)
        assert data["success"] is True
        assert data["command"] == "prospect"
        assert data["result"]["leads"] == 50

    @patch("urllib.request.urlopen")
    def test_openclaw_execute_unreachable(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        out = openclaw_execute(command="status")
        assert "unreachable" in out.lower()


class TestQdrantReader:
    def test_get_embedding_deterministic_length(self):
        vec = get_embedding("Test embedding text")
        assert len(vec) == 768
        assert isinstance(vec[0], float)

    @patch("urllib.request.urlopen")
    def test_query_outcomes_parses_results(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "result": [
                {
                    "id": "1",
                    "score": 0.92,
                    "payload": {
                        "task": "prospect",
                        "result": {"leads": 12},
                        "timestamp": 123456789,
                    },
                }
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        outcomes = query_outcomes("prospection")
        assert len(outcomes) == 1
        assert outcomes[0]["task"] == "prospect"
        assert outcomes[0]["score"] == 0.92

    def test_qdrant_tool_empty_query(self):
        res = qdrant_outcomes_tool(query="")
        assert "query string is required" in res


class TestHealthChecker:
    @patch("urllib.request.urlopen")
    def test_ping_service_healthy(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status":"ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = ping_service("http://localhost:3001/health")
        assert res["status"] == "healthy"
        assert res["reachable"] is True

    @patch("monitoring.health_checker.ping_service")
    def test_check_all_services_aggregated(self, mock_ping):
        mock_ping.return_value = {"status": "healthy", "reachable": True, "statusCode": 200}
        report = check_all_services()
        assert report["overall"] == "healthy"
        assert "openclaw_api" in report["services"]
        assert "qdrant" in report["services"]
        assert "ollama" in report["services"]


class TestStrategicPlanner:
    def test_plan_revenue_goal(self):
        planner = StrategicPlanner()
        plan = planner.plan_objective("revenue", "Acquérir 100 clients artisans", 30)

        assert plan["strategic_goal"]["type"] == "revenue"
        assert len(plan["delegated_openclaw_tasks"]) >= 1
        assert plan["delegated_openclaw_tasks"][0]["command"] == "prospect"
        assert "0 9 * * *" in plan["delegated_openclaw_tasks"][0]["schedule"]

    def test_plan_content_goal(self):
        planner = StrategicPlanner()
        plan = planner.plan_objective("content", "Campagne LinkedIn RGPD", 14)

        assert plan["strategic_goal"]["type"] == "content"
        assert plan["delegated_openclaw_tasks"][0]["command"] == "content"
