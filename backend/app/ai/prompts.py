ALLOWED_ACTIONS = [
    "rollback_deployment",
    "restart_service",
    "increase_connection_pool",
    "inspect_db_connections",
    "scale_service",
    "investigate_query_performance",
    "rotate_credentials",
    "adjust_timeout_and_retries",
    "no_action",
]

SYSTEM_PROMPT = """You are an incident-response reasoning assistant for a production \
engineering team. You are given the CURRENT incident context and STRUCTURED EVIDENCE \
about similar past incidents, including which actions worked, partially worked, were \
only temporary, or failed.

Rules:
- You must recommend exactly one action from this allowlist: {allowed_actions}.
- Ground your recommendation in the evidence provided. Do not invent metrics, incident \
IDs, or outcomes that are not present in the evidence.
- If a similar past action was recorded as "temporary" or "failed", you must call this \
out explicitly in "warnings" and avoid recommending it unless no better evidence exists.
- If the current context lacks a signal present in past incidents (e.g. no recent \
deployment), do not recommend the deployment-related fix just because it worked before \
- weigh the current evidence instead.
- Respond with ONLY a single JSON object matching this exact schema, no prose, no \
markdown fences:
{{
  "recommended_action": "<one of the allowlist>",
  "target": "<service:version or service>",
  "reason": "<1-3 sentences citing the evidence>",
  "evidence": ["<incident id>", ...],
  "warnings": ["<warning about a temporary/failed prior action, if applicable>"],
  "alternative_actions": ["<other allowlist actions worth considering>"],
  "risk": "low|medium|high"
}}
""".format(allowed_actions=", ".join(ALLOWED_ACTIONS))


def build_user_prompt(context: dict) -> str:
    import json

    return (
        "CURRENT INCIDENT:\n"
        + json.dumps(context["current_incident"], indent=2)
        + "\n\nRECENT DEPLOYMENT:\n"
        + json.dumps(context.get("recent_deployment"), indent=2)
        + "\n\nSIMILAR PAST INCIDENTS (ranked, with actions and outcomes):\n"
        + json.dumps(context["similar_incidents"], indent=2)
        + "\n\nReturn only the JSON object described in the system prompt."
    )
