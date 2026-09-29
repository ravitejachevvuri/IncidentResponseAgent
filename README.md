# Production Memory

**AI-powered incident response agent that remembers what worked — built on Hindsight.**

Production Memory doesn't just remember what happened during a production incident — it
remembers what actions were tried, what happened afterward, and what should be
recommended next time. Memory is provided by [Hindsight](https://hindsight.vectorize.io)
(Vectorize).

```
Incident → Action → Outcome → Learning → Better Future Recommendation
```

## Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL (structured incident/action/outcome data)
- **Memory:** [Hindsight](https://hindsight.vectorize.io) — `retain()` writes every
  resolved incident's narrative into a per-service memory bank; `recall()` powers
  similar-incident retrieval; `reflect()` (with a JSON `response_schema`) generates the
  actual remediation recommendation, reasoning over retained memory
- **AI fallback chain:** Hindsight reflect → direct Groq call (Llama 3.3) → deterministic
  rule-based recommendation, each validated by the same backend guardrails
- **Frontend:** React + Vite
- **Infra:** Docker Compose

## Quickstart

```bash
cp .env.example .env
# Sign up at https://ui.hindsight.vectorize.io/signup (promo code MEMHACK99 for $50
# credit), then fill in HINDSIGHT_API_KEY and HINDSIGHT_BASE_URL in .env.
# Optionally set GROQ_API_KEY too, as a secondary fallback if Hindsight is unreachable.
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173

The database is auto-seeded on first backend startup with the reference demo
scenario (`payment-service`, incidents INC-087 / INC-064 / INC-041 — see
`docs/submission/live-demo-script.md`), and those same incidents are `retain()`-ed into Hindsight.
Use the **Reset Demo** button (or `POST /api/demo/reset`) to restore that seeded
state in both Postgres and Hindsight at any time.

Without `HINDSIGHT_API_KEY`/`HINDSIGHT_BASE_URL` configured, the header shows
"Hindsight: not configured" and the system transparently falls back to Groq, then to
the deterministic recommendation engine — the full workflow (recommend → approve →
simulate → outcome → memory) still works end-to-end either way (spec: the demo must
be reliable even if an external integration is unavailable).

## Repository layout

```
backend/
  app/
    api/          FastAPI routes
    models/       SQLAlchemy models
    schemas/      Pydantic request/response models
    services/     incident, memory, similarity, recommendation, outcome, simulation
    ai/           hindsight_memory.py (retain/recall/reflect), Groq client, prompts
    main.py
  seed/           reference demo scenario seed data (Postgres + Hindsight retain calls)
  tests/          unit tests, incl. a mocked Hindsight-client end-to-end flow
frontend/
  src/
    components/   dashboard sections (metrics, similar incidents, recommendation, etc.)
    api.js        backend client
docker-compose.yml
```

## The signature feature: Outcome Memory, via Hindsight

Most systems retrieve "we saw this before." Production Memory additionally
retrieves **what happened after** the action was taken — successful, partial,
temporary, or failed — and folds that into both the recommendation and an
explicit warning (e.g. "restart was only temporary last time; don't rely on it
as a permanent fix"). That retrieval and the recommendation itself are both
powered by Hindsight, not hand-rolled: `app/ai/hindsight_memory.py` wraps
`retain`/`recall`/`reflect`, and `app/services/memory_service.py` /
`recommendation_service.py` use them as the primary path (see
`docs/architecture.md` for the exact fallback chain and why Postgres still
exists alongside Hindsight).

## Confidence scoring

Confidence is still computed in application code, never invented by any LLM or
by Hindsight (see `app/services/recommendation_service.py::compute_confidence`).
Five weighted signals (20 points each): same service, symptom similarity,
metric similarity, recent-deployment consistency, and historical action/outcome
relevance for the recommended action.

## Testing

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest httpx
python -m pytest tests/ -q
```

`tests/test_recommendation_logic.py` covers the deterministic reasoning layer
in isolation (no DB). `tests/test_hindsight_flow.py` runs the full HTTP flow
against an in-memory SQLite DB with a mocked Hindsight client, proving: recall
results populate "Similar Incidents", reflect's structured output becomes the
recommendation, retain() is called on memory write-back, and — critically —
the backend guardrail overrides Hindsight even when it stubbornly recommends
rollback with no deployment signal.

See `docs/architecture.md`, `docs/api.md`, and `docs/submission/live-demo-script.md` for more detail.

For a full plain-language walkthrough of the tech stack choices, the
reasoning loop, and worked examples (including a non-payment-service
domain), see **`docs/how-it-works.md`**.

For a shot-by-shot script for the demo video — including a real,
unstaged "the agent just learned live" moment — see **`docs/submission/demo-video-script.md`**.

For ideas deliberately left out of this build — including linking incidents
to a real Git repo/CI pipeline — see **`docs/future-scope.md`**.

For a two-part overview document — a written explanation plus a section
mapping the demo video to what's actually happening underneath — see
**`docs/submission/overview.md`**.

For a read-aloud narration script for recording the demo video — story,
learning-curve proof, and what's next, with no UI directions — see
**`docs/submission/demo-narration-script.md`**.

For the 3-minute video script following the intro/problem/demo/takeaway
structure — with on-screen cues, real files and endpoints to show, and
YouTube title options — see **`docs/submission/video-script.md`**.

For the complete walkthrough covering everything built — talk-and-drive-the-
screen format, cuttable into sections — see
**`docs/submission/full-walkthrough-script.md`**.
