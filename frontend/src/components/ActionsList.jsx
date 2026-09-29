const OUTCOME_LABEL = {
  successful: "Successful",
  partial: "Partial",
  temporary: "Temporary",
  failed: "Failed",
  unresolved: "Unresolved",
};

export default function ActionsList({ actions }) {
  if (!actions || actions.length === 0) return null;
  return (
    <section className="card">
      <h2>Actions Taken</h2>
      <ul className="similar-list">
        {actions.map((a) => (
          <li key={a.id} className="similar-item">
            <div className="similar-header">
              <span className="incident-code">{a.type.replaceAll("_", " ")}</span>
              {a.outcome && (
                <span className={`similarity-badge outcome-${a.outcome.status}`}>
                  {OUTCOME_LABEL[a.outcome.status] || a.outcome.status}
                </span>
              )}
            </div>
            <div className="muted">{a.description}</div>
            {a.recommendation?.reason && (
              <div className="lesson-text">Why: {a.recommendation.reason}</div>
            )}
            {a.recommendation?.warnings?.length > 0 && (
              <div className="warning-box">
                {a.recommendation.warnings.map((w, i) => (
                  <div key={i}>⚠ {w}</div>
                ))}
              </div>
            )}
            {a.outcome && (
              <div className="muted">
                Before: {JSON.stringify(a.outcome.metrics_before)} → After:{" "}
                {JSON.stringify(a.outcome.metrics_after)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
