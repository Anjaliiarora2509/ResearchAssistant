"""FastAPI entry point for the ResearchAssistant backend."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from backend.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="ResearchAssistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# Serve the frontend at /  (frontend/index.html)
_FRONTEND_DIR = Path(__file__).parent / "frontend"
app.mount("/ui", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

# Single shared orchestrator instance — initialised once at startup
_orchestrator: Orchestrator | None = None


@app.on_event("startup")
def _startup() -> None:
    global _orchestrator
    _orchestrator = Orchestrator()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ResearchRequest(BaseModel):
    topic: str

    @field_validator("topic")
    @classmethod
    def topic_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("topic must not be empty")
        return stripped


class ResearchResponse(BaseModel):
    topic: str
    result: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse)
def research(req: ResearchRequest) -> ResearchResponse:
    """Run a full research session and return the synthesised answer."""
    try:
        result = _orchestrator.run(req.topic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ResearchResponse(topic=req.topic, result=result)
