const NORMAL = { error_rate: 2, latency_ms: 500, db_connections_pct: 70 };
const LABELS = { error_rate: "Error rate", latency_ms: "Latency", db_connections_pct: "DB connections" };
const UNITS = { error_rate: "%", latency_ms: "ms", db_connections_pct: "%" };

function MetricTile({ metricKey, value }) {
  const normal = NORMAL[metricKey];
  const breached = normal !== undefined && value > normal;
  return (
    <div className={`metric-tile ${breached ? "metric-breach" : "metric-ok"}`}>
      <span className="metric-label">{LABELS[metricKey] || metricKey}</span>
      <span className="metric-value">
        {value}
        {UNITS[metricKey] || ""}
      </span>
      {normal !== undefined && <span className="metric-normal">normal &lt; {normal}{UNITS[metricKey]}</span>}
    </div>
  );
}

export default function LiveMetrics({ incident }) {
  if (!incident) return null;
  const metrics = incident.metrics_after || incident.metrics_before || {};
  const deployment = incident.recent_deployment;
  const isResolved = incident.status === "resolved";
  const deploymentIsBreach = Boolean(deployment) && !isResolved;
  return (
    <section className="card">
      <h2>Live Metrics</h2>
      <div className="metric-grid">
        {Object.entries(metrics).map(([key, value]) => (
          <MetricTile key={key} metricKey={key} value={value} />
        ))}
        <div className={`metric-tile ${deploymentIsBreach ? "metric-breach" : "metric-ok"}`}>
          <span className="metric-label">Deployment age</span>
          <span className="metric-value">
            {deployment ? `${deployment.minutes_before_incident}m ago` : "none recent"}
          </span>
          {deployment && (
            <span className="metric-normal">
              {deployment.version}
              {isResolved ? " (incident resolved)" : ""}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
