export default function Header({ llmConfigured, hindsightConfigured, environment }) {
  return (
    <header className="header">
      <div className="header-left">
        <span className="logo-mark">◆</span>
        <div>
          <h1>Production Memory</h1>
          <p className="tagline">Incident → Action → Outcome → Learning, powered by Hindsight</p>
        </div>
      </div>
      <div className="header-right">
        <span className="pill">{environment || "production"}</span>
        <span className={`pill ${hindsightConfigured ? "pill-ok" : "pill-warn"}`}>
          {hindsightConfigured ? "Hindsight: connected" : "Hindsight: not configured"}
        </span>
        <span className={`pill ${llmConfigured ? "pill-ok" : "pill-warn"}`}>
          {llmConfigured ? "Groq: connected" : "Groq: deterministic fallback"}
        </span>
      </div>
    </header>
  );
}
