export default function DemoControls({ onTrigger, onReset, busy }) {
  return (
    <section className="card demo-controls">
      <h2>Demo Scenarios</h2>
      <p className="muted">
        Scenario 1 matches the reference incident (recent deployment). Scenario 2 removes the
        deployment signal to prove the agent reasons contextually rather than repeating the same fix.
      </p>
      <div className="button-row">
        <button disabled={busy} onClick={() => onTrigger("with-deployment")}>
          Trigger Scenario 1 — with recent deployment
        </button>
        <button disabled={busy} onClick={() => onTrigger("no-deployment")}>
          Trigger Scenario 2 — no recent deployment
        </button>
        <button disabled={busy} className="secondary" onClick={onReset}>
          Reset Demo
        </button>
      </div>
    </section>
  );
}
