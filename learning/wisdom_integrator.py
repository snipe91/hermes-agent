#!/usr/bin/env python3
"""
Wisdom Integrator for Hermes Agent.

Connects Hermes directly to the 66,746+ book chunks stored in Qdrant (`book_knowledge` collection).
Extracts actionable entrepreneurial principles to guide strategic decision-making,
and persists synthesized business action rules in the `business_rules` collection.
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
BOOK_COLLECTION = "book_knowledge"
RULES_COLLECTION = "business_rules"
VECTOR_SIZE = 768


def get_embedding(text: str, ollama_url: Optional[str] = None) -> List[float]:
    """Compute normalized 768-dim vector via Ollama nomic-embed-text or deterministic fallback."""
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
        logger.debug("Ollama embedding failed, using deterministic fallback: %s", exc)

    # Fallback deterministic vector
    vec = [0.0] * VECTOR_SIZE
    h = 0
    for char in text:
        h = ((h << 5) - h + ord(char)) & 0xFFFFFFFF
        vec[h % VECTOR_SIZE] += 0.01

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class WisdomIntegrator:
    """Queries entrepreneur books and maintains codified business rules."""

    def __init__(self, qdrant_url: Optional[str] = None, ollama_url: Optional[str] = None):
        self.qdrant_url = (qdrant_url or QDRANT_DEFAULT_URL).rstrip("/")
        self.ollama_url = (ollama_url or OLLAMA_DEFAULT_URL).rstrip("/")
        self._rules_collection_checked = False

    def ensure_rules_collection(self) -> bool:
        """Ensure the `business_rules` collection exists in Qdrant."""
        if self._rules_collection_checked:
            return True
        try:
            req = urllib.request.Request(f"{self.qdrant_url}/collections/{RULES_COLLECTION}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    self._rules_collection_checked = True
                    return True
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                create_payload = {
                    "vectors": {
                        "size": VECTOR_SIZE,
                        "distance": "Cosine",
                    }
                }
                create_req = urllib.request.Request(
                    f"{self.qdrant_url}/collections/{RULES_COLLECTION}",
                    data=json.dumps(create_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                try:
                    with urllib.request.urlopen(create_req, timeout=10) as cresp:
                        if cresp.status in (200, 201):
                            logger.info("Created Qdrant collection '%s'", RULES_COLLECTION)
                            self._rules_collection_checked = True
                            return True
                except Exception as ce:
                    logger.warning("Could not create collection %s: %s", RULES_COLLECTION, ce)
        except Exception as e:
            logger.debug("Qdrant check failed: %s", e)
        return False

    def search_books(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search the 66,746 book chunks in Qdrant."""
        endpoint = f"{self.qdrant_url}/collections/{BOOK_COLLECTION}/points/search"
        vector = get_embedding(query, self.ollama_url)

        payload = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                results = res_data.get("result", [])
                lessons = []
                for r in results:
                    p = r.get("payload", {})
                    content = p.get("_content") or p.get("text") or ""
                    if content:
                        lessons.append({
                            "content": content.strip(),
                            "source": p.get("source") or p.get("filename") or "Unknown Book",
                            "category": p.get("category", "general"),
                            "score": round(r.get("score", 0.0), 3),
                        })
                return lessons
        except Exception as exc:
            logger.warning("Search in book_knowledge failed: %s", exc)
            return []

    def search_rules(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search codified action rules in Qdrant."""
        if not self.ensure_rules_collection():
            return []
        endpoint = f"{self.qdrant_url}/collections/{RULES_COLLECTION}/points/search"
        vector = get_embedding(query, self.ollama_url)

        payload = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return [r.get("payload", {}) for r in res_data.get("result", [])]
        except Exception as exc:
            logger.debug("Search in business_rules failed: %s", exc)
            return []

    def save_action_rule(
        self,
        theme: str,
        situation: str,
        action: str,
        reason: str,
        source_book: Optional[str] = None,
    ) -> bool:
        """Persist a codified SI-ALORS-PARCE QUE rule in Qdrant."""
        if not self.ensure_rules_collection():
            return False
        import uuid
        rule_id = str(uuid.uuid4())
        full_text = f"SI {situation} ALORS {action} PARCE QUE {reason}"
        vector = get_embedding(full_text, self.ollama_url)

        point_payload = {
            "theme": theme,
            "situation": situation,
            "action": action,
            "reason": reason,
            "rule_text": full_text,
            "source_book": source_book or "Entrepreneur Wisdom",
        }

        req = urllib.request.Request(
            f"{self.qdrant_url}/collections/{RULES_COLLECTION}/points?wait=true",
            data=json.dumps({"points": [{"id": rule_id, "vector": vector, "payload": point_payload}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 201)
        except Exception as exc:
            logger.warning("Could not save action rule: %s", exc)
            return False

    def consult_wisdom(self, situation: str, limit_lessons: int = 4) -> Dict[str, Any]:
        """Consult both codified rules and original book excerpts for a situation."""
        rules = self.search_rules(situation, limit=3)
        lessons = self.search_books(situation, limit=limit_lessons)
        return {
            "situation": situation,
            "codified_rules": rules,
            "book_lessons": lessons,
            "recommendation_prompt": self._format_wisdom_for_prompt(rules, lessons),
        }

    def _format_wisdom_for_prompt(self, rules: List[Dict[str, Any]], lessons: List[Dict[str, Any]]) -> str:
        lines = []
        if rules:
            lines.append("RÈGLES D'ACTION CODIFIÉES :")
            for r in rules:
                lines.append(f"- {r.get('rule_text', '')}")
        if lessons:
            lines.append("\nEXTRAITS DE LIVRES D'ENTREPRENEURS :")
            for idx, l in enumerate(lessons, 1):
                snippet = l['content'].replace("\n", " ")[:300]
                lines.append(f"{idx}. [{l['source']}] {snippet}...")
        return "\n".join(lines)


wisdom_integrator = WisdomIntegrator()


def consult_wisdom_tool(situation: str, limit: int = 4) -> str:
    """Tool entrypoint for Hermes to consult business wisdom from Qdrant."""
    s = (situation or "").strip()
    if not s:
        return tool_error("situation description is required.")

    result = wisdom_integrator.consult_wisdom(situation=s, limit_lessons=limit)
    return json.dumps(result, ensure_ascii=False, indent=2)


WISDOM_SCHEMA = {
    "name": "consult_business_wisdom",
    "description": (
        "Search the 66,746+ book chunks in Qdrant (Alex Hormozi, Brian Tracy, Scaling Challenges, etc.) "
        "and codified business rules to provide battle-tested entrepreneurial guidance on any challenge "
        "(growth, pricing, marketing, client retention, closing, operational efficiency)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "situation": {
                "type": "string",
                "description": "The operational problem or strategic question (e.g., 'augmenter la rétention d'une app', 'conversion prospection B2B', 'tarification récurrente').",
            },
            "limit": {
                "type": "integer",
                "description": "Number of book excerpts to retrieve (default: 4).",
                "default": 4,
            },
        },
        "required": ["situation"],
    },
}

registry.register(
    name="consult_business_wisdom",
    toolset="learning",
    schema=WISDOM_SCHEMA,
    handler=lambda args, **kw: consult_wisdom_tool(
        situation=args.get("situation", ""),
        limit=int(args.get("limit", 4)),
    ),
    check_fn=lambda: True,
    emoji="📚",
)
