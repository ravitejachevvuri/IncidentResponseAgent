"""Groq LLM client (OpenAI-compatible chat completions API).

Returns None on any failure (missing key, network error, invalid JSON, action not
in the allowlist) so the caller can fall back to the deterministic recommendation
path. Per spec: an LLM response must never bypass backend validation.
"""
import json
import logging

import requests

from app.config import settings
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt, ALLOWED_ACTIONS

logger = logging.getLogger(__name__)

REQUIRED_KEYS = {
    "recommended_action",
    "target",
    "reason",
    "evidence",
    "warnings",
    "alternative_actions",
    "risk",
}


def _validate(payload: dict) -> bool:
    if not REQUIRED_KEYS.issubset(payload.keys()):
        return False
    if payload["recommended_action"] not in ALLOWED_ACTIONS:
        return False
    if payload["risk"] not in ("low", "medium", "high"):
        return False
    if not isinstance(payload["evidence"], list) or not isinstance(payload["warnings"], list):
        return False
    return True


def generate_recommendation(context: dict) -> dict | None:
    if not settings.groq_api_key:
        logger.info("GROQ_API_KEY not set; using deterministic fallback")
        return None

    try:
        response = requests.post(
            f"{settings.groq_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": settings.groq_model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(context)},
                ],
            },
            timeout=15,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(content)
        if not _validate(payload):
            logger.warning("LLM response failed validation: %s", payload)
            return None
        payload["evidence"] = [str(e) for e in payload["evidence"]]
        payload["alternative_actions"] = [
            a for a in payload.get("alternative_actions", []) if a in ALLOWED_ACTIONS
        ]
        return payload
    except Exception:
        logger.exception("LLM call failed; using deterministic fallback")
        return None
