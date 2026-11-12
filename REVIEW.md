# Senior Research Review: AI Data Analyst Agent

**Reviewer perspective:** Senior Researcher in AI Engineering & Data Science
**Date:** 2026-11-12
**Artifact under review:** `AI-Data-Analyst-Agent` — a LangGraph-based text-to-SQL agent with Python sandbox, chart generation, and ablation evaluation framework.

---

## 1. Executive Summary

This project implements a **multi-step agentic data analyst** that converts natural-language questions into SQL queries and Python visualizations against a local analytics warehouse. It is built on LangGraph with an explicit state machine, uses NVIDIA's free hosted LLM API, and ships with a 50-question golden evaluation suite and a 10-arm ablation study framework.

**Overall assessment: This is a well-engineered, security-conscious, and intellectually honest project.** It demonstrates strong systems thinking, disciplined scope control, and a level of defensive engineering rarely seen in portfolio-grade AI projects. The ablation framework and the clear separation between demo/scripted/live modes show research maturity. That said, there are meaningful architectural gaps, evaluation limitations, and design choices that would not survive peer review at a top venue without revision.

**Grade: B+ / Strong portfolio piece with clear paths to A-level work.**

---

## 2. Architecture & Design

### 2.1 Strengths

- **Explicit state graph over opaque chains.** The [graph.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/agent/graph.py) file defines every node and conditional edge of the LangGraph explicitly, with named routing functions. This is dramatically more debuggable, testable, and auditable than the common pattern of chaining LangChain `RunnableSequence` objects. Each node has a clear contract: read state → do work → return a partial state update. This is excellent engineering.

- **Defense-in-depth security model.** The SQL execution path has **four independent layers** of protection:
  1. Intent-level blocking of destructive natural-language requests ([sql_guard.py#L22-L43](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/security/sql_guard.py#L22-L43))
  2. SQL keyword guard with comment-stripping and string-masking ([sql_guard.py#L46-L73](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/security/sql_guard.py#L46-L73))
  3. Read-only database connection via SQLite `mode=ro` + `PRAGMA query_only` ([connection.py#L59-L71](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/db/connection.py#L59-L71))
  4. Human-in-the-loop review gate ([graph.py#L211-L236](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/agent/graph.py#L211-L236))

  This is the correct pattern. The test `test_compromised_planner_cannot_run_dml` in [test_agent.py#L33-L49](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/tests/test_agent.py#L33-L49) demonstrates threat modeling awareness — it simulates a compromised planner injecting DML and proves the guard catches it.

- **Ablation study design.** The 10-arm ablation in [arms.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/agent/arms.py) is well-structured: arms A–C isolate individual tool contributions, D–F add capabilities incrementally (schema filter → profile → chart review), G is the full agent, and H–J vary the documentation delivery strategy. This is a proper controlled experiment.

- **Honest demo/live separation.** The project is transparent that demo mode replays curated SQL and is not a model score. This is stated in the README, in the CLI output, in the harness, and in the code comments. In an era of inflated LLM demo claims, this intellectual honesty is notable.

### 2.2 Weaknesses

> [!WARNING]
> **Single-turn architecture limits real-world utility.** The agent has no memory across questions. Each `run_agent()` call creates a fresh `Session()`. The `messages` field in state uses LangGraph's `add_messages` reducer, but only the initial user message is injected — there is no mechanism to carry forward prior context, SQL results, or conversation history. A real analyst would say "now break that down by region" after a revenue question. This agent cannot do that.

- **No multi-turn conversation support.** While `thread_id` is tracked, it is only used for the HITL resume flow. There is no retrieval of prior state from earlier turns.

- **Single LLM call per planning step.** The `NvidiaPlanner` makes one `complete()` call and expects the model to return a fully-formed JSON plan. There is no chain-of-thought prompting, no self-correction on malformed output, and no multi-step reasoning. The `parse_plan` fallback on JSON parse failure is a dead-end `respond` with "try rephrasing." A more robust design would retry with a repair prompt.

- **No streaming.** The FastAPI `/api/chat` endpoint blocks until the entire graph completes. For complex queries with SQL + Python + chart generation, this could take 10–30 seconds. There is no SSE/WebSocket streaming of intermediate results.

---

## 3. Security Analysis

### 3.1 Strengths

The security posture is genuinely impressive for a project of this scope:

- **Python sandbox is thorough.** The [local_sandbox.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/sandbox/local_sandbox.py) runner monkey-patches `builtins.open`, `os.open`, blocks 20+ dangerous `os` functions, neuters `socket`, `subprocess`, `sqlite3`, `shutil`, and `urllib.request`, installs a `MetaPathFinder` to ban dangerous imports, sets `RLIMIT_CPU` and `RLIMIT_FSIZE`, and strips API keys from the child environment. The `_Banner.find_spec` method even handles the subtlety that numpy/matplotlib internally import `pickle`/`ctypes` during initialization — it checks the call stack to distinguish user-code imports from library-internal ones.

- **CSV formula injection defense.** The [csv_sanitize.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/security/csv_sanitize.py) module prefixes cells starting with `=`, `+`, `@`, `\t`, `\r`, and non-numeric `-` with a single quote. This prevents spreadsheet formula injection attacks.

- **AST guard before execution.** The [ast_guard.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/security/ast_guard.py) performs static analysis before any code reaches the subprocess, blocking `eval`, `exec`, `__import__`, dunder attribute access, and imports outside the allowlist.

### 3.2 Vulnerabilities & Gaps

> [!CAUTION]
> **The Python sandbox is not a true sandbox.** It relies on monkey-patching in-process. A determined adversary with control over the generated Python code could bypass it:
> - `importlib.import_module("os")` returns the *already-patched* `os`, but the original functions can be recovered from `types.ModuleType.__subclasses__()` or from `object.__subclasses__()` traversal.
> - `ctypes` is banned from user code, but if the `_Banner.find_spec` stack-walk heuristic is fooled (e.g., via a decorator that clears the frame), `ctypes` could be imported and used to call arbitrary C functions.
> - The `resource.setrlimit` call silently fails on macOS for `RLIMIT_FSIZE`, providing no file-size limit on the platform the project was built for.

The README acknowledges this is "not a VM" and "the stand-in for E2B / Docker," which is fair. But the test suite should include adversarial bypass attempts, not just known-bad imports.

- **SQL guard has edge cases.** The regex-based keyword guard blocks `INTO` as a standalone token, which would also block `SELECT ... CAST(x AS INTEGER) INTO ...` — but more importantly, it does not handle SQLite-specific vectors like `SELECT load_extension(...)` which is blocked only as `LOAD_EXTENSION` (all caps in the regex with `re.IGNORECASE`, so this works), but not `ATTACH` combined with a read-only connection trick. The layered defense makes this unlikely to be exploitable, but a proper SQL parser (e.g., `sqlglot`) would be more robust than regex.

- **No rate limiting or authentication** on the FastAPI endpoints. The `/api/chat` endpoint can be called by anyone, and each call creates an NVIDIA API request (in live mode). This is a DoS and cost-amplification vector.

---

## 4. Evaluation Framework

### 4.1 Strengths

- **Execution accuracy (EX)** is computed correctly: the agent's SQL is re-executed and compared row-by-row against the gold SQL's output, with proper normalization in [metrics.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/eval/metrics.py) (rounding floats, handling NaN/Inf, ordered vs. unordered comparison).

- **Valid Efficiency Score (VES)** implementation is a reasonable simplification: $\min(1, \sqrt{t_{\text{gold}} / t_{\text{predicted}}})$ for correct results, 0 for incorrect. The cap at 1.0 is explicitly documented as a design choice.

- **Safe SQL Rate** is measured both on the golden suite and on an adversarial probe set of 8 malicious queries in [ablation.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/eval/ablation.py#L24-L33).

### 4.2 Weaknesses

> [!IMPORTANT]
> **The golden evaluation is self-referential.** The 50 golden questions in [golden.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/db/golden.py) are hand-written against the same schema that the seed script creates. The scripted planner *replays* these exact SQL statements. A demo-mode score of 100% EX is tautological — it proves the plumbing works, not the model. The README says this, but the evaluation report format (`EX 100.0%`) could easily be mistaken for a model capability claim.

- **No external benchmark results.** BIRD and Spider 2.0 are referenced but not bundled, and no results are reported. This makes it impossible to compare this system's performance to published baselines. For a research contribution, this is a significant gap.

- **Golden questions lack diversity.** Of the 50 questions, ~35 are revenue aggregations with different filters. The suite has very few:
  - Multi-hop reasoning questions (e.g., "Which region's top customer also bought the cheapest product?")
  - Ambiguous questions requiring clarification
  - Questions that require handling NULL values or edge cases
  - Questions about empty result sets
  - Questions that the schema *cannot* answer (only q59's absence from the set is tested, via the "unladen swallow" test)

- **Token estimation is crude.** `estimate_tokens` in [config.py#L136-L139](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/config.py#L136-L139) divides string length by 4. This is a rough heuristic (typical BPE tokenizers produce ~1.3 tokens per word, or ~1 token per 3.5–4.5 characters for English), but it's used for budget enforcement. Off-by-2x estimates could prematurely terminate legitimate queries or fail to stop runaway ones.

---

## 5. Code Quality & Engineering

### 5.1 Strengths

- **~4,400 lines of Python** for the entire system including tests and evaluation. This is admirably compact. No unnecessary abstractions, no dead code, no framework bloat.

- **Test coverage is well-targeted.** The 8 test files cover:
  - All 50 golden questions parametrically ([test_agent.py#L10-L20](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/tests/test_agent.py#L10-L20))
  - Safety: destructive requests, compromised planner DML injection, reader connection write rejection
  - Sandbox: AST guard, runtime socket blocking, file escape, timeout, chart validation
  - API: health endpoint key hiding, demo mode, CSV upload formula neutralization
  - HITL: rejection, approval, error recovery
  - Edge cases: unknown planner mode, missing API key, workspace path traversal

- **Dependency list is minimal and pinned.** 13 packages in [requirements.txt](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/requirements.txt), all with minimum versions. No unnecessary imports.

- **Deterministic seed data.** The [seed.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/db/seed.py) uses arithmetic progressions instead of `random` for all synthetic data. This means tests are perfectly reproducible.

### 5.2 Weaknesses

- **Global mutable state.** The catalog cache (`_cache` in [catalog.py#L97](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/schema/catalog.py#L97)), engine singletons (`_reader`, `_writer` in [connection.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/db/connection.py)), and the session singleton in [service.py#L131-L140](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/agent/service.py#L131-L140) are all module-level global mutable variables. This makes testing more fragile (tests must remember to call `invalidate_catalog()` and `reset_engines()`) and would cause issues in multi-worker deployments.

- **No type checking or linting configuration.** No `mypy.ini`, `pyproject.toml` with tool configs, `ruff.toml`, or `.pre-commit-config.yaml`. The type annotations are inconsistent: some functions use `str | None` (Python 3.10+), others use `Optional[str]`.

- **No logging configuration beyond `basicConfig`.** The [main.py lifespan](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/main.py#L35-L39) sets up `basicConfig` at `INFO` level. There is no structured logging, no request correlation IDs, and no log level configuration via environment variables.

- **The `get_settings()` function re-reads `.env` on every call.** This hits the filesystem on every request. While `dotenv_values` is cheap, caching with a TTL or reading once at startup would be more appropriate.

---

## 6. LLM Integration & Prompt Engineering

### 6.1 Strengths

- **Provider lock-in prevention.** The `assert_free_endpoint()` function in [config.py#L124-L133](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/config.py#L124-L133) actively refuses to call any host other than NVIDIA's free API, preventing accidental billing. API keys are explicitly passed to `ChatOpenAI()` rather than relying on environment variables, preventing a stray `OPENAI_API_KEY` from redirecting calls.

- **Clean prompt structure.** The [prompts.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/agent/prompts.py) system prompt is concise, structured, and includes explicit negative instructions ("Never emit INSERT..."). The input renderer includes the error from the previous attempt, enabling self-correction loops.

### 6.2 Weaknesses

- **No few-shot examples in the prompt.** The planner prompt contains rules but no examples of correct input→output mappings. For text-to-SQL with Llama 3.3 70B, few-shot prompting typically improves EX by 5–15 percentage points (cf. DIN-SQL, DAIL-SQL).

- **JSON extraction is fragile.** `parse_plan()` in [planner.py#L78-L98](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/agent/planner.py#L78-L98) uses `re.search(r"\{.*\}", text, re.DOTALL)` to find the first `{...}` in the model output. This greedy match fails on nested JSON objects (it stops at the *last* `}` due to `re.DOTALL`), and it fails entirely if the model wraps the JSON in a markdown code fence with extra text after the closing brace. A more robust approach: ask the model for ```json fenced output, extract between the fences, or use a JSON repair library.

- **No prompt versioning or A/B testing infrastructure.** The system prompt is a hardcoded string. Changes require code changes and redeployment. A template-based system with version tracking would enable systematic prompt optimization.

- **Temperature 0 is the default but not enforced.** While `NVIDIA_TEMPERATURE` defaults to "0", it can be overridden by environment variable. For text-to-SQL where determinism matters, temperature 0 should be the strongly recommended setting, with a warning if overridden.

---

## 7. Schema Filtering & Data Profiling

### 7.1 Strengths

- **Token-overlap schema filter** in [filter.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/schema/filter.py) is a practical heuristic: tokenize the question, intersect with table/column/keyword tokens, keep matches plus their foreign-key parents. This reduces prompt size (the ablation measures the reduction) and focuses the model.

- **Data profiling** in [profile.py](file:///Users/injy/Desktop/RAG_projects/AI-Data-Analyst-Agent/backend/schema/profile.py) provides row counts, date ranges, and categorical value distributions. This is the kind of grounding information that dramatically reduces hallucinated filter values.

### 7.2 Weaknesses

- **Schema filter uses bag-of-words, not embeddings.** The token overlap approach will fail on synonyms ("income" → `revenue`, "clients" → `customers`). An embedding-based similarity (even a simple one using sentence-transformers) would be more robust. The project constrains itself to no local model loading, which explains this choice, but it's a significant accuracy limitation.

- **No schema linking.** Modern text-to-SQL systems (RESDSQL, DIN-SQL, CHESS) perform explicit schema linking: mapping question entities to specific columns and values. This project skips that step entirely, relying on the LLM to do implicit schema linking from the prompt.

---

## 8. Comparison with State of the Art

| Aspect | This Project | SOTA (2024–2025) |
|--------|-------------|------------------|
| **Text-to-SQL approach** | Single-pass LLM prompt | Multi-agent decomposition (MAC-SQL, CHESS) |
| **Schema linking** | Bag-of-words filter | Embedding + cross-encoder (RESDSQL) |
| **Self-correction** | Re-plan on SQL error (up to 8 iterations) | Execution-based refinement + LLM reflection |
| **Benchmark evaluation** | Custom 50-question suite | BIRD (12,751 questions), Spider 2.0 |
| **Reported EX** | Not reported (demo only) | 72–75% on BIRD dev, 85%+ on Spider 1.0 |
| **Visualization** | Matplotlib via sandbox | Not typically evaluated |
| **Security** | 4-layer defense | Rarely addressed |
| **Ablation** | 10 arms, systematic | Varies, often ad hoc |

> [!NOTE]
> The project's strongest differentiators versus typical portfolio projects are its security model and its ablation study discipline. Its weakest area relative to research state-of-the-art is the text-to-SQL pipeline itself, which lacks schema linking, few-shot prompting, and multi-step reasoning decomposition.

---

## 9. Recommendations

### High Priority (would significantly improve the project)

1. **Add multi-turn conversation support.** Maintain a sliding window of prior (question, SQL, summary) pairs in the state. This is low-hanging fruit that dramatically improves usability.

2. **Add few-shot examples to the planner prompt.** Select 3–5 diverse examples from the golden 50 that demonstrate the expected JSON format, multi-table joins, date filtering, and chart requests.

3. **Run and report BIRD dev-set results.** Even on a subset (100–500 questions), this would position the project against published baselines. The harness is already built; only the data needs to be loaded.

4. **Replace regex JSON extraction with a robust parser.** Use `json_repair` or fence-based extraction. Add retry with a repair prompt on parse failure.

### Medium Priority (would improve robustness)

5. **Add rate limiting** to the FastAPI endpoints (e.g., `slowapi` or a simple token bucket).

6. **Add structured logging** with request IDs that correlate through the graph execution trace.

7. **Cache `get_settings()`** with a configurable TTL or read-once-at-startup pattern.

8. **Add a `pyproject.toml`** with mypy, ruff, and pytest configuration. Pin exact versions in a lockfile.

### Lower Priority (nice-to-have for research credibility)

9. **Add embedding-based schema filtering** as an ablation arm (K). Compare token overlap vs. cosine similarity.

10. **Add a chain-of-thought prompting arm.** Compare single-pass JSON output vs. "think step by step, then output JSON."

11. **Stream intermediate results** via SSE or WebSocket to improve perceived latency.

---

## 10. Final Remarks

This project demonstrates a level of engineering discipline and security awareness that places it well above the median AI portfolio project. The explicit LangGraph state machine, the defense-in-depth security model, the deterministic seed data, the honest demo/live separation, and the 10-arm ablation framework all reflect mature systems thinking.

The primary gaps are:
- **No live model results** make it impossible to evaluate the actual AI capability
- **Self-referential evaluation** (golden questions against own schema) does not measure generalization
- **Missing SOTA techniques** (schema linking, few-shot, multi-step reasoning) in the text-to-SQL pipeline

The project would benefit most from running against an external benchmark and adding multi-turn support. These changes are well within reach given the existing architecture.

> [!TIP]
> **If this is intended for a research publication**, focus on the ablation study as the contribution: "What does each component (schema filter, profile, chart review, documentation mode) add to a text-to-SQL agent?" Run BIRD dev with all 10 arms and report the EX/VES deltas. That's a solid empirical contribution.
>
> **If this is intended as a portfolio piece**, the project is already strong. Add BIRD results, multi-turn support, and streaming to make it stand out.
