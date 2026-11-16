"""research.py - web search, official page fetching, LLM extraction and verification.

Rules enforced here:
- The LLM may only extract values that appear in the fetched page text.
- Every field gets a status: verified / estimated / not_found, plus a source URL.
"""
import asyncio
import hashlib
import json
import os
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(override=True)

SEARCH_API_KEY = os.getenv("SEARCH_API_KEY", "")
SEARCH_URL = os.getenv("SEARCH_URL", "https://api.tavily.com/search")  # Tavily-style API
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")  # any OpenAI-compatible API
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

TIMEOUT = httpx.Timeout(25.0)
HEADERS = {"User-Agent": "UCRP-Research/0.1 (educational project)"}
MAX_PAGE_CHARS = 12000
_llm_sem = asyncio.Semaphore(2)  # protect free-tier rate limits

SCALAR_FIELDS = [
    "university", "faculty", "program_name", "level", "country", "city",
    "duration_years", "annual_tuition", "tuition_currency",
    "min_academic_percent", "min_ielts", "application_deadline",
]
LIST_FIELDS = ["keywords", "career_outcomes", "research_areas"]


class ResearchError(Exception):
    pass


# ---------------------------------------------------------------- search

def is_official(url: str) -> bool:
    """Heuristic: academic domains (.edu, .ac.xx, .edu.xx). Not perfect, so non-official data is marked 'estimated'."""
    host = (urlparse(url).hostname or "").lower()
    return bool(re.search(r"(^|\.)(edu|ac)(\.|$)", host))


async def web_search(query: str, max_results: int = 6) -> list[dict]:
    if not SEARCH_API_KEY:
        raise ResearchError("SEARCH_API_KEY is not set")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {SEARCH_API_KEY}"},
            json={"query": query, "max_results": max_results, "search_depth": "basic"},
        )
        if r.status_code != 200:
            raise ResearchError(f"Search API error {r.status_code}")
        return r.json().get("results", [])


async def find_candidate_urls(profile: dict, limit: int) -> list[str]:
    countries = profile.get("countries") or ["Australia"]
    queries = []
    for c in countries:
        base = f"{profile['level']} {profile['field_of_study']} {c} university"
        queries.append(f"{base} annual tuition fees per year entry requirements minimum")
        queries.append(f"{base} course overview career outcomes faculty")
    results = await asyncio.gather(*[web_search(q) for q in queries], return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    if errors and len(errors) == len(results):
        raise errors[0]  # surface the real search error

    seen, official, other = set(), [], []
    for res in results:
        if isinstance(res, Exception):
            continue
        for item in res:
            url = item.get("url", "")
            if not url or url in seen or url.lower().endswith(".pdf"):
                continue
            seen.add(url)
            (official if is_official(url) else other).append(url)
    urls = (official + other)[:limit]
    if not urls:
        raise ResearchError("Search returned no usable URLs")
    return urls


# ---------------------------------------------------------------- fetch

async def fetch_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(url)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            raise ResearchError(f"Cannot read {url}")
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:MAX_PAGE_CHARS]


# ---------------------------------------------------------------- LLM

async def llm_json(system: str, user: str) -> dict:
    if not LLM_API_KEY:
        raise ResearchError("LLM_API_KEY is not set")
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    async with _llm_sem:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            for attempt in range(3):
                r = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
                if r.status_code == 429 or r.status_code >= 500:
                    await asyncio.sleep(2 * (attempt + 1))  # simple backoff
                    continue
                if r.status_code != 200:
                    raise ResearchError(f"LLM API error {r.status_code}")
                content = r.json()["choices"][0]["message"]["content"]
                content = re.sub(r"^```(?:json)?|```$", "", content.strip()).strip()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    raise ResearchError("LLM returned invalid JSON")
    raise ResearchError(f"LLM API error {r.status_code}: {r.text[:200]}")


EXTRACT_SYSTEM = """You extract university program data from web page text.
STRICT RULES:
- Use ONLY information explicitly present in the text. Never guess or use outside knowledge.
- If a value is not in the text, return null.
- Numbers must be plain numbers (no currency symbols or commas).
- min_academic_percent: only if the text states a minimum average as a percentage; otherwise null.
- annual_tuition: yearly tuition for the requested student type; if only per-credit/per-unit fees are given, return null.
- Return a single JSON object with exactly these keys:
university, faculty, program_name, level, country, city, duration_years, annual_tuition,
tuition_currency (ISO code), min_academic_percent, min_ielts, application_deadline,
keywords (list of short strings), career_outcomes (list), research_areas (list)."""


def _found_in_text(value, text: str) -> bool:
    low = text.lower()
    if isinstance(value, (int, float)):
        n = int(value) if float(value).is_integer() else value
        variants = {str(n), f"{n:,}" if isinstance(n, int) else str(n)}
        return any(v in text for v in variants)
    return str(value).lower() in low


def _build_program(url: str, text: str, data: dict) -> dict:
    official = is_official(url)
    fields = {}
    for f in SCALAR_FIELDS:
        v = data.get(f)
        if v in (None, "", "null"):
            fields[f] = {"value": None, "status": "not_found", "source": None}
        else:
            ok = official and _found_in_text(v, text)
            fields[f] = {"value": v, "status": "verified" if ok else "estimated", "source": url}
    for f in LIST_FIELDS:
        v = data.get(f) or []
        v = [str(x) for x in v if x][:12] if isinstance(v, list) else []
        if not v:
            fields[f] = {"value": [], "status": "not_found", "source": None}
        else:
            fields[f] = {"value": v, "status": "verified" if official else "estimated", "source": url}
    uni = (fields["university"]["value"] or "").strip().lower()
    prog = (fields["program_name"]["value"] or "").strip().lower()
    return {
        "id": hashlib.sha1(f"{uni}|{prog}|{url}".encode()).hexdigest()[:10],
        "source_url": url,
        "official": official,
        "fields": fields,
    }


async def _extract_one(url: str, profile: dict) -> dict:
    text = await fetch_text(url)
    user = (f"Student type: {profile.get('student_type', 'international')}\n"
            f"Wanted level: {profile['level']}; field: {profile['field_of_study']}\n"
            f"Source URL: {url}\n\nPAGE TEXT:\n{text}")
    data = await llm_json(EXTRACT_SYSTEM, user)
    return _build_program(url, text, data)


# ---------------------------------------------------------------- enrichment

KEY_FIELDS = ["annual_tuition", "tuition_currency", "min_academic_percent",
              "min_ielts", "application_deadline", "career_outcomes"]

ENRICH_SYSTEM = """You extract missing details about ONE specific university program from web page text.
STRICT RULES:
- Use ONLY information explicitly present in the text. Never guess.
- Only return details that clearly belong to the named program and university; otherwise return null.
- If a value is not in the text, return null.
- Numbers must be plain numbers (no currency symbols or commas).
- min_academic_percent: only if stated as a percentage; otherwise null.
- annual_tuition: yearly tuition for the requested student type; per-credit fees -> null.
Return a single JSON object with exactly these keys:
annual_tuition, tuition_currency (ISO code), min_academic_percent, min_ielts,
application_deadline, career_outcomes (list)."""


async def _enrich(program: dict, profile: dict) -> None:
    """Fill missing key fields from other official pages about the same program (edits in place)."""
    f = program["fields"]
    missing = [k for k in KEY_FIELDS if f[k]["status"] == "not_found"]
    uni, prog = f["university"]["value"], f["program_name"]["value"]
    if not missing or not uni or not prog:
        return
    try:
        results = await web_search(f"{uni} {prog} tuition fees entry requirements", max_results=5)
    except Exception:
        return
    urls = [r["url"] for r in results
            if r.get("url") and is_official(r["url"])
            and not r["url"].lower().endswith(".pdf") and r["url"] != program["source_url"]][:2]
    for url in urls:
        try:
            text = await fetch_text(url)
            if prog.lower() not in text.lower():
                continue  # page is not about this program, skip to avoid wrong data
            user = (f"Student type: {profile.get('student_type', 'international')}\n"
                    f"University: {uni}\nProgram: {prog}\nSource URL: {url}\n\nPAGE TEXT:\n{text}")
            data = await llm_json(ENRICH_SYSTEM, user)
        except Exception:
            continue
        for k in missing:
            if f[k]["status"] != "not_found":
                continue
            v = data.get(k)
            if k == "career_outcomes":
                v = [str(x) for x in v if x][:12] if isinstance(v, list) else []
                if v:
                    f[k] = {"value": v, "status": "verified", "source": url}
            elif v not in (None, "", "null"):
                ok = _found_in_text(v, text)
                f[k] = {"value": v, "status": "verified" if ok else "estimated", "source": url}


async def research_programs(profile: dict, max_programs: int = 6) -> list[dict]:
    urls = await find_candidate_urls(profile, limit=max_programs * 2)
    results = await asyncio.gather(*[_extract_one(u, profile) for u in urls], return_exceptions=True)
    programs, seen, errors, skipped = [], set(), [], 0
    for res in results:
        if isinstance(res, Exception):
            errors.append(str(res))
            continue
        f = res["fields"]
        if not f["university"]["value"] or not f["program_name"]["value"]:
            skipped += 1  # page had no usable program data
            continue
        key = (f["university"]["value"].lower(), f["program_name"]["value"].lower())
        if key in seen:
            continue
        seen.add(key)
        programs.append(res)
    if not programs:
        raise ResearchError(
            f"No program extracted. Pages: {len(urls)}, errors: {len(errors)}, "
            f"unusable: {skipped}. First error: {errors[0] if errors else 'none'}"
        )
    programs.sort(key=lambda p: not p["official"])
    programs = programs[:max_programs]
    await asyncio.gather(*[_enrich(p, profile) for p in programs], return_exceptions=True)
    return programs


# ---------------------------------------------------------------- explanation

EXPLAIN_SYSTEM = """You explain a university compatibility result to a student.
Use ONLY the scores, notes and data provided. Do not add facts. Max 120 words, plain English.
Return JSON: {"explanation": "..."}"""


async def explain_result(profile: dict, result: dict) -> str:
    summary = {
        "university": result["university"], "program": result["program_name"],
        "overall": result["overall"], "criteria": result["criteria"],
        "strengths": result["strengths"], "weaknesses": result["weaknesses"],
        "risks": result["risks"], "tags": result["tags"],
        "student_goal": profile.get("career_goal", ""),
    }
    data = await llm_json(EXPLAIN_SYSTEM, json.dumps(summary))
    return str(data.get("explanation", "")).strip()