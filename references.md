# References

## Frameworks and Libraries

| Technology | Purpose | Documentation |
|---|---|---|
| FastAPI | Backend web framework | https://fastapi.tiangolo.com |
| Uvicorn | ASGI server | https://www.uvicorn.org |
| Pydantic | Request validation and data models | https://docs.pydantic.dev |
| HTTPX | Async HTTP client for search and LLM calls | https://www.python-httpx.org |
| Beautiful Soup | HTML parsing and text extraction | https://www.crummy.com/software/BeautifulSoup/bs4/doc/ |
| python-dotenv | Loading environment variables from `.env` | https://pypi.org/project/python-dotenv/ |

## External Services

| Service | Purpose | Documentation |
|---|---|---|
| Tavily | Web search API used to find candidate program pages | https://docs.tavily.com |
| Groq | Free-tier, OpenAI-compatible LLM API used for extraction and explanations | https://console.groq.com/docs |
| Render | Hosting and deployment | https://render.com/docs |

## Data Sources

- Official university, faculty and school websites (course pages, fees pages, entry requirement pages), retrieved at analysis time. Each result stores the source URL it was extracted from.
- No university data is stored permanently; results exist in memory only and may change as university websites change.

## Estimated Values (Not Sourced)

The following values in `backend/engine.py` are rough estimates used only for approximate comparison. They are not taken from a cited source and should be replaced with sourced figures before any serious use:

- Currency exchange rates to AUD (`FX_TO_AUD`)
- Yearly living-cost estimates by country (`LIVING_COST_AUD`)
- Scoring thresholds and formulas (design choices, not published standards)

For up-to-date figures, use official sources such as central bank exchange rates and the living-cost guidance published by each destination country's government or study agency.

## Design Principles

The platform follows these project design rules: prefer official sources; distinguish verified, estimated and missing data; never let the AI generate information without a source; keep every score explainable and checkable; and never treat university ranking as the only deciding criterion.