"""Safe simulated remediation. No real infrastructure is ever touched."""
import random

# (error_rate_multiplier, latency_multiplier, db_connections_multiplier, regresses_after_minutes)
SIMULATION_PROFILES = {
    "rollback_deployment": (0.06, 0.12, 0.35, None),
    "restart_service": (0.15, 0.20, 0.55, 10),
    "increase_connection_pool": (0.35, 0.55, 0.45, None),
    "scale_service": (0.30, 0.40, 0.70, None),
    "inspect_db_connections": (0.25, 0.35, 0.40, None),
    "investigate_query_performance": (0.30, 0.45, 0.55, None),
    "rotate_credentials": (0.08, 0.15, 0.40, None),
    "adjust_timeout_and_retries": (0.35, 0.45, 0.50, None),
    "no_action": (1.0, 1.0, 1.0, None),
}

METRIC_KEYS = ("error_rate", "latency_ms", "db_connections_pct")


def simulate_action(action_type: str, metrics_before: dict) -> tuple[dict, int | None]:
    error_mult, latency_mult, db_mult, regresses_after = SIMULATION_PROFILES.get(
        action_type, SIMULATION_PROFILES["no_action"]
    )
    jitter = lambda: random.uniform(0.92, 1.08)  # noqa: E731 - small realism jitter

    metrics_after = dict(metrics_before)
    if "error_rate" in metrics_before:
        metrics_after["error_rate"] = round(metrics_before["error_rate"] * error_mult * jitter(), 2)
    if "latency_ms" in metrics_before:
        metrics_after["latency_ms"] = round(metrics_before["latency_ms"] * latency_mult * jitter())
    if "db_connections_pct" in metrics_before:
        metrics_after["db_connections_pct"] = round(metrics_before["db_connections_pct"] * db_mult * jitter(), 1)

    return metrics_after, regresses_after
