#!/usr/bin/env python3
"""
System Health Checker & Auto-Monitoring for Hermes Agent.

Continuously verifies connectivity and status of the unified ecosystem:
- OpenClaw API server (default port 3001)
- Qdrant Vector Engine (default port 6333)
- Ollama Local LLM / Embeddings (default port 11434)

Exposes tool `system_health_check` for Hermes.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from tools.registry import registry

logger = logging.getLogger(__name__)

OPENCLAW_URL = os.getenv("OPENCLAW_API_URL", "http://127.0.0.1:3001")
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")


def ping_service(url: str, timeout: int = 5) -> Dict[str, Any]:
    """Check connectivity to an HTTP service endpoint."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Hermes-HealthChecker/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            try:
                data = json.loads(body)
            except Exception:
                data = {"raw": body[:200]}
            return {
                "status": "healthy",
                "statusCode": resp.status,
                "reachable": True,
                "data": data,
            }
    except urllib.error.HTTPError as http_err:
        return {
            "status": "degraded",
            "statusCode": http_err.code,
            "reachable": True,
            "error": f"HTTP {http_err.code}",
        }
    except Exception as exc:
        return {
            "status": "down",
            "reachable": False,
            "error": str(exc),
        }


def check_all_services() -> Dict[str, Any]:
    """Audit all core services in the ecosystem."""
    openclaw_health = ping_service(f"{OPENCLAW_URL.rstrip('/')}/health")
    qdrant_health = ping_service(f"{QDRANT_URL.rstrip('/')}/collections")
    ollama_health = ping_service(f"{OLLAMA_URL.rstrip('/')}/api/tags")

    services = {
        "openclaw_api": {
            "url": OPENCLAW_URL,
            **openclaw_health,
        },
        "qdrant": {
            "url": QDRANT_URL,
            **qdrant_health,
        },
        "ollama": {
            "url": OLLAMA_URL,
            **ollama_health,
        },
    }

    down_count = sum(1 for s in services.values() if s["status"] == "down")
    degraded_count = sum(1 for s in services.values() if s["status"] == "degraded")

    if down_count == 0 and degraded_count == 0:
        overall = "healthy"
    elif down_count == 0:
        overall = "degraded"
    else:
        overall = "critical" if down_count > 1 else "degraded"

    recovery_actions = []
    if services["openclaw_api"]["status"] == "down":
        recovery_actions.append(
            "Start OpenClaw API: run 'npm run dev' or 'node dist/super-intelligence-bootstrap.js' in openclaw-brain-v3"
        )
    if services["qdrant"]["status"] == "down":
        recovery_actions.append(
            "Start Qdrant: run 'docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant'"
        )
    if services["ollama"]["status"] == "down":
        recovery_actions.append(
            "Start Ollama: run 'ollama serve' in your terminal"
        )

    return {
        "overall": overall,
        "services": services,
        "recovery_actions": recovery_actions,
    }


def system_health_tool() -> str:
    """Entry point for Hermes system_health_check tool."""
    report = check_all_services()
    return json.dumps(report, ensure_ascii=False, indent=2)


HEALTH_SCHEMA = {
    "name": "system_health_check",
    "description": (
        "Check system health and connectivity of all coordinated services: "
        "OpenClaw Backend API (port 3001), Qdrant Vector Engine (port 6333), and Ollama (port 11434). "
        "Returns service status, HTTP codes, and auto-recovery instructions if any service is down."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

registry.register(
    name="system_health_check",
    toolset="monitoring",
    schema=HEALTH_SCHEMA,
    handler=lambda args, **kw: system_health_tool(),
    check_fn=lambda: True,
    emoji="🩺",
)
