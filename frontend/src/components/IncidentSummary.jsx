export default function IncidentSummary({ incident }) {
  if (!incident) return null;
  return (
    <section className="card">
      <h2>Incident Summary</h2>
      <div className="grid-2">
        <div>
          <span className="label">ID</span>
          <span className="value">{incident.code || `#${incident.id}`}</span>
        </div>
        <div>
          <span className="label">Service</span>
          <span className="value">{incident.service_name}</span>
        </div>
        <div>
          <span className="label">Severity</span>
          <span className={`value severity-${incident.severity?.replace("SEV-", "")}`}>{incident.severity}</span>
        </div>
        <div>
          <span className="label">Status</span>
          <span className={`value status-${incident.status}`}>{incident.status}</span>
        </div>
        <div>
          <span className="label">Detected</span>
          <span className="value">{new Date(incident.timestamp).toLocaleString()}</span>
        </div>
        <div>
          <span className="label">Symptoms</span>
          <span className="value">{incident.symptoms?.join(", ")}</span>
        </div>
        {incident.affected_component && (
          <div>
            <span className="label">Where</span>
            <span className="value">{incident.affected_component}</span>
          </div>
        )}
        {incident.root_cause && (
          <div>
            <span className="label">Root cause</span>
            <span className="value">{incident.root_cause}</span>
          </div>
        )}
      </div>
    </section>
  );
}
