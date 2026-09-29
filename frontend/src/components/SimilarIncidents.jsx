export default function SimilarIncidents({ incidents }) {
  if (!incidents || incidents.length === 0) {
    return (
      <section className="card">
        <h2>Similar Incidents</h2>
        <p className="muted">No closely matching historical incidents were found.</p>
      </section>
    );
  }
  const poweredByHindsight = incidents.some((s) => s.retrieval_source === "hindsight");
  return (
    <section className="card">
      <div className="recommendation-header">
        <h2>Similar Incidents</h2>
        <span className={`pill ${poweredByHindsight ? "pill-ok" : "pill-warn"}`}>
          {poweredByHindsight ? "Hindsight recall" : "Structured fallback match"}
        </span>
      </div>
      <ul className="similar-list">
        {incidents.map((s) => (
          <li key={s.incident_id} className="similar-item">
            <div className="similar-header">
              <span className="incident-code">{s.incident_code}</span>
              <span className={`similarity-badge similarity-${s.similarity_label.toLowerCase()}`}>
                {s.similarity_label} · {s.similarity_score}%
              </span>
            </div>
            <div className="muted">{s.symptoms.join(", ")}</div>
            {s.recall_text && <div className="lesson-text">Hindsight memory: "{s.recall_text}"</div>}
            {s.key_lesson && <div className="lesson-text">Lesson: {s.key_lesson}</div>}
            <div className="action-chips">
              {s.actions.map((a) => (
                <span key={a.id} className={`chip outcome-${a.outcome?.status || "unrecorded"}`}>
                  {a.type.replaceAll("_", " ")}: {a.outcome?.status || "unrecorded"}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
