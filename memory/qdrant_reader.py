#!/usr/bin/env python3
"""
Qdrant Outcome Reader for Hermes Agent.

Provides semantic and historical querying of `business_outcomes` recorded in Qdrant
by OpenClaw or Hermes. This serves as the unified operational memory.
"""

import json
import logging
import math
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

QDRANT_DEFAULT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
OLLAMA_DEFAULT_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OUTCOMES_COLLECTION = "business_outcomes"
VECTOR_SIZE = 768


def get_embedding(text: str, ollama_url: Optional[str] = None) -> List[float]:
    """Obtain a 768-dim embedding from Ollama nomic-embed-text or return deterministic fallback."""
    base_ollama = (ollama_url or OLLAMA_DEFAULT_URL).rstrip("/")
    endpoint = f"{base_ollama}/api/embeddings"
    payload = {
        "model": os.getenv("EMBED_MODEL", "nomic-embed-text"),
        "prompt": (text or "")[:4000],
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            vec = data.get("embedding")
            if isinstance(vec, list) and len(vec) == VECTOR_SIZE:
                norm = math.sqrt(sum(v * v for v in vec)) or 1.0
                return [v / norm for v in vec]
    except Exception as exc:
        logger.debug("Ollama embedding failed, using fallback vector: %s", exc)

    # Fallback deterministic vector
    vec = [0.0] * VECTOR_SIZE
    h = 0
    for char in text:
        h = ((h << 5) - h + ord(char)) & 0xFFFFFFFF
        vec[h % VECTOR_SIZE] += 0.01

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def query_outcomes(
    query: str,
    limit: int = 10,
    qdrant_url: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search business outcomes from Qdrant vector collection.

    Args:
        query: Natural language search query or keywords.
        limit: Maximum number of points to retrieve.
        qdrant_url: Qdrant base URL.
        ollama_url: Ollama base URL.

    Returns:
        List of matching payloads with similarity scores.
    """
    base_qdrant = (qdrant_url or QDRANT_DEFAULT_URL).rstrip("/")
    endpoint = f"{base_qdrant}/collections/{OUTCOMES_COLLECTION}/points/search"

    vector = get_embedding(query, ollama_url=ollama_url)
    search_payload = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(search_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            results = res_data.get("result", [])
            out = []
            for item in results:
                payload = item.get("payload", {})
                payload["score"] = item.get("score", 0.0)
                payload["id"] = item.get("id")
                out.append(payload)
            return out
    except urllib.error.HTTPError as http_err:
        if http_err.code == 404:
            logger.info("Qdrant collection '%s' does not exist yet.", OUTCOMES_COLLECTION)
            return []
        logger.warning("Qdrant query HTTP %s: %s", http_err.code, http_err.read().decode("utf-8", errors="ignore"))
        return []
    except Exception as exc:
        logger.warning("Could not query Qdrant outcomes: %s", exc)
        return []


def qdrant_outcomes_tool(query: str, limit: int = 10) -> str:
    """Tool entrypoint for Hermes to recall past outcomes."""
    q = (query or "").strip()
    if not q:
        return tool_error("query string is required.")

    results = query_outcomes(query=q, limit=limit)
    if not results:
        return json.dumps({
            "success": True,
            "message": f"No past outcomes found in Qdrant matching '{q}'.",
            "outcomes": [],
        }, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "count": len(results),
        "outcomes": results,
    }, ensure_ascii=False, indent=2)


QDRANT_SCHEMA = {
    "name": "qdrant_outcomes",
    "description": (
        "Query the unified operational memory stored in Qdrant (business_outcomes collection). "
        "Allows Hermes to recall past execution results, prospection outcomes, and generated content "
        "to make data-informed strategic decisions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Semantic search query or keywords (e.g. 'prospection plombier Lyon', 'articles LinkedIn B2B', 'audit RGPD').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to retrieve (default: 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

registry.register(
    name="qdrant_outcomes",
    toolset="memory",
    schema=QDRANT_SCHEMA,
    handler=lambda args, **kw: qdrant_outcomes_tool(
        query=args.get("query", ""),
        limit=int(args.get("limit", 10)),
    ),
    check_fn=lambda: True,
    emoji="🧠",
)
