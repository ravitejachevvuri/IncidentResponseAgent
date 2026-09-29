const SOURCE_LABEL = {
  hindsight: "Hindsight memory reflect",
  llm: "Groq LLM (direct)",
  deterministic_fallback: "Deterministic fallback",
};

export default function RecommendationCard({ recommendation, onApprove, onReject, onRegenerate, decided, outcome, busy }) {
  if (!recommendation) return null;

  const outcomeUnresolved = decided === "approved" && outcome && outcome.status !== "successful";
  const canRegenerate = decided === "rejected" || outcomeUnresolved;

  return (
    <section className="card recommendation-card">
      <div className="recommendation-header">
        <h2>AI Recommendation</h2>
        <span className={`pill ${recommendation.source === "hindsight" ? "pill-ok" : recommendation.source === "llm" ? "pill-ok" : "pill-warn"}`}>
          {SOURCE_LABEL[recommendation.source] || recommendation.source}
        </span>
      </div>

      <div className="grid-2">
        <div>
          <span className="label">Recommended action</span>
          <span className="value action-name">{recommendation.recommended_action.replaceAll("_", " ")}</span>
        </div>
        <div>
          <span className="label">Target</span>
          <span className="value">{recommendation.target}</span>
        </div>
        <div>
          <span className="label">Risk</span>
          <span className={`value risk-${recommendation.risk}`}>{recommendation.risk}</span>
        </div>
        <div>
          <span className="label">Confidence</span>
          <span className="value confidence-value">{recommendation.confidence}%</span>
        </div>
      </div>

      <p className="reason-text">{recommendation.reason}</p>

      {recommendation.warnings?.length > 0 && (
        <div className="warning-box">
          {recommendation.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      <div className="evidence-row">
        <span className="label">Evidence</span>
        {recommendation.evidence.map((e) => (
          <span key={e} className="chip">
            {e}
          </span>
        ))}
        {recommendation.evidence.length === 0 && <span className="muted">No direct historical evidence</span>}
      </div>

      {recommendation.alternative_actions?.length > 0 && (
        <div className="evidence-row">
          <span className="label">Alternatives</span>
          {recommendation.alternative_actions.map((a) => (
            <span key={a} className="chip chip-muted">
              {a.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      )}

      <details className="confidence-breakdown">
        <summary>Why this confidence score?</summary>
        <ul>
          {recommendation.confidence_breakdown.map((item) => (
            <li key={item.signal}>
              <strong>
                {item.signal}: {item.contribution}/{item.weight}
              </strong>{" "}
              — {item.explanation}
            </li>
          ))}
        </ul>
      </details>

      {!decided ? (
        <div className="button-row">
          <button disabled={busy} onClick={onApprove}>
            Approve
          </button>
          <button disabled={busy} className="secondary" onClick={onReject}>
            Reject
          </button>
        </div>
      ) : (
        <>
          <p className={`decision-label decision-${decided}`}>
            Recommendation {decided}
            {outcomeUnresolved && ` — outcome: ${outcome.status}, did not fully resolve the incident`}
          </p>
          {canRegenerate && (
            <div className="button-row">
              <button disabled={busy} onClick={onRegenerate}>
                {decided === "rejected" ? "Generate a new recommendation" : "Try another action on this incident"}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
