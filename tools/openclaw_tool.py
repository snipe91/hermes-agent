#!/usr/bin/env python3
"""
OpenClaw Bridge Tool for Hermes Agent.

Allows Hermes (Strategic Leader) to command OpenClaw (Specialized Backend Executor)
over HTTP without relying on autonomous crons in OpenClaw.

Tasks supported:
- prospection (SIRENE, Google, Pages Jaunes, B2B leads)
- content (writing, social publications, newsletter)
- audit (RGPD scan, compliance check)
- support (customer support, knowledge base query)
- status (agent health, integrations, active runs)
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

OPENCLAW_DEFAULT_URL = os.getenv("OPENCLAW_API_URL", "http://127.0.0.1:3001")


def openclaw_execute(
    command: str,
    params: Optional[Dict[str, Any]] = None,
    api_url: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """Execute a business task on the OpenClaw backend engine.

    Args:
        command: Action to run ('prospect', 'content', 'audit', 'support', 'status', 'custom')
        params: Task parameters (e.g. target, sectors, location, limit, url, topic)
        api_url: Base URL of OpenClaw API (defaults to http://127.0.0.1:3001)
        timeout: Request timeout in seconds (default 120)

    Returns:
        JSON string containing the execution result from OpenClaw.
    """
    cmd = (command or "").strip().lower()
    if not cmd:
        return tool_error("command is required ('prospect', 'content', 'audit', 'support', 'status', 'custom').")

    base_url = (api_url or OPENCLAW_DEFAULT_URL).rstrip("/")
    endpoint = f"{base_url}/api/execute"
    payload = {
        "command": cmd,
        "params": params or {},
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Hermes-Leader-Agent/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            body = response.read().decode("utf-8")
            try:
                parsed = json.loads(body)
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return json.dumps({"success": True, "raw_response": body}, ensure_ascii=False)

    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8", errors="replace")
        logger.warning("OpenClaw HTTP %s error: %s", http_err.code, err_body)
        return tool_error(f"OpenClaw returned HTTP {http_err.code}: {err_body}")

    except urllib.error.URLError as url_err:
        logger.warning("Could not reach OpenClaw at %s: %s", endpoint, url_err.reason)
        return tool_error(
            f"OpenClaw backend is unreachable at {base_url}. "
            "Make sure openclaw-brain API server is running on port 3001 (npm run start or npm run dev). "
            f"Details: {url_err.reason}"
        )

    except Exception as exc:
        logger.error("Unexpected error contacting OpenClaw: %s", exc)
        return tool_error(f"Unexpected error communicating with OpenClaw: {str(exc)}")


def check_openclaw_requirements() -> bool:
    """OpenClaw tool is always available; backend reachability is handled at runtime."""
    return True


OPENCLAW_SCHEMA = {
    "name": "openclaw_execute",
    "description": (
        "Command the OpenClaw backend execution engine to perform specialized business tasks. "
        "Hermes acts as the strategic leader and delegates work to OpenClaw without autonomous cron conflicts. "
        "Supported commands:\n"
        "- 'prospect': B2B lead hunting via SIRENE & Google (params: sectors, region, limit/batchSize)\n"
        "- 'content': Generate and plan marketing/social content (params: topic, platform)\n"
        "- 'audit': Scan websites for RGPD and compliance defects (params: url, full: bool)\n"
        "- 'support': Answer client support and knowledge base questions (params: query, context)\n"
        "- 'status': Report health, agent registry, and integration state\n"
        "- 'custom': Run any custom agent event (params: type, payload)"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["prospect", "content", "audit", "support", "status", "custom"],
                "description": "The business task command to delegate to OpenClaw.",
            },
            "params": {
                "type": "object",
                "description": (
                    "Parameters for the task (e.g., {'sectors': ['btp', 'plombier'], 'region': 'Lyon', 'limit': 20} "
                    "or {'url': 'https://example.com'} for audit, or {'topic': 'IA & PME'} for content)."
                ),
            },
        },
        "required": ["command"],
    },
}

registry.register(
    name="openclaw_execute",
    toolset="openclaw",
    schema=OPENCLAW_SCHEMA,
    handler=lambda args, **kw: openclaw_execute(
        command=args.get("command", ""),
        params=args.get("params"),
    ),
    check_fn=check_openclaw_requirements,
    emoji="🦞",
)
