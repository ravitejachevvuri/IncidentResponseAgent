export default function DeploymentHistory({ deployments }) {
  if (!deployments || deployments.length === 0) {
    return (
      <section className="card">
        <h2>Deployment History</h2>
        <p className="muted">No deployments recorded.</p>
      </section>
    );
  }

  const byService = {};
  for (const d of deployments) {
    byService[d.service_name] = byService[d.service_name] || [];
    byService[d.service_name].push(d);
  }

  return (
    <section className="card">
      <h2>Deployment History ({deployments.length})</h2>
      {Object.entries(byService).map(([serviceName, deploys]) => (
        <div key={serviceName} className="deployment-group">
          <h3>{serviceName}</h3>
          <ul className="similar-list">
            {deploys.map((d) => (
              <li key={d.id} className="similar-item">
                <div className="similar-header">
                  <span className="incident-code">{d.version}</span>
                  <span className={`chip outcome-${d.status === "rolled_back" ? "failed" : "successful"}`}>
                    {d.status}
                  </span>
                </div>
                <div className="muted">{new Date(d.timestamp).toLocaleString()}</div>
                {d.changes && <div className="lesson-text">{d.changes}</div>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
