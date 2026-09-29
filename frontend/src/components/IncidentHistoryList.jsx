export default function IncidentHistoryList({ incidents, onSelect, selectedId }) {
  return (
    <section className="card">
      <h2>All Incidents ({incidents.length})</h2>
      <ul className="similar-list">
        {incidents.map((inc) => (
          <li
            key={inc.id}
            className={`similar-item history-item ${selectedId === inc.id ? "history-item-active" : ""}`}
            onClick={() => onSelect(inc.id)}
          >
            <div className="similar-header">
              <span className="incident-code">{inc.code}</span>
              <span className={`chip outcome-${inc.status}`}>{inc.status}</span>
            </div>
            <div className="muted">
              {inc.service_name} · {inc.severity} · {inc.symptoms.join(", ")}
            </div>
            {inc.root_cause && <div className="lesson-text">{inc.root_cause}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}
