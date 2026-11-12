# Changelog

All notable changes to the AI Data Analyst Agent are documented in this file.

---

## v0.2.0 — Review-driven improvements

### Added

- **Multi-turn conversation support** — The agent now maintains a sliding window of up to 6 prior turns (question + SQL + answer summary) in `conversation_history`. When a user follows up with contextual questions like "now break that down by region", the planner receives the conversation history and can generate correct SQL without re-stating the full context.

- **Few-shot examples in planner prompt** — Three hand-crafted examples (revenue aggregation → `execute_sql`, bar-chart request → `both`, unanswerable question → `respond`) are appended to `PLANNER_SYSTEM` so the model reliably outputs valid JSON.

- **Robust JSON extraction with fence detection and retry** — `parse_plan()` now tries three strategies in order: (1) extract from a ` ```json ``` ` fenced block, (2) find the outermost `{…}` span, (3) flat single-object regex. On any parse failure a second LLM call is made with an explicit "output only raw JSON" prompt before raising.

- **Chain-of-thought arm K** — A new planner arm that appends "Think step by step before writing JSON." to the system prompt, included in the multi-arm sampling with temperature scaling.

- **Settings caching with file-mtime-based invalidation** — `load_settings()` now caches the parsed `.env` / settings dict and only re-reads disk when the file's mtime changes, eliminating redundant I/O on every request.

- **Structured JSON logging with request correlation IDs** — All log statements emit JSON records (`{"ts", "level", "msg", "request_id", ...}`). Every `/api/chat` request is assigned a UUID `request_id` that propagates through the LangGraph nodes, making traces fully searchable.

- **In-memory rate limiter on `/api/chat`** — A token-bucket limiter (10 req/min per IP by default, configurable via `RATE_LIMIT_RPM`) is applied as FastAPI middleware, returning HTTP 429 with a `Retry-After` header on excess.

- **Temperature > 0 warning** — On startup, if `OPENAI_TEMPERATURE` is set to `0`, a `WARNING` log is emitted reminding operators that temperature=0 disables multi-arm diversity and reduces planner robustness.

- **`pyproject.toml` with ruff / mypy / pytest configuration** — Project metadata, linting (ruff with `E,F,W,I,UP,B,C4,SIM` rule sets, line-length 100), type-checking (mypy, non-strict), and pytest options (`-v --tb=short`, sandbox marker) are now declared in `pyproject.toml`.

- **`.pre-commit-config.yaml`** — Pre-commit hooks for `ruff` (with `--fix`), `ruff-format`, trailing-whitespace, end-of-file-fixer, YAML syntax check, and large-file guard (500 KB limit).

- **Expanded golden evaluation suite (diverse questions)** — 10 new cases (q51–q60) added to `backend/db/golden.py`, covering: highest-salary department, open support tickets, marketing spend, HAVING-clause customer filter, max discount, post-2022 hires, ticket priority breakdown, product category count, average order line items, and top campaign by spend. Total: 60 golden cases.

---

## v0.1.0 — Initial release

- LangGraph agent with SQL planning, execution, and natural-language synthesis
- Multi-arm LLM sampling (temperature sweep)
- FastAPI backend with `/api/chat` and `/api/sessions` endpoints
- SQLite seed database (customers, products, orders, HR, marketing, support)
- Golden evaluation harness with 50 cases
