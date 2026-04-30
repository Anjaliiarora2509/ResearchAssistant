---
name: Frontend & API Architecture
description: How the FastAPI backend and browser frontend are structured in ResearchAssistant, and how they connect to the core backend.
type: project
---

A FastAPI REST API and a plain HTML/JS frontend were added to the ResearchAssistant project.

**Why:** To expose the CLI-only research agent as a browser-accessible web app without touching any backend logic.

## Files added

| File | Role |
|---|---|
| `api.py` | FastAPI app — single entry point for the web layer |
| `frontend/index.html` | Browser UI — vanilla HTML/CSS/JS, no framework |

## Architecture

```
browser (frontend/index.html)
  └── POST /research  {"topic": "..."}  → returns {"topic": "...", "result": "..."}
        └── api.py → Orchestrator.run(topic) → str
  └── GET  /ui/       serves index.html via StaticFiles
  └── GET  /health    uptime check
```

## Key design decisions

- `Orchestrator` is instantiated **once** at FastAPI startup (`@app.on_event("startup")`) and shared across all requests — avoids re-initialising Tavily/Groq clients per request.
- CORS is open (`allow_origins=["*"]`) — intentional for local dev; restrict in production.
- The frontend is served at `/ui` via `StaticFiles`, so a single `uvicorn api:app` serves both API and UI.
- `main.py` (CLI) is untouched — both entry points coexist.

## How to run

```bash
pip install -r requirements.txt
uvicorn api:app --reload
# UI at http://localhost:8000/ui
# API at http://localhost:8000/research
```

## Seam for future changes

The entire backend is behind `Orchestrator.run(topic: str) → str`. Any UI change only touches `api.py` and `frontend/`. No backend files need to change.

**How to apply:** When the user asks about adding features to the UI or API, remember the seam is `Orchestrator.run()`. New UI pages or API routes only need to import and call that.
