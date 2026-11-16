"""engine.py - explainable compatibility scoring, risk analysis, ranking and tagging.

Every criterion returns a score (0-100) or None when data is missing.
Missing criteria are excluded and the remaining weights are renormalised,
so a missing value never silently becomes a guess.
"""
import re

WEIGHTS_DEFAULT = {"academic": 20, "financial": 20, "course": 20, "career": 15, "admission": 15, "lifestyle": 10}
# Research degrees: research fit and supervisor/facility match matter more
WEIGHTS_RESEARCH = {"academic": 20, "financial": 15, "course": 30, "career": 10, "admission": 15, "lifestyle": 10}
RESEARCH_LEVELS = {"master by research", "mphil", "phd"}

# Approximate rates to AUD - update periodically. Treated as estimates.
FX_TO_AUD = {"AUD": 1.0, "USD": 1.5, "NZD": 0.92, "SGD": 1.13, "CAD": 1.08, "JPY": 0.01,
            "KRW": 0.0011, "TWD": 0.047, "CNY": 0.21, "EUR": 1.65, "GBP": 1.95, "CHF": 1.7, "SEK": 0.15}

# Rough yearly living cost in AUD (estimate, not verified data)
LIVING_COST_AUD = {"australia": 28000, "new zealand": 24000, "singapore": 26000, "united states": 32000,
                "canada": 24000, "japan": 18000, "south korea": 16000, "taiwan": 12000, "china": 12000,
                "germany": 18000, "netherlands": 22000, "france": 19000, "sweden": 22000,
                "switzerland": 38000, "ireland": 24000, "united kingdom": 30000}
DEFAULT_LIVING_COST = 22000

STOPWORDS = {"with", "and", "the", "for", "of", "in", "to", "a", "an", "degree", "program", "studies", "study"}


def _val(program: dict, field: str):
    return program["fields"][field]["value"]


def _status(program: dict, field: str) -> str:
    return program["fields"][field]["status"]


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z]{3,}", text.lower()) if t not in STOPWORDS}


def _overlap(user_text: str, target_text: str):
    user_tokens = _tokens(user_text)
    if not user_tokens or not target_text.strip():
        return None
    return len(user_tokens & _tokens(target_text)) / len(user_tokens)


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def _to_aud(amount, currency):
    rate = FX_TO_AUD.get((currency or "").upper())
    return amount * rate if rate else None


def annual_cost_aud(program: dict):
    tuition = _val(program, "annual_tuition")
    if tuition is None:
        return None
    t = _to_aud(float(tuition), _val(program, "tuition_currency"))
    if t is None:
        return None
    living = LIVING_COST_AUD.get((_val(program, "country") or "").lower(), DEFAULT_LIVING_COST)
    return t + living


# ---------------------------------------------------------------- criteria

def score_academic(profile, program):
    user, req = profile.get("academic_percent"), _val(program, "min_academic_percent")
    if user is None or req is None:
        return None, "Academic requirement or student grade not available"
    diff = user - float(req)
    score = _clamp(60 + diff * 4)  # at the minimum = 60, +10 points above = 100
    return score, f"Your average {user:.0f}% vs typical minimum {float(req):.0f}%"


def score_admission(profile, program):
    checks, notes = [], []
    req = _val(program, "min_academic_percent")
    if req is not None and profile.get("academic_percent") is not None:
        ok = profile["academic_percent"] >= float(req)
        checks.append(ok)
        notes.append("meets grade requirement" if ok else "below grade requirement")
    ielts = _val(program, "min_ielts")
    if ielts is not None and profile.get("ielts") is not None and profile.get("student_type") == "international":
        ok = profile["ielts"] >= float(ielts)
        checks.append(ok)
        notes.append("meets English requirement" if ok else "below English requirement")
    if not checks:
        return None, "Not enough data to judge admission feasibility"
    score = 90 - 35 * sum(1 for c in checks if not c)
    return _clamp(score), "; ".join(notes)


def score_financial(profile, program):
    budget = profile.get("budget_per_year")
    cost = annual_cost_aud(program)
    if budget is None or cost is None:
        return None, "Tuition or budget not available"
    budget_aud = _to_aud(float(budget), profile.get("currency", "AUD"))
    if not budget_aud:
        return None, "Unsupported budget currency"
    ratio = cost / budget_aud
    score = 100 if ratio <= 0.7 else _clamp(100 - (ratio - 0.7) / 0.8 * 100)
    return score, f"Estimated yearly cost ~AUD {cost:,.0f} (tuition + estimated living) vs budget ~AUD {budget_aud:,.0f}"


def score_course(profile, program):
    wanted = f"{profile.get('field_of_study', '')} {' '.join(profile.get('interests', []))}"
    haystack = " ".join([_val(program, "program_name") or "", _val(program, "faculty") or "",
                        " ".join(_val(program, "keywords")), " ".join(_val(program, "research_areas"))])
    ratio = _overlap(wanted, haystack)
    if ratio is None:
        return None, "No course content available"
    score = 0 if ratio == 0 else _clamp(30 + 70 * ratio)
    return score, f"{ratio:.0%} of your field/interest terms match the program"


def score_career(profile, program):
    goal = profile.get("career_goal", "")
    haystack = " ".join(_val(program, "career_outcomes") + _val(program, "keywords"))
    ratio = _overlap(goal, haystack)
    if ratio is None:
        return None, "Career goal or program career outcomes not available"
    score = 0 if ratio == 0 else _clamp(30 + 70 * ratio)
    return score, f"{ratio:.0%} of your career-goal terms match listed outcomes"


def score_lifestyle(profile, program):
    prefs = [p.lower() for p in profile.get("preferred_locations", []) if p.strip()]
    if not prefs:
        return None, "No lifestyle/location preference given"
    place = f"{_val(program, 'city') or ''} {_val(program, 'country') or ''}".lower()
    if not place.strip():
        return None, "Program location not available"
    hit = any(p in place for p in prefs)
    return (100 if hit else 40), ("Matches preferred location" if hit else "Not in preferred locations")


SCORERS = {"academic": score_academic, "financial": score_financial, "course": score_course,
        "career": score_career, "admission": score_admission, "lifestyle": score_lifestyle}


# ---------------------------------------------------------------- program scoring

def score_program(profile: dict, program: dict) -> dict:
    weights = WEIGHTS_RESEARCH if profile["level"].lower() in RESEARCH_LEVELS else WEIGHTS_DEFAULT
    criteria, used_w, total = {}, 0, 0.0
    for name, fn in SCORERS.items():
        score, note = fn(profile, program)
        criteria[name] = {"score": None if score is None else round(score, 1), "weight": weights[name], "note": note}
        if score is not None:
            used_w += weights[name]
            total += weights[name] * score
    coverage = used_w / sum(weights.values())
    overall = round(total / used_w, 1) if coverage >= 0.4 else None  # too little data -> no score

    strengths = [f"{k.title()}: {v['note']}" for k, v in criteria.items() if v["score"] is not None and v["score"] >= 70]
    weaknesses = [f"{k.title()}: {v['note']}" for k, v in criteria.items() if v["score"] is not None and v["score"] <= 40]
    missing = [k for k, v in criteria.items() if v["score"] is None]

    risks = {}
    fin, adm = criteria["financial"]["score"], criteria["admission"]["score"]
    risks["financial"] = "unknown" if fin is None else "high" if fin < 40 else "medium" if fin < 70 else "low"
    risks["admission"] = "unknown" if adm is None else "high" if adm < 50 else "medium" if adm < 75 else "low"
    key_fields = ["annual_tuition", "min_academic_percent", "keywords", "career_outcomes", "city"]
    if profile.get("student_type") == "international":
        key_fields.append("min_ielts")
    found = sum(1 for k in key_fields if program["fields"][k]["status"] != "not_found")
    data_ratio = found / len(key_fields)
    risks["data"] = "high" if data_ratio < 0.5 else "medium" if data_ratio < 0.8 else "low"

    verified = sum(1 for f in program["fields"].values() if f["status"] == "verified")
    return {
        "id": program["id"],
        "university": _val(program, "university"),
        "faculty": _val(program, "faculty"),
        "program_name": _val(program, "program_name"),
        "level": _val(program, "level"),
        "country": _val(program, "country"),
        "city": _val(program, "city"),
        "annual_cost_aud": None if annual_cost_aud(program) is None else round(annual_cost_aud(program)),
        "overall": overall,
        "tier": None,
        "tags": [],
        "criteria": criteria,
        "coverage": round(coverage, 2),
        "missing_criteria": missing,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risks": risks,
        "official": program["official"],
        "source_url": program["source_url"],
        "verified_fields": f"{verified}/{len(program['fields'])}",
        "fields": program["fields"],
        "explanation": "",
    }


def basic_explanation(r: dict) -> str:
    """Rule-based fallback when the LLM is unavailable."""
    if r["overall"] is None:
        return "Not enough verified data to compute a reliable score for this program."
    parts = [f"Overall compatibility {r['overall']}/100."]
    if r["strengths"]:
        parts.append("Strengths: " + "; ".join(r["strengths"][:2]) + ".")
    if r["weaknesses"]:
        parts.append("Weaknesses: " + "; ".join(r["weaknesses"][:2]) + ".")
    if r["missing_criteria"]:
        parts.append("Missing data for: " + ", ".join(r["missing_criteria"]) + ".")
    return " ".join(parts)


# ---------------------------------------------------------------- ranking

def rank_and_tag(results: list[dict]) -> list[dict]:
    scored = [r for r in results if r["overall"] is not None]
    unscored = [r for r in results if r["overall"] is None]
    scored.sort(key=lambda r: r["overall"], reverse=True)

    for r in scored:
        r["tier"] = "Highest" if r["overall"] >= 70 else "Moderate" if r["overall"] >= 50 else "Lowest"
    for r in unscored:
        r["tier"] = "Insufficient data"

    def crit(r, k):
        return r["criteria"][k]["score"]

    if scored:
        scored[0]["tags"].append("Best Match")
        ambitious = [r for r in scored if crit(r, "admission") is not None and crit(r, "admission") < 65
                    and (crit(r, "course") or 0) >= 60]
        if ambitious:
            max(ambitious, key=lambda r: r["overall"])["tags"].append("Ambitious Choice")
        safe = [r for r in scored if (crit(r, "admission") or 0) >= 80 and (crit(r, "academic") or 0) >= 70]
        if safe:
            max(safe, key=lambda r: r["overall"])["tags"].append("Safe Choice")
        priced = [r for r in scored if r["annual_cost_aud"] is not None]
        if priced:
            min(priced, key=lambda r: r["annual_cost_aud"])["tags"].append("Budget-Friendly Choice")
    return scored + unscored


COMPARE_FIELDS = ["university", "faculty", "program_name", "level", "country", "city", "annual_cost_aud",
                "overall", "tier", "tags", "risks", "source_url"]


def compare(results: list[dict]) -> dict:
    return {
        "items": [{**{k: r[k] for k in COMPARE_FIELDS},
                "criteria": {k: v["score"] for k, v in r["criteria"].items()}} for r in results]
    }