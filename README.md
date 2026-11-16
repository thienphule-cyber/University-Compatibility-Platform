# University Compatibility & Recommendation Platform (UCRP)

An AI-assisted web platform that helps students find, evaluate and compare universities, faculties and courses based on their academic profile, finances, goals and personal circumstances. Instead of returning a single "best university", UCRP produces an explainable compatibility score for every option and shows which pieces of data are verified, estimated or missing.

## Website link: https://university-compatibility-platform.onrender.com

## Key Features

- **Three levels of analysis:** university, faculty/school and course/program.
- **All academic levels:** Foundation, Diploma, Undergraduate (Associate, Bachelor, Honours), Postgraduate Coursework (Graduate Certificate, Graduate Diploma, Master), Postgraduate Research (Master by Research, MPhil, PhD), and Pathway/Professional programs.
- **Two modes:**
  - *Local Mode:* Australia.
  - *International Mode:* New Zealand, Singapore, United States, Canada, Japan, South Korea, Taiwan, China, and selected European countries (up to 3 countries per analysis).
- **Explainable scoring:** six weighted criteria, each with its own score and note.
- **Risk analysis:** financial, admission and data-quality risk for every result.
- **Ranking and recommendations:** Highest / Moderate / Lowest compatibility tiers, plus Best Match, Ambitious Choice, Safe Choice and Budget-Friendly Choice tags.
- **Side-by-side comparison** of 2 to 4 programs.
- **Source transparency:** every extracted field carries a status and a source URL.

## Compatibility Criteria

| Criterion | Default weight | Research weight* |
|---|---|---|
| Academic Compatibility | 20% | 20% |
| Financial Compatibility | 20% | 15% |
| Course Compatibility | 20% | 30% |
| Career Compatibility | 15% | 10% |
| Admission Compatibility | 15% | 15% |
| Lifestyle Compatibility | 10% | 10% |

\*Research weights apply to Master by Research, MPhil and PhD, where research fit matters more than for coursework degrees.

Results are grouped into tiers: **Highest** (70 and above), **Moderate** (50 to 69) and **Lowest** (below 50). University ranking is deliberately not used as a deciding criterion.

## How It Works

1. **User input:** the student fills in a profile (level, field, interests, grade, IELTS, budget, career goal, preferred locations).
2. **Research:** a search API finds candidate pages, preferring official academic domains.
3. **Extraction:** page text is fetched and an LLM extracts structured fields from that text only.
4. **Verification:** each value is labelled `verified`, `estimated` or `not_found`.
5. **Enrichment:** missing key fields (fees, entry requirements, career outcomes) are looked up on other official pages about the same program.
6. **Scoring:** the engine scores each criterion, renormalises weights when data is missing, and computes risks.
7. **Recommendation:** results are ranked, tagged, explained and can be compared.

## Data Integrity Principles

- Official university and faculty websites are preferred over third-party sources.
- A value is `verified` only when it comes from an academic domain **and** appears in the fetched page text; otherwise it is `estimated`. Missing values are `not_found`.
- The AI never invents information: extraction is restricted to the provided page text, and explanations use only computed scores and extracted data.
- Missing criteria are excluded from the overall score instead of being guessed. If fewer than 40% of the weighting has data, the program is shown as "Insufficient data" rather than given a score.
- Every score is traceable to a note and, where applicable, a source URL.

## Architecture

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript (no framework) |
| Backend | Python 3.12, FastAPI |
| LLM | Any OpenAI-compatible, free-tier API (default: Groq) |
| Web search | Tavily-style search API |
| Data extraction | Python (httpx, Beautiful Soup) |
| Storage | In-memory only (no database, no authentication) |
| Deployment | Render |

### Project Structure

```text
university-compatibility-platform/
├── frontend/
│   ├── index.html       # profile form, results and comparison UI
│   ├── style.css
│   └── script.js        # API calls and rendering
├── backend/
│   ├── main.py          # FastAPI app, endpoints, in-memory sessions
│   ├── research.py      # search, page fetching, LLM extraction, verification
│   └── engine.py        # scoring, risk analysis, ranking, comparison
├── requirements.txt
├── start.sh / stop.sh   # optional local helper scripts (macOS/Linux)
├── .env                 # API keys (never committed)
├── LICENSE.md
└── references.md
```

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/analyze` | Research programs for a profile, then score, rank and explain them |
| POST | `/api/compare` | Compare 2 to 4 programs from a previous analysis |

Analysis sessions are kept in memory for one hour and are lost when the server restarts.

## Configuration

Settings are read from environment variables (a local `.env` file is supported).

| Variable | Description |
|---|---|
| `SEARCH_API_KEY` | API key for the search provider |
| `SEARCH_URL` | Search endpoint (default: Tavily) |
| `LLM_API_KEY` | API key for the LLM provider |
| `LLM_BASE_URL` | OpenAI-compatible base URL (default: Groq) |
| `LLM_MODEL` | Chat model name; provider model lists change, so choose a currently available chat model |

Keys must never be committed to version control.

## Quick Start

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# create .env with the variables above
uvicorn backend.main:app --reload
```

Then open the printed local address in a browser. On Render, use `pip install -r requirements.txt` as the build command and `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` as the start command.

## Known Limitations

- Result quality depends on the search API, the LLM and how each university publishes its data.
- Entry requirements are compared only when published as a percentage; ATAR and GPA scales are not converted.
- Exchange rates and living-cost figures in the engine are rough estimates and should be reviewed periodically.
- Free-tier APIs are rate limited, so large analyses can be slow or partially fail.
- Pages that depend heavily on JavaScript or block automated access cannot be read.
- Free hosting may sleep when idle, causing slow first requests.

## Roadmap

1. Core platform and UI
2. AI research and data extraction
3. Compatibility and evaluation engine
4. AI recommendation and comparison
5. Testing and deployment

Possible future work: persistent caching, ATAR/GPA conversion, more countries and programs, user accounts and saved shortlists.

## Disclaimer

UCRP is a decision-support tool. Scores are estimates built from publicly available information and may be incomplete or out of date. Always confirm fees, entry requirements, deadlines and visa conditions on the official university website before making decisions.

## License

Released under the MIT License. See [LICENSE.md](LICENSE.md).

See [references.md](references.md) for technologies and data sources.
