import { useState } from "react";

const SERVICE_OPTIONS = [
  "payment-service",
  "checkout-service",
  "auth-service",
  "notification-service",
  "integration-gateway",
  "internal-web-service",
];

export default function CustomIncidentForm({ onSubmit, busy }) {
  const [open, setOpen] = useState(false);
  const [serviceName, setServiceName] = useState("integration-gateway");
  const [severity, setSeverity] = useState("SEV-2");
  const [symptoms, setSymptoms] = useState("API timeouts, connection pool exhausted");
  const [errorRate, setErrorRate] = useState("14.5");
  const [latencyMs, setLatencyMs] = useState("2200");
  const [dbConnectionsPct, setDbConnectionsPct] = useState("");
  const [affectedComponent, setAffectedComponent] = useState("");
  const [hasDeployment, setHasDeployment] = useState(false);
  const [deployVersion, setDeployVersion] = useState("");
  const [deployChanges, setDeployChanges] = useState("");
  const [deployMinutesBefore, setDeployMinutesBefore] = useState("8");

  function handleSubmit(e) {
    e.preventDefault();
    const metrics = {};
    if (errorRate) metrics.error_rate = parseFloat(errorRate);
    if (latencyMs) metrics.latency_ms = parseFloat(latencyMs);
    if (dbConnectionsPct) metrics.db_connections_pct = parseFloat(dbConnectionsPct);

    const payload = {
      service_name: serviceName,
      severity,
      symptoms: symptoms
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      metrics,
    };
    if (affectedComponent) payload.affected_component = affectedComponent;
    if (hasDeployment) {
      payload.recent_deployment = {
        version: deployVersion || "v1.0.0",
        changes: deployChanges || "",
        minutes_before: parseFloat(deployMinutesBefore) || 5,
      };
    }
    onSubmit(payload);
  }

  if (!open) {
    return (
      <section className="card demo-controls">
        <h2>Custom Incident</h2>
        <p className="muted">
          Trigger any incident you like — including the same pattern twice in a row, to watch the
          agent's confidence and evidence change as it retains what just happened.
        </p>
        <button className="secondary" onClick={() => setOpen(true)}>
          Open custom incident form
        </button>
      </section>
    );
  }

  return (
    <section className="card demo-controls">
      <h2>Custom Incident</h2>
      <form onSubmit={handleSubmit} className="custom-incident-form">
        <div className="grid-2">
          <label>
            <span className="label">Service</span>
            <select value={serviceName} onChange={(e) => setServiceName(e.target.value)}>
              {SERVICE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Severity</span>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="SEV-1">SEV-1</option>
              <option value="SEV-2">SEV-2</option>
              <option value="SEV-3">SEV-3</option>
            </select>
          </label>
        </div>
        <label>
          <span className="label">Symptoms (comma separated)</span>
          <input value={symptoms} onChange={(e) => setSymptoms(e.target.value)} />
        </label>
        <div className="grid-2">
          <label>
            <span className="label">Error rate (%)</span>
            <input value={errorRate} onChange={(e) => setErrorRate(e.target.value)} />
          </label>
          <label>
            <span className="label">Latency (ms)</span>
            <input value={latencyMs} onChange={(e) => setLatencyMs(e.target.value)} />
          </label>
          <label>
            <span className="label">DB connections (%, optional)</span>
            <input value={dbConnectionsPct} onChange={(e) => setDbConnectionsPct(e.target.value)} />
          </label>
        </div>
        <label>
          <span className="label">Affected component (optional — e.g. an endpoint, host, or pod)</span>
          <input
            value={affectedComponent}
            onChange={(e) => setAffectedComponent(e.target.value)}
            placeholder="e.g. checkout-service pod checkout-7b4df"
          />
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={hasDeployment} onChange={(e) => setHasDeployment(e.target.checked)} />
          <span>Recent deployment</span>
        </label>
        {hasDeployment && (
          <div className="grid-2">
            <label>
              <span className="label">Version</span>
              <input value={deployVersion} onChange={(e) => setDeployVersion(e.target.value)} placeholder="v1.2.3" />
            </label>
            <label>
              <span className="label">Minutes before incident</span>
              <input value={deployMinutesBefore} onChange={(e) => setDeployMinutesBefore(e.target.value)} />
            </label>
            <label>
              <span className="label">Changes</span>
              <input value={deployChanges} onChange={(e) => setDeployChanges(e.target.value)} />
            </label>
          </div>
        )}
        <div className="button-row">
          <button type="submit" disabled={busy}>
            Trigger this incident
          </button>
          <button type="button" className="secondary" onClick={() => setOpen(false)}>
            Collapse
          </button>
        </div>
      </form>
    </section>
  );
}
