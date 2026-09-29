import { useEffect, useState } from "react";
import { api } from "./api";
import Header from "./components/Header.jsx";
import DemoControls from "./components/DemoControls.jsx";
import IncidentSummary from "./components/IncidentSummary.jsx";
import LiveMetrics from "./components/LiveMetrics.jsx";
import SimilarIncidents from "./components/SimilarIncidents.jsx";
import RecommendationCard from "./components/RecommendationCard.jsx";
import OutcomePanel from "./components/OutcomePanel.jsx";
import Timeline from "./components/Timeline.jsx";
import MemoryUpdate from "./components/MemoryUpdate.jsx";
import IncidentHistoryList from "./components/IncidentHistoryList.jsx";
import ActionsList from "./components/ActionsList.jsx";
import CustomIncidentForm from "./components/CustomIncidentForm.jsx";
import DeploymentHistory from "./components/DeploymentHistory.jsx";

const SCENARIOS = {
  "with-deployment": {
    service_name: "payment-service",
    severity: "SEV-1",
    symptoms: ["5xx errors", "high latency", "db connection saturation"],
    metrics: { error_rate: 18.4, latency_ms: 2400, db_connections_pct: 96 },
    recent_deployment: {
      version: "v2.4.1",
      changes: "Updated payment retry logic",
      minutes_before: 8,
    },
  },
  "no-deployment": {
    service_name: "payment-service",
    severity: "SEV-1",
    symptoms: ["5xx errors", "high latency", "db connection saturation"],
    metrics: { error_rate: 16.8, latency_ms: 2100, db_connections_pct: 91 },
  },
};

export default function App() {
  const [view, setView] = useState("demo"); // "demo" | "history"
  const [health, setHealth] = useState(null);
  const [incident, setIncident] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [recommendation, setRecommendation] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [outcome, setOutcome] = useState(null);
  const [decided, setDecided] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const [historyList, setHistoryList] = useState([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState(null);
  const [historyIncident, setHistoryIncident] = useState(null);
  const [historyTimeline, setHistoryTimeline] = useState([]);
  const [deployments, setDeployments] = useState([]);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ llm_configured: false }));
  }, []);

  useEffect(() => {
    if (view === "history") {
      api.history().then(setHistoryList).catch((e) => setError(String(e.message || e)));
    }
    if (view === "deployments") {
      api.listDeployments().then(setDeployments).catch((e) => setError(String(e.message || e)));
    }
  }, [view]);

  async function selectHistoryIncident(id) {
    setSelectedHistoryId(id);
    try {
      const [inc, tl] = await Promise.all([api.getIncident(id), api.getTimeline(id)]);
      setHistoryIncident(inc);
      setHistoryTimeline(tl);
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function refreshIncident(id) {
    const [inc, sim, tl] = await Promise.all([api.getIncident(id), api.getSimilar(id), api.getTimeline(id)]);
    setIncident(inc);
    setSimilar(sim);
    setTimeline(tl);
    return inc;
  }

  async function triggerPayload(payload) {
    setBusy(true);
    setError(null);
    setOutcome(null);
    setDecided(null);
    setRecommendation(null);
    try {
      const created = await api.createIncident(payload);
      await refreshIncident(created.id);
      const rec = await api.generateRecommendation(created.id);
      setRecommendation(rec);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function triggerScenario(kind) {
    await triggerPayload(SCENARIOS[kind]);
  }

  async function handleApprove() {
    if (!recommendation) return;
    setBusy(true);
    setError(null);
    try {
      await api.approveAction(recommendation.action_id, "on-call-engineer");
      await api.simulateAction(recommendation.action_id);
      const result = await api.recordOutcome(recommendation.action_id);
      setOutcome(result);
      setDecided("approved");
      setIncident(result.incident);
      const tl = await api.getTimeline(incident.id);
      setTimeline(tl);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    if (!recommendation) return;
    setBusy(true);
    setError(null);
    try {
      await api.rejectAction(recommendation.action_id, "on-call-engineer");
      setDecided("rejected");
      const tl = await api.getTimeline(incident.id);
      setTimeline(tl);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenerate() {
    if (!incident) return;
    setBusy(true);
    setError(null);
    setDecided(null);
    setOutcome(null);
    try {
      const rec = await api.generateRecommendation(incident.id);
      setRecommendation(rec);
      const tl = await api.getTimeline(incident.id);
      setTimeline(tl);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    setBusy(true);
    setError(null);
    try {
      await api.resetDemo();
      setIncident(null);
      setSimilar([]);
      setRecommendation(null);
      setTimeline([]);
      setOutcome(null);
      setDecided(null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <Header
        llmConfigured={health?.llm_configured}
        hindsightConfigured={health?.hindsight_configured}
        environment={incident?.environment}
      />
      <div className="tab-row">
        <button className={view === "demo" ? "" : "secondary"} onClick={() => setView("demo")}>
          Live Demo
        </button>
        <button className={view === "history" ? "" : "secondary"} onClick={() => setView("history")}>
          All Incidents
        </button>
        <button className={view === "deployments" ? "" : "secondary"} onClick={() => setView("deployments")}>
          Deployments
        </button>
      </div>
      <main className="main-grid">
        {error && <div className="card error-banner">{error}</div>}

        {view === "demo" && (
          <>
            <DemoControls onTrigger={triggerScenario} onReset={handleReset} busy={busy} />
            <CustomIncidentForm onSubmit={triggerPayload} busy={busy} />
            {!incident && !error && (
              <div className="card empty-state">
                Trigger a scenario above to start a live incident walkthrough.
              </div>
            )}
            {incident && (
              <>
                <IncidentSummary incident={incident} />
                <LiveMetrics incident={incident} />
                <SimilarIncidents incidents={similar} />
                <RecommendationCard
                  recommendation={recommendation}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onRegenerate={handleRegenerate}
                  decided={decided}
                  outcome={outcome}
                  busy={busy}
                />
                <OutcomePanel outcome={outcome} />
                <Timeline events={timeline} />
                <MemoryUpdate lessons={incident.lessons} />
              </>
            )}
          </>
        )}

        {view === "history" && (
          <>
            <IncidentHistoryList
              incidents={historyList}
              onSelect={selectHistoryIncident}
              selectedId={selectedHistoryId}
            />
            {historyIncident && (
              <>
                <IncidentSummary incident={historyIncident} />
                <LiveMetrics incident={historyIncident} />
                <ActionsList actions={historyIncident.actions} />
                <Timeline events={historyTimeline} />
                <MemoryUpdate lessons={historyIncident.lessons} />
              </>
            )}
          </>
        )}

        {view === "deployments" && <DeploymentHistory deployments={deployments} />}
      </main>
    </div>
  );
}
