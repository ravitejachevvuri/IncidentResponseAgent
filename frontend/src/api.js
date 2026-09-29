const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  health: () => request("/api/health"),
  createIncident: (payload) => request("/api/incidents", { method: "POST", body: JSON.stringify(payload) }),
  getIncident: (id) => request(`/api/incidents/${id}`),
  getSimilar: (id) => request(`/api/incidents/${id}/similar`),
  getTimeline: (id) => request(`/api/incidents/${id}/timeline`),
  generateRecommendation: (id) => request(`/api/incidents/${id}/recommendation`, { method: "POST" }),
  approveAction: (actionId, approvedBy) =>
    request(`/api/actions/${actionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  rejectAction: (actionId, approvedBy) =>
    request(`/api/actions/${actionId}/reject`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  simulateAction: (actionId) => request(`/api/actions/${actionId}/simulate`, { method: "POST" }),
  recordOutcome: (actionId) => request(`/api/actions/${actionId}/outcome`, { method: "POST" }),
  resetDemo: () => request("/api/demo/reset", { method: "POST" }),
  history: () => request("/api/incidents/history"),
  listDeployments: () => request("/api/deployments"),
};
