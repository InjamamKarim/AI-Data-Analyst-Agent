# AI Data Analyst Agent

A LangGraph analyst that answers questions about a local warehouse. SQL is read-only. Python runs in a separate process with an import allow-list and a file jail. The language model is [NVIDIA's free hosted API](https://build.nvidia.com/settings). The key is empty until you add it.

This machine was checked before the project was built: macOS, no `nvidia-smi` GPU, 8 GB of RAM, heavy compressor and swap pressure, and no Docker. Because of that, the app does not download weights, does not train, and does not call a paid sandbox.

## What is intentionally different from a paid stack

| Guide piece | This build |
| --- | --- |
| GPT-4o / Claude / DeepSeek via a paid key | `NVIDIA_API_KEY` left blank. Calls go only to `integrate.api.nvidia.com` |
| E2B code interpreter | Not installed and not called. Local subprocess sandbox |
| S3 / GCS chart upload | Charts are written under `artifacts/charts` and served by the API |
| LangSmith | Not enabled. Traces go to `logs/traces.jsonl` and `logs/audit.jsonl` |
| BIRD / Spider download | Not downloaded. Metrics and a 50-question suite run on the sample warehouse |

## Setup

```bash
python3 -m venv data-agent-env
source data-agent-env/bin/activate
pip install -r requirements.txt
python -m backend.db.seed
```

`.env` already exists with an empty key. When you want live answers, paste a free key from https://build.nvidia.com/settings into `NVIDIA_API_KEY` and leave the rest as-is. The next request reads the file; you do not need to edit code. The default model is `meta/llama-3.3-70b-instruct`. Change `NVIDIA_MODEL` if your account uses a different free model.

Do not point `NVIDIA_BASE_URL` at OpenAI or another paid host. The client refuses any host other than `integrate.api.nvidia.com` unless you set `NVIDIA_ALLOW_HOSTS` for a server you run yourself.

## Run

```bash
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 . Demo mode is on while the key is empty. It replays curated SQL for the 50 sample questions and labels that clearly. It is not a model score.

```bash
python -m backend.cli --examples
python -m backend.cli --demo "What was completed-order revenue in Q3 2024?"
```

Without `--demo`, and with the key still empty, the CLI tells you to add the key and does not invent a query. A destructive request such as "Delete all users from the database" is refused before any model call.

## Tests and evaluation

```bash
pytest -q
python -m eval.harness --demo --limit 5
python -m eval.ablation
```

`pytest` never calls NVIDIA. Three of the golden questions also draw a chart in the local sandbox.

Live scoring, after the key is set:

```bash
python -m eval.harness --live --limit 5
python -m eval.ablation --live --arms A,B,C --limit 3
```

Start with arms A–C. The offline ablation always runs: it checks that every gold query executes, that destructive SQL is blocked, and how much schema filtering shrinks the prompt. Execution accuracy stays blank until a live run. The sample percentages in the original guide are illustrations, not results from this database.

BIRD and Spider 2.0 are not bundled. `eval/benchmarks.py` explains where to place a local export if you add one later.

## How a turn works

1. **Prepare.** Load the schema. Arms D–J can drop unrelated tables. Arms E–J can attach a measured profile (row counts, date ranges, small categories). A destructive request stops here.
2. **Plan.** The model returns one JSON object: SQL, Python, both, a request for semantic notes, or a final answer. Demo mode substitutes the golden SQL instead of calling NVIDIA.
3. **Review.** If human review is on, the graph pauses with `interrupt()` until `/api/chat/resume` approves the plan.
4. **SQL.** One statement, `SELECT` or `WITH` only. Keywords are checked after comments are stripped and strings are masked. The SQLite login is also `query_only`. Rows sent back to the model are capped.
5. **Python.** Only if a chart or a second calculation was asked for. The child process cannot import sockets, subprocesses, or sqlite, and it cannot read or write outside its work directory (the interpreter's own libraries are readable). Charts are copied out before the work directory is left behind.
6. **Chart check.** The file must be a real PNG and the code must draw the requested chart type.
7. **Answer.** A table is always available. If Python fails three times, the SQL table is returned anyway.

Arm G is the full configuration: SQL, Python, schema filtering, profiling, and chart review. Arms H–J change only the documentation layout (semantic notes, notes fetched by a tool, or a preference for the `completed_lines` and `quarterly_revenue` views).

## Security checklist

- Read-only database role. Local SQLite uses URI `mode=ro` and `PRAGMA query_only`. For Postgres, start from `scripts/postgres_readonly_role.sql` and set `DB_CONNECTION_STRING`. The keyword guard is the second layer. Tests keep using SQLite even if that variable is set.
- Sandbox network. Sockets are disabled inside the child. E2B is ignored even if `E2B_API_KEY` is filled in. Docker is not required and was not present on this machine.
- CSV upload. Cells that start with `=`, `+`, `@`, or a non-numeric `-` are prefixed so a spreadsheet will not treat them as formulas. Column names are forced to plain identifiers. The file is loaded only into the local database, never written to an external one.
- Limits. Sandbox CPU and wall-clock timeout, 8 graph steps, 10 tool calls, and a token budget.
- Audit. Every plan, SQL hash, Python hash, block, and answer is appended to `logs/audit.jsonl`.
- Artifacts. PNGs are copied to `artifacts/charts` and served from `/api/artifacts/`. The sandbox directory is not the delivery path.

## Sample warehouse

`python -m backend.db.seed` rebuilds `data/analytics.db`. Sales tables are `customers`, `products`, `orders`, and `order_items`. Revenue is completed-order line revenue: `quantity * unit_price * (1 - discount)`. `hr_employees`, `marketing_campaigns`, and `support_tickets` exist so schema filtering has something to drop. The seed is deterministic (no random draws).

## Layout

```text
backend/agent     LangGraph, planners, arms
backend/tools     SQL tool, chart check, sandbox workspace
backend/sandbox   Local process runner
backend/security  SQL guard, AST allow-list, CSV neutralization, audit log
backend/schema    Catalog, filter, profile, context modes
backend/db        Seed and the Golden 50
backend/llm       NVIDIA client
backend/static    Chat page
eval              Metrics, harness, ablation
tests             Safety, sandbox, golden questions, API
```

## Host check

```bash
python scripts/check_host.py
```

If a GPU is present and its utilization is 70% or higher, the ablation entrypoint stops instead of adding local work. There is still no training job in this repository.
