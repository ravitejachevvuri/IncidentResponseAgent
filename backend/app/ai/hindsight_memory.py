"""Hindsight integration: the memory layer for this app.

Hindsight (https://hindsight.vectorize.io) is used for the two things it is
built for:
  - retain(): write each resolved incident's narrative into memory - a real
    memory update, not just a SQL insert.
  - recall(): find similar past incidents by meaning, not just exact field
    matches, to power the "Similar Incidents" panel.
  - reflect(): generate the actual recommendation, reasoning over retained
    memory with a bank mission tuned for SRE incident response.

Everything here degrades gracefully to `None`/`[]` if Hindsight isn't
configured or a call fails, so the rest of the app (Postgres-based structured
data + the deterministic fallback) keeps working regardless.

A fresh client is constructed for every call rather than cached: the SDK
builds its REST/aiohttp machinery at construction time bound to whatever
thread/event-loop is active then, and FastAPI dispatches sync route handlers
across a worker thread pool, so a single cached client intermittently breaks
with "Timeout context manager should be used inside a task" once a different
thread reuses it. Construction itself makes no network calls, so this is
cheap; each client is explicitly closed after use to avoid leaking aiohttp
sessions.
"""
import logging
import re

from hindsight_client import Hindsight

from app.config import settings
from app.ai.prompts import ALLOWED_ACTIONS

logger = logging.getLogger(__name__)

_banks_ready: set[str] = set()

RECOMMENDATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_action": {"type": "string", "enum": ALLOWED_ACTIONS},
        "target": {"type": "string"},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "alternative_actions": {"type": "array", "items": {"type": "string"}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "recommended_action",
        "target",
        "reason",
        "evidence",
        "warnings",
        "alternative_actions",
        "risk",
    ],
}


def is_configured() -> bool:
    return bool(settings.hindsight_api_key and settings.hindsight_base_url)


def get_client() -> Hindsight | None:
    if not is_configured():
        return None
    return Hindsight(base_url=settings.hindsight_base_url, api_key=settings.hindsight_api_key)


def bank_id_for_service(service_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", service_name.lower()).strip("-") or "service"
    return f"incident-memory-{slug}"


def _ensure_bank(client: Hindsight, service_name: str) -> str:
    bank_id = bank_id_for_service(service_name)
    if bank_id in _banks_ready:
        return bank_id
    try:
        client.create_bank(
            bank_id=bank_id,
            name=f"{service_name} incident memory",
            mission=(
                f"Operational memory for {service_name} production incidents: what happened, "
                "what actions engineers tried, and whether those actions actually worked."
            ),
            retain_mission=(
                "Extract the incident's symptoms, root cause, the remediation action taken, and "
                "its outcome (successful, partial, temporary, or failed)."
            ),
            reflect_mission=(
                f"You are an SRE incident-response advisor for {service_name}. Given a new "
                "incident, recommend exactly one remediation action grounded in retained incident "
                "history. Always warn explicitly when a similar past action was only temporary or "
                "failed. Never recommend a deployment rollback unless the current incident itself "
                "has a recent-deployment signal."
            ),
            disposition_skepticism=4,
        )
    except Exception:
        logger.info("create_bank for %s skipped (likely already exists)", bank_id)
    _banks_ready.add(bank_id)
    return bank_id


def reset_bank(service_name: str) -> None:
    """Delete a service's memory bank so demo reset also clears Hindsight state,
    not just Postgres, avoiding duplicate memories from repeated resets."""
    client = get_client()
    if client is None:
        return
    bank_id = bank_id_for_service(service_name)
    try:
        client.delete_bank(bank_id)
    except Exception:
        logger.info("delete_bank for %s skipped (likely did not exist)", bank_id)
    finally:
        _banks_ready.discard(bank_id)
        client.close()


def retain_incident_memory(
    service_name: str, content: str, metadata: dict[str, str], tags: list[str] | None = None
) -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        bank_id = _ensure_bank(client, service_name)
        client.retain(bank_id=bank_id, content=content, metadata=metadata, tags=tags)
        return True
    except Exception:
        logger.exception("Hindsight retain failed for service %s", service_name)
        return False
    finally:
        client.close()


def recall_similar_incidents(service_name: str, query: str, max_tokens: int = 3000) -> list:
    client = get_client()
    if client is None:
        return []
    try:
        bank_id = _ensure_bank(client, service_name)
        response = client.recall(bank_id=bank_id, query=query, budget="mid", max_tokens=max_tokens)
        return response.results or []
    except Exception:
        logger.exception("Hindsight recall failed for service %s", service_name)
        return []
    finally:
        client.close()


def reflect_recommendation(service_name: str, query: str, context_text: str) -> dict | None:
    client = get_client()
    if client is None:
        return None
    try:
        bank_id = _ensure_bank(client, service_name)
        response = client.reflect(
            bank_id=bank_id,
            query=query,
            context=context_text,
            budget="mid",
            response_schema=RECOMMENDATION_RESPONSE_SCHEMA,
        )
        if response.structured_output_error:
            logger.warning("Hindsight reflect structured_output_error: %s", response.structured_output_error)
            return None
        return response.structured_output
    except Exception:
        logger.exception("Hindsight reflect failed for service %s", service_name)
        return None
    finally:
        client.close()
