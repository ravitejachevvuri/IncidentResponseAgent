const OUTCOME_LABEL = {
  successful: "Successful",
  partial: "Partial",
  temporary: "Temporary",
  failed: "Failed",
  unresolved: "Unresolved",
};

export default function OutcomePanel({ outcome }) {
  if (!outcome) return null;
  return (
    <section className="card">
      <h2>Outcome</h2>
      <div className={`outcome-badge outcome-${outcome.status}`}>{OUTCOME_LABEL[outcome.status] || outcome.status}</div>
      <div className="grid-2">
        <div>
          <span className="label">Before</span>
          <span className="value">{JSON.stringify(outcome.metrics_before)}</span>
        </div>
        <div>
          <span className="label">After</span>
          <span className="value">{JSON.stringify(outcome.metrics_after)}</span>
        </div>
      </div>
      <p className="reason-text">{outcome.notes}</p>
    </section>
  );
}
