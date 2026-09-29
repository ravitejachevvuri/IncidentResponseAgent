"""Seeds a richer historical-incident dataset across six services, so the
memory layer (Hindsight recall/reflect) has real breadth to reason over
instead of three rows on one service. The reference demo scenario is
preserved exactly - INC-087/064/041 on payment-service, with
those pinned ids so evidence codes in the UI and prompts match our
demo script/pitch.

Most incidents are hand-authored (not pulled from a live monitoring feed -
real observability integration is out of scope for this build). The
integration-gateway and internal-web-service incidents (ids 130-135) are
adapted from a real public dataset: ameau01/synthetic-it-support-tickets on
HuggingFace (MIT licensed) - specifically its "AIT" (Integration Gateway API
timeouts) and "CES" (expired TLS certificate on an internal web service)
categories, which are the two categories in that dataset that are genuinely
production/infra-relevant rather than corporate helpdesk tickets (password
resets, VPN, printers, etc., which make up most of that dataset and were not
used here). Root causes and resolutions are taken from that dataset's real
ticket text; symptom lists, metrics, and the action/outcome schema were
normalized to fit this app's model.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import (
    Service,
    Deployment,
    Incident,
    Action,
    Outcome,
    Lesson,
    IncidentEmbedding,
    Severity,
    IncidentStatus,
    ActionStatus,
    OutcomeStatus,
)
from app.ai.embeddings import embed_incident
from app.ai import hindsight_memory

DELETE_ORDER = [Lesson, Outcome, Action, IncidentEmbedding, Incident, Deployment, Service]

SERVICES = {
    "payment-service": {"environment": "production", "owner": "payments-team"},
    "checkout-service": {"environment": "production", "owner": "commerce-team"},
    "auth-service": {"environment": "production", "owner": "identity-team"},
    "notification-service": {"environment": "production", "owner": "messaging-team"},
    "integration-gateway": {"environment": "production", "owner": "platform-team"},
    "internal-web-service": {"environment": "production", "owner": "platform-team"},
}

# Each entry mirrors _seed_historical_incident's kwargs, minus `service` (looked
# up by `service_name`). Ids are pinned so INC-XXX codes are stable across resets.
INCIDENTS = [
    # --- payment-service: the reference demo scenario ---
    dict(
        service_name="payment-service",
        incident_id=87,
        severity=Severity.SEV1.value,
        symptoms=["5xx errors", "high latency", "db connection saturation"],
        metrics_before={"error_rate": 19.1, "latency_ms": 2500, "db_connections_pct": 94},
        root_cause="Deployment v2.3.0 introduced a connection leak causing DB exhaustion.",
        resolution="Resolved via rollback deployment.",
        deployment_version="v2.3.0",
        deployment_minutes_before=9,
        deployment_changes="Refactored payment gateway connection handling",
        action_type="rollback_deployment",
        action_description="Rolled back payment-service to v2.2.4",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 1.1, "latency_ms": 260, "db_connections_pct": 30},
        duration_minutes=None,
        outcome_notes="Rollback restored stable metrics within minutes.",
        lesson_text=(
            "Rollback deployment was effective for this incident pattern. Deployment-related DB "
            "exhaustion resolved by rollback."
        ),
        days_ago=23,
    ),
    dict(
        service_name="payment-service",
        incident_id=64,
        severity=Severity.SEV1.value,
        symptoms=["5xx errors", "high latency", "db connection saturation"],
        metrics_before={"error_rate": 17.5, "latency_ms": 2300, "db_connections_pct": 90},
        root_cause="Transient resource exhaustion; underlying cause not fully identified at the time.",
        resolution="Errors returned after roughly 10 minutes; required further action.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="restart_service",
        action_description="Restarted payment-service pods",
        outcome_status=OutcomeStatus.TEMPORARY.value,
        metrics_after={"error_rate": 2.0, "latency_ms": 400, "db_connections_pct": 40},
        duration_minutes=10,
        outcome_notes="Recovered for ~10 minutes; incident returned.",
        lesson_text=(
            "Restart service only provided temporary relief for this incident pattern. Recovered for "
            "~10 minutes before symptoms returned. Do not rely on it as a permanent fix next time."
        ),
        days_ago=26,
    ),
    dict(
        service_name="payment-service",
        incident_id=41,
        severity=Severity.SEV2.value,
        symptoms=["5xx errors", "elevated latency"],
        metrics_before={"error_rate": 9.2, "latency_ms": 1400, "db_connections_pct": 75},
        root_cause="Connection pool sizing insufficient for load spike.",
        resolution="Errors reduced but underlying cause persisted.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="increase_connection_pool",
        action_description="Increased DB connection pool size",
        outcome_status=OutcomeStatus.PARTIAL.value,
        metrics_after={"error_rate": 4.5, "latency_ms": 900, "db_connections_pct": 60},
        duration_minutes=None,
        outcome_notes="Reduced errors but did not remove underlying cause.",
        lesson_text=(
            "Increase connection pool partially mitigated the incident but did not fully resolve it. "
            "Reduced errors but did not remove underlying cause."
        ),
        days_ago=29,
    ),
    # --- payment-service: two more, showing restart isn't *always* temporary ---
    dict(
        service_name="payment-service",
        incident_id=102,
        severity=Severity.SEV2.value,
        symptoms=["timeout errors", "elevated latency"],
        metrics_before={"error_rate": 6.5, "latency_ms": 1800, "db_connections_pct": 40},
        root_cause="Third-party payment gateway began rate-limiting our API key under peak load.",
        resolution="Partially mitigated by scaling; gateway limit remained the true bottleneck.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="scale_service",
        action_description="Scaled payment-service replicas from 4 to 8",
        outcome_status=OutcomeStatus.PARTIAL.value,
        metrics_after={"error_rate": 3.8, "latency_ms": 1100, "db_connections_pct": 42},
        duration_minutes=None,
        outcome_notes="Reduced queuing internally, but the external rate limit remained the bottleneck.",
        lesson_text=(
            "Scaling only partially helped when the bottleneck was an external gateway rate limit, "
            "not our own capacity. Confirm the constraint is internal before scaling."
        ),
        days_ago=14,
    ),
    dict(
        service_name="payment-service",
        incident_id=119,
        severity=Severity.SEV1.value,
        symptoms=["5xx errors", "queue backlog"],
        metrics_before={"error_rate": 22.0, "latency_ms": 1900, "db_connections_pct": 50},
        root_cause="A queue consumer process deadlocked and stopped processing payment events.",
        resolution="Resolved by restarting the stuck consumer process.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="restart_service",
        action_description="Restarted the payment-events consumer",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.9, "latency_ms": 310, "db_connections_pct": 35},
        duration_minutes=None,
        outcome_notes="Consumer resumed processing immediately and stayed healthy.",
        lesson_text=(
            "Restart service was fully effective here because the root cause was a deadlocked "
            "process, not resource exhaustion - unlike INC-064, where restart only masked the "
            "problem temporarily. The outcome depends on the underlying cause, not the action alone."
        ),
        days_ago=6,
    ),
    # --- checkout-service ---
    dict(
        service_name="checkout-service",
        incident_id=55,
        severity=Severity.SEV1.value,
        symptoms=["5xx errors", "high latency"],
        metrics_before={"error_rate": 12.4, "latency_ms": 2100, "db_connections_pct": 55},
        root_cause="Connection pool to the inventory-service dependency was exhausted under load.",
        resolution="Resolved by increasing the outbound connection pool size.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="increase_connection_pool",
        action_description="Increased inventory-service client connection pool",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 1.2, "latency_ms": 340, "db_connections_pct": 30},
        duration_minutes=None,
        outcome_notes="Errors and latency returned to normal within minutes.",
        lesson_text="Increase connection pool was effective when the bottleneck was a downstream dependency pool, not the database itself.",
        days_ago=18,
    ),
    dict(
        service_name="checkout-service",
        incident_id=71,
        severity=Severity.SEV1.value,
        symptoms=["failed transactions", "high latency"],
        metrics_before={"error_rate": 15.7, "latency_ms": 2600, "db_connections_pct": 82},
        root_cause="A recent deployment introduced an N+1 query pattern in the checkout flow.",
        resolution="Resolved via rollback deployment.",
        deployment_version="v4.8.0",
        deployment_minutes_before=14,
        deployment_changes="Refactored cart pricing calculation",
        action_type="rollback_deployment",
        action_description="Rolled back checkout-service to v4.7.2",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.8, "latency_ms": 280, "db_connections_pct": 35},
        duration_minutes=None,
        outcome_notes="Query load and latency returned to normal immediately after rollback.",
        lesson_text="Rollback deployment was effective for a deployment-introduced N+1 query pattern.",
        days_ago=11,
    ),
    dict(
        service_name="checkout-service",
        incident_id=93,
        severity=Severity.SEV2.value,
        symptoms=["failed transactions"],
        metrics_before={"error_rate": 7.1, "latency_ms": 950, "db_connections_pct": 68},
        root_cause="Database deadlocks under high concurrency during checkout writes.",
        resolution="Deadlocking queries identified; full fix required an application-level change.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="investigate_query_performance",
        action_description="Analyzed slow query log and lock contention during peak checkout writes",
        outcome_status=OutcomeStatus.PARTIAL.value,
        metrics_after={"error_rate": 4.0, "latency_ms": 700, "db_connections_pct": 60},
        duration_minutes=None,
        outcome_notes="Identified the deadlocking transaction pattern but resolution needed a code change outside automated remediation.",
        lesson_text=(
            "Investigate query performance surfaced the right root cause (deadlocking transactions) "
            "but is a diagnostic step, not a fix - expect a follow-up action item, not full resolution."
        ),
        days_ago=8,
    ),
    # --- auth-service ---
    dict(
        service_name="auth-service",
        incident_id=33,
        severity=Severity.SEV1.value,
        symptoms=["login failures", "high latency"],
        metrics_before={"error_rate": 28.3, "latency_ms": 1600, "db_connections_pct": 45},
        root_cause="A recent deployment broke session token validation for a subset of token formats.",
        resolution="Resolved via rollback deployment.",
        deployment_version="v9.2.0",
        deployment_minutes_before=6,
        deployment_changes="Migrated session tokens to a new signing algorithm",
        action_type="rollback_deployment",
        action_description="Rolled back auth-service to v9.1.3",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.5, "latency_ms": 220, "db_connections_pct": 20},
        duration_minutes=None,
        outcome_notes="Login success rate returned to normal immediately.",
        lesson_text="Rollback deployment was effective when a token/session format migration broke validation.",
        days_ago=20,
    ),
    dict(
        service_name="auth-service",
        incident_id=48,
        severity=Severity.SEV1.value,
        symptoms=["login failures", "5xx errors"],
        metrics_before={"error_rate": 19.0, "latency_ms": 1300, "db_connections_pct": 88},
        root_cause="Redis session store connection pool exhausted under peak login traffic.",
        resolution="Resolved by increasing the Redis connection pool size.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="increase_connection_pool",
        action_description="Increased Redis session-store connection pool",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 1.0, "latency_ms": 240, "db_connections_pct": 35},
        duration_minutes=None,
        outcome_notes="Login failures resolved within minutes of the pool increase.",
        lesson_text="Increase connection pool was effective for session-store exhaustion under peak login load.",
        days_ago=15,
    ),
    dict(
        service_name="auth-service",
        incident_id=62,
        severity=Severity.SEV2.value,
        symptoms=["login failures"],
        metrics_before={"error_rate": 11.2, "latency_ms": 500, "db_connections_pct": 25},
        root_cause="An expired TLS certificate on the upstream identity-provider integration.",
        resolution="Not resolvable by any automated action; required manual certificate renewal.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="no_action",
        action_description="Escalated to manual certificate renewal; no automated action applied",
        outcome_status=OutcomeStatus.FAILED.value,
        metrics_after={"error_rate": 10.9, "latency_ms": 510, "db_connections_pct": 25},
        duration_minutes=None,
        outcome_notes="Automated remediation does not apply to certificate expiry; required manual escalation.",
        lesson_text=(
            "No automated action resolves a third-party certificate expiry - this pattern should be "
            "escalated to manual intervention immediately rather than attempting a remediation action."
        ),
        days_ago=5,
    ),
    # --- notification-service ---
    dict(
        service_name="notification-service",
        incident_id=77,
        severity=Severity.SEV2.value,
        symptoms=["delayed notifications", "queue backlog"],
        metrics_before={"error_rate": 2.5, "latency_ms": 300, "db_connections_pct": 30},
        root_cause="Notification worker pool was undersized for a holiday traffic spike.",
        resolution="Resolved by scaling the worker pool.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="scale_service",
        action_description="Scaled notification workers from 6 to 16",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.4, "latency_ms": 120, "db_connections_pct": 20},
        duration_minutes=None,
        outcome_notes="Queue backlog cleared within 15 minutes of scaling.",
        lesson_text="Scale service was effective for genuine capacity shortfalls during traffic spikes.",
        days_ago=17,
    ),
    dict(
        service_name="notification-service",
        incident_id=84,
        severity=Severity.SEV1.value,
        symptoms=["delayed notifications", "high latency"],
        metrics_before={"error_rate": 8.0, "latency_ms": 2200, "db_connections_pct": 40},
        root_cause="A recent deployment introduced blocking I/O in the notification worker loop.",
        resolution="Resolved via rollback deployment.",
        deployment_version="v3.1.0",
        deployment_minutes_before=11,
        deployment_changes="Switched notification templates to synchronous rendering",
        action_type="rollback_deployment",
        action_description="Rolled back notification-service to v3.0.4",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.6, "latency_ms": 150, "db_connections_pct": 25},
        duration_minutes=None,
        outcome_notes="Latency and delivery delay returned to normal immediately.",
        lesson_text="Rollback deployment was effective when a deployment introduced blocking I/O in a worker loop.",
        days_ago=9,
    ),
    dict(
        service_name="notification-service",
        incident_id=91,
        severity=Severity.SEV2.value,
        symptoms=["duplicate notifications sent"],
        metrics_before={"error_rate": 4.2, "latency_ms": 280, "db_connections_pct": 22},
        root_cause="A message queue acknowledgement bug caused redelivery of already-sent notifications.",
        resolution="Symptoms briefly stopped after restart, then recurred once queue depth grew again.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="restart_service",
        action_description="Restarted the notification-worker consumer group",
        outcome_status=OutcomeStatus.TEMPORARY.value,
        metrics_after={"error_rate": 1.0, "latency_ms": 200, "db_connections_pct": 20},
        duration_minutes=25,
        outcome_notes="Duplicates stopped for ~25 minutes, then resumed - the ack bug itself was never fixed.",
        lesson_text=(
            "Restart service only provided temporary relief for a message-acknowledgement bug; "
            "the underlying bug needs a code fix, not a process restart."
        ),
        days_ago=3,
    ),
    # --- integration-gateway: adapted from ameau01/synthetic-it-support-tickets (HuggingFace,
    # MIT licensed), category AIT "Integration Gateway API timeouts". Root causes and
    # resolutions are taken from that dataset's real ticket text; symptoms/metrics/schema
    # fields were normalized to fit this app's incident model. ---
    dict(
        service_name="integration-gateway",
        incident_id=130,
        severity=Severity.SEV1.value,
        symptoms=["API timeouts", "504 gateway timeout", "delayed data sync"],
        metrics_before={"error_rate": 18.0, "latency_ms": 12000},
        root_cause=(
            "Integration Gateway service account token expired after a failed automated rotation "
            "job, causing authentication failures that cascaded into downstream call timeouts."
        ),
        resolution="Resolved by manually rotating the token and restarting the gateway worker.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="rotate_credentials",
        action_description="Manually rotated the expired service-account API token and restarted the gateway worker process",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.8, "latency_ms": 280},
        duration_minutes=None,
        outcome_notes="Authenticated calls succeeded immediately after rotation; batch sync latency returned to baseline.",
        lesson_text=(
            "Rotate credentials was fully effective when an expired service-account token caused "
            "authentication failures that cascaded into timeouts. Confirm automated token-rotation "
            "jobs alert on failure, not just run silently."
        ),
        days_ago=12,
    ),
    dict(
        service_name="integration-gateway",
        incident_id=131,
        severity=Severity.SEV2.value,
        symptoms=["API timeouts", "504 gateway timeout", "delayed data sync"],
        metrics_before={"error_rate": 9.4, "latency_ms": 45000},
        root_cause=(
            "Downstream Inventory API latency spiked (p99 ~45s vs a 2s baseline), exceeding the "
            "Integration Gateway's 30s timeout and causing repeated 504 responses."
        ),
        resolution="Mitigated by temporarily raising the gateway timeout and tuning retry/backoff.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="adjust_timeout_and_retries",
        action_description="Temporarily raised the gateway timeout from 30s to 90s and tuned retry/backoff settings",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.9, "latency_ms": 1800},
        duration_minutes=None,
        outcome_notes="Sync jobs completed once downstream latency stabilized; the temporary timeout increase was reverted afterward.",
        lesson_text=(
            "Adjust timeout and retries is effective as a mitigation while a downstream dependency "
            "is slow, but it does not fix the downstream service itself - confirm the temporary "
            "change is reverted once the root latency issue resolves."
        ),
        days_ago=10,
    ),
    dict(
        service_name="integration-gateway",
        incident_id=132,
        severity=Severity.SEV2.value,
        symptoms=["API timeouts", "429 rate limited", "delayed data sync"],
        metrics_before={"error_rate": 15.0, "latency_ms": 9000},
        root_cause=(
            "A downstream partner API began rate-limiting the integration client (HTTP 429), and "
            "retry volume under elevated latency exhausted the gateway's timeout window."
        ),
        resolution="Resolved with backoff tuning plus a downstream quota increase.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="adjust_timeout_and_retries",
        action_description="Applied exponential backoff (2s-60s, jittered) and coordinated with the downstream API owner to raise the client's request quota",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 1.1, "latency_ms": 900},
        duration_minutes=None,
        outcome_notes="Retry storms stopped once backoff was applied, and job failures ended after the quota increase took effect.",
        lesson_text=(
            "Adjust timeout and retries also resolves rate-limit-driven timeouts, but a durable fix "
            "required the downstream owner raising quota - backoff alone only reduces retry pressure, "
            "it doesn't remove the limit."
        ),
        days_ago=7,
    ),
    dict(
        service_name="integration-gateway",
        incident_id=133,
        severity=Severity.SEV1.value,
        symptoms=["API timeouts", "504 gateway timeout"],
        metrics_before={"error_rate": 16.5, "latency_ms": 8000},
        root_cause=(
            "The integration service account token expired because the scheduled rotation job "
            "silently failed, causing authentication failures that cascaded into call timeouts."
        ),
        resolution="Resolved by rotating the token in the secrets vault and restarting the gateway pod.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="rotate_credentials",
        action_description="Rotated the expired API token in the secrets vault and restarted the Integration Gateway pod",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.7, "latency_ms": 260},
        duration_minutes=None,
        outcome_notes="Timeouts stopped immediately after the gateway reloaded with the refreshed credential.",
        lesson_text=(
            "This is the second time an expired service-account token caused cascading timeouts on "
            "this gateway (see also INC-130) - the recurring pattern suggests the rotation job's "
            "failure alerting itself needs to be fixed, not just each individual token."
        ),
        days_ago=4,
    ),
    # --- internal-web-service: adapted from the same dataset, category CES "Expired TLS
    # certificate on Internal Web Service behind Load Balancer". ---
    dict(
        service_name="internal-web-service",
        incident_id=134,
        severity=Severity.SEV1.value,
        symptoms=["TLS certificate warnings", "connection rejected", "5xx errors"],
        metrics_before={"error_rate": 22.0},
        root_cause=(
            "The TLS certificate presented by the load balancer expired, and certificate renewal "
            "monitoring had failed to alert before expiration."
        ),
        resolution="Resolved by renewing the certificate and deploying the full chain to the load balancer.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="rotate_credentials",
        action_description="Renewed the TLS certificate and deployed the full certificate chain to the load balancer",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.3},
        duration_minutes=None,
        outcome_notes="TLS handshakes succeeded immediately after the renewed chain was deployed; expiry monitoring was restored.",
        lesson_text=(
            "Rotate credentials was effective for an expired TLS certificate, but the real fix also "
            "requires restoring expiry monitoring/alerting - otherwise this class of incident recurs silently."
        ),
        days_ago=19,
    ),
    dict(
        service_name="internal-web-service",
        incident_id=135,
        severity=Severity.SEV1.value,
        symptoms=["TLS certificate warnings", "connection rejected"],
        metrics_before={"error_rate": 19.5},
        root_cause=(
            "A prior certificate renewal was applied to the backend service but never deployed to "
            "the load balancer, so the load balancer continued serving the expired certificate to clients."
        ),
        resolution="Resolved by deploying the already-renewed certificate chain to the load balancer.",
        deployment_version=None,
        deployment_minutes_before=0,
        deployment_changes="",
        action_type="rotate_credentials",
        action_description="Deployed the already-renewed certificate chain to the load balancer and reloaded its configuration",
        outcome_status=OutcomeStatus.SUCCESSFUL.value,
        metrics_after={"error_rate": 0.2},
        duration_minutes=None,
        outcome_notes="Service was confirmed live within two minutes of the load balancer reload.",
        lesson_text=(
            "A certificate rotation that only updates the backend service without also updating the "
            "load balancer's certificate chain will resurface as the same incident - always validate "
            "the full chain from the client's perspective, not just the origin (see also INC-134)."
        ),
        days_ago=2,
    ),
]

MAX_INCIDENT_ID = max(item["incident_id"] for item in INCIDENTS)

# Structured "where is this actually happening" location, kept separate from the free-text
# root_cause so the UI can surface it as its own field rather than making users read prose.
AFFECTED_COMPONENTS = {
    87: "payment-service pod payment-7f2c9 (DB connection pool)",
    64: "payment-service pods (restarted)",
    41: "payment-service DB connection pool",
    102: "payment-service -> third-party payment gateway API client",
    119: "payment-events queue consumer process",
    55: "checkout-service -> inventory-service client connection pool",
    71: "checkout-service cart pricing calculation path",
    93: "checkout-service database (checkout writes table)",
    33: "auth-service session token validation path",
    48: "auth-service Redis session store",
    62: "auth-service identity-provider TLS integration",
    77: "notification-service worker pool",
    84: "notification-service worker loop (template rendering)",
    91: "notification-service queue consumer (ack handling)",
    130: "integration-gateway service account svc-custsync-prod",
    131: "integration-gateway -> Inventory API endpoint /api/v2/inventory/sync",
    132: "integration-gateway -> downstream partner API client",
    133: "integration-gateway service account svc-datasync-prod (pod intgw-prod)",
    134: "internal-web-service load balancer LB-EAST-02 (svc-internal.corplabs.internal)",
    135: "internal-web-service load balancer LB-EAST-02 (internal-api.corp)",
}


def _now():
    return datetime.now(timezone.utc)


def _reset_tables(db: Session):
    for model in DELETE_ORDER:
        db.query(model).delete()
    db.commit()


def _seed_historical_incident(db: Session, service: Service, **kwargs):
    incident_id = kwargs["incident_id"]
    symptoms = kwargs["symptoms"]
    metrics_before = kwargs["metrics_before"]
    root_cause = kwargs["root_cause"]
    action_type = kwargs["action_type"]
    action_description = kwargs["action_description"]
    outcome_status = kwargs["outcome_status"]
    metrics_after = kwargs["metrics_after"]
    outcome_notes = kwargs["outcome_notes"]
    lesson_text = kwargs["lesson_text"]

    base_time = _now() - timedelta(days=kwargs["days_ago"])

    deployment = None
    if kwargs["deployment_version"]:
        deployment = Deployment(
            service_id=service.id,
            version=kwargs["deployment_version"],
            timestamp=base_time - timedelta(minutes=kwargs["deployment_minutes_before"]),
            changes=kwargs["deployment_changes"],
            status="deployed",
        )
        db.add(deployment)
        db.flush()

    incident = Incident(
        id=incident_id,
        service_id=service.id,
        severity=kwargs["severity"],
        timestamp=base_time,
        symptoms=symptoms,
        status=IncidentStatus.RESOLVED.value,
        root_cause=root_cause,
        affected_component=AFFECTED_COMPONENTS.get(incident_id),
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        resolution=kwargs["resolution"],
        is_historical=1,
        recent_deployment_id=deployment.id if deployment else None,
    )
    db.add(incident)
    db.flush()

    db.add(IncidentEmbedding(incident_id=incident.id, vector=embed_incident(symptoms, root_cause)))

    action = Action(
        incident_id=incident.id,
        type=action_type,
        description=action_description,
        timestamp=base_time + timedelta(minutes=5),
        approved_by="on-call-engineer",
        status=ActionStatus.SIMULATED.value,
    )
    db.add(action)
    db.flush()

    db.add(
        Outcome(
            action_id=action.id,
            status=outcome_status,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            duration_minutes=kwargs["duration_minutes"],
            notes=outcome_notes,
        )
    )

    db.add(
        Lesson(
            incident_id=incident.id,
            lesson_text=lesson_text,
            evidence=[f"INC-{incident_id:03d}"],
            created_at=base_time + timedelta(minutes=20),
        )
    )

    affected_component = AFFECTED_COMPONENTS.get(incident_id)
    hindsight_memory.retain_incident_memory(
        service_name=service.name,
        content=(
            f"Incident INC-{incident_id:03d} on {service.name}: symptoms were {', '.join(symptoms)}. "
            + (f"Affected component: {affected_component}. " if affected_component else "")
            + f"Root cause: {root_cause} Action taken: {action_description} ({action_type}). "
            f"Outcome: {outcome_status} — {outcome_notes} Lesson: {lesson_text}"
        ),
        metadata={
            "incident_code": f"INC-{incident_id:03d}",
            "service": service.name,
            "action_type": action_type,
            "outcome_status": outcome_status,
            "severity": kwargs["severity"],
        },
        tags=[action_type, outcome_status],
    )


def reset_and_seed(db: Session):
    _reset_tables(db)
    for service_name in SERVICES:
        hindsight_memory.reset_bank(service_name)

    services: dict[str, Service] = {}
    for name, attrs in SERVICES.items():
        service = Service(name=name, environment=attrs["environment"], owner=attrs["owner"])
        db.add(service)
        db.flush()
        services[name] = service

    for incident_kwargs in INCIDENTS:
        service = services[incident_kwargs["service_name"]]
        _seed_historical_incident(db, service, **{k: v for k, v in incident_kwargs.items() if k != "service_name"})

    db.commit()

    # Keep future auto-generated incident ids above the highest pinned historical one.
    db.execute(text(f"SELECT setval(pg_get_serial_sequence('incidents', 'id'), {MAX_INCIDENT_ID}, true)"))
    db.commit()
