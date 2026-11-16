"""main.py - FastAPI app: API endpoints + static frontend. Storage is in-memory only."""
import asyncio
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import engine, research

app = FastAPI(title="University Compatibility & Recommendation Platform")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
SESSION_TTL = 3600
MAX_SESSIONS = 50
SESSIONS: dict[str, dict] = {}  # analysis_id -> {"ts", "profile", "results"}

INTERNATIONAL_COUNTRIES = {
    "new zealand", "singapore", "united states", "canada", "japan", "south korea", "taiwan",
    "china", "germany", "netherlands", "france", "sweden", "switzerland", "ireland", "united kingdom",
}


class Profile(BaseModel):
    mode: Literal["local", "international"] = "local"
    countries: list[str] = Field(default_factory=list)
    student_type: Literal["domestic", "international"] = "international"
    level: str = Field(min_length=2, max_length=60)          # e.g. "Bachelor", "Master", "PhD"
    field_of_study: str = Field(min_length=2, max_length=120)
    interests: list[str] = Field(default_factory=list, max_length=10)
    academic_percent: Optional[float] = Field(default=None, ge=0, le=100)
    ielts: Optional[float] = Field(default=None, ge=0, le=9)
    budget_per_year: Optional[float] = Field(default=None, ge=0)
    currency: str = "AUD"
    career_goal: str = Field(default="", max_length=300)
    preferred_locations: list[str] = Field(default_factory=list, max_length=10)
    max_results: int = Field(default=5, ge=1, le=8)


class CompareRequest(BaseModel):
    analysis_id: str
    program_ids: list[str] = Field(min_length=2, max_length=4)


def _purge_sessions():
    now = time.time()
    for k in [k for k, v in SESSIONS.items() if now - v["ts"] > SESSION_TTL]:
        del SESSIONS[k]
    while len(SESSIONS) > MAX_SESSIONS:
        del SESSIONS[min(SESSIONS, key=lambda k: SESSIONS[k]["ts"])]


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(profile: Profile):
    data = profile.model_dump()
    if profile.mode == "local":
        data["countries"] = ["Australia"]
    else:
        countries = [c.strip() for c in profile.countries if c.strip()]
        bad = [c for c in countries if c.lower() not in INTERNATIONAL_COUNTRIES]
        if not countries or bad:
            raise HTTPException(400, f"Unsupported or missing countries: {bad or 'none selected'}")
        data["countries"] = countries[:3]  # limit to protect free-tier quotas

    try:
        programs = await research.research_programs(data, max_programs=profile.max_results)
    except research.ResearchError as e:
        raise HTTPException(502, f"Research failed: {e}")
    except Exception:
        raise HTTPException(500, "Unexpected research error")
    if not programs:
        return {"analysis_id": None, "results": [], "message": "No matching programs found. Try different keywords."}

    results = engine.rank_and_tag([engine.score_program(data, p) for p in programs])

    # AI explanation for the top results only; fall back to rule-based text
    top = results[:3]
    explanations = await asyncio.gather(*[research.explain_result(data, r) for r in top], return_exceptions=True)
    for r, ex in zip(top, explanations):
        r["explanation"] = ex if isinstance(ex, str) and ex else engine.basic_explanation(r)
    for r in results[3:]:
        r["explanation"] = engine.basic_explanation(r)

    _purge_sessions()
    analysis_id = uuid.uuid4().hex[:12]
    SESSIONS[analysis_id] = {"ts": time.time(), "profile": data, "results": results}
    return {"analysis_id": analysis_id, "results": results}


@app.post("/api/compare")
async def compare(req: CompareRequest):
    session = SESSIONS.get(req.analysis_id)
    if not session:
        raise HTTPException(404, "Analysis expired or not found. Please run the analysis again.")
    chosen = [r for r in session["results"] if r["id"] in req.program_ids]
    if len(chosen) < 2:
        raise HTTPException(400, "Select at least two valid programs to compare.")
    return engine.compare(chosen)


# Serve the frontend last so /api routes take priority
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")