# AgentShield: Known Limitations & Architectural Trade-offs

This document consolidates the architectural boundaries, security trade-offs, and environmental constraints of AgentShield as of the final evaluation milestone.

---

## 1. Operating System Environment: Windows Host Only

- **Platform Scope**: All development, testing, and evaluation runs were executed directly on the **Windows host platform** (Windows 11, PowerShell, CPython 3.11 via virtual environment). Linux container orchestration (Docker/WSL) was skipped.
- **Filesystem & Path Divergences**:
  - Windows filesystems (NTFS) are case-preserving but case-insensitive by default, whereas production Linux deployments are strictly case-sensitive.
  - Windows supports legacy 8.3 short names (e.g., `RUNTIM~1`), Alternate Data Streams (ADS, e.g., `file.txt:hidden_stream`), and reserved DOS device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`).
  - Production deployments on Linux must independently validate path canonicalization under Linux POSIX semantics.

---

## 2. Docker Compose Infrastructure Never Executed End-to-End

- **Unverified Compose Orchestration**: The repository includes a `docker-compose.yml` specification defining multi-container service configurations (PostgreSQL, Jaeger OTLP collector, FastAPI gateway, React frontend). This compose file was **never executed or verified end-to-end** during development or evaluation.
- **Runtime Reality**: All services, mock endpoints, and test suites were run directly as host processes against SQLite and localhost loopback interfaces. Claims regarding multi-container docker deployment readiness remain unverified.

---

## 3. Scripted Mock Agents (Not Live LLMs)

- **Deterministic Logic**: The agents in the evaluation harness (`SqlAgent`, `WebAgent`, `FileShellAgent`, `LoopingAgent`) are **scripted mock agents**, not live LLM instances.
- **Scope of Benchmark Findings**: The benchmark results measure AgentShield's ability to intercept and evaluate deterministic tool call patterns; they do **not** reflect how live LLM models reason, hallucinate, drift under temperature variance, or respond to conversational multi-turn jailbreaks.
- **Prompt Guardrail Omission**: The prompt-only guardrail baseline was excluded from empirical evaluation tables because external LLM provider API credentials were not provisioned; mock LLMs cannot simulate stochastic prompt adherence.

---

## 4. Single-Author Test Suites & Effective Diversity

- **Shared-Author Bias**: Both the detection mechanisms and the evaluation test suites (including the 20 held-out unsafe scenarios and the 50 replay regression variants) were authored by the same system/author. This introduces shared-author blind spots.
- **Template Expansion**: The 90 standard benign tasks derive from 3–4 prompt templates per agent expanded across parameter values. Consequently, effective semantic diversity is lower than 90 independent prompts, and reported confidence intervals are narrower than what true independent distributions would exhibit.

---

## 5. Cooperative In-Process SDK Enforcement

- **In-Process Boundary**: Policy checks are triggered by SDK decorators (`@trace_tool_call`, `@trace_model_call`) executing within the same process space as the agent application.
- **Threat Model Scope**: AgentShield's threat model assumes a **misbehaving, prompt-injected, hallucinating, or budget-exceeding LLM**, not hostile host agent code.
- **Bypass Surface**: If an agent process is written to deliberately circumvent the SDK decorators, or if host code opens direct socket connections or subprocess calls without decorators, it bypasses gateway policy checks.
- **Production Hardening**: Securing against uncooperative or compromised host agent code requires network-level egress enforcement (e.g., sidecar proxies, iptables rules, Landlock LSM, or kernel containers) where tool credentials are withheld from the host process.

---

## 6. Storage Engine: Tested Exclusively on SQLite

- **Single Engine Validation**: All automated test suites, migrations, concurrency tests, and live demonstrations were executed strictly against SQLite (`agentshield.db` or in-memory `:memory:`).
- **PostgreSQL Untested**: PostgreSQL-specific behaviors—including JSONB querying, `SELECT ... FOR UPDATE` row locks, dialect-specific datetime handling, and production connection pooling—have **not been tested** in this environment. Claims of PostgreSQL readiness remain unverified until validated against a live PostgreSQL server.

---

## 7. Telemetry & OTLP Collector Verification

- **Schema Validated**: OpenTelemetry span generation and attribute formatting (`gen_ai.request.model`, `gen_ai.usage.prompt_tokens`, `tool.name`, etc.) are validated via unit tests against standard OTLP schemas.
- **No Live Jaeger Collector Verification**: Telemetry has not been validated against a live, running Jaeger collector instance (e.g., via `localhost:16686` or Jaeger query APIs).

---

## 8. Time-of-Check to Time-of-Use (TOCTOU) on File Paths

- **Pre-Execution Check**: `check_path_safety` canonicalizes paths using `os.path.realpath(os.path.abspath(target_path))` and checks containment within allowed roots before the tool function executes.
- **Race Condition Window**: In non-isolated environments, a race condition exists between the gateway policy check and tool execution. An asynchronous process could swap an allowed directory with a symlink or rename target directories during this window (TOCTOU).

---

## 9. SQL Tautology Detection is Best-Effort Heuristic Matching

- **Computational Complexity (Boolean SAT)**: Determining whether an arbitrary SQL `WHERE` expression is universally true (tautology) across all database rows is NP-complete, and undecidable for SQL dialects supporting complex expressions and subqueries.
- **AST Pattern Heuristics**: AgentShield uses syntactic AST inspection via `sqlglot` to detect common tautologies (e.g., `1=1`, `'a'='a'`, `id=5 OR 1=1`). Complex semantic identities (e.g., mathematical identities) or schema-dependent tautologies (e.g., `WHERE id >= 0` on unsigned columns) will pass syntactic checks without a formal theorem prover.

---

## 10. Client-Reported Running Metrics (Cost, Tokens, Steps)

- **Running Metric Provenance**: The running cost (`current_running_cost`), token usage (`current_total_tokens`), and step count (`current_step_count`) sent in `/gateway/check` requests are tracked in-process by the SDK and reported by the client.
- **Security Boundary**: A compromised agent process could underreport running metrics to delay budget limit enforcement. In contrast, **elapsed wall-clock time is computed server-side** directly from the run's `started_at` timestamp recorded in the database.

---

## 11. Budget Limits Enforced Exclusively at Tool-Call Boundary

- **Tool-Call Check**: Cost, token, and step count caps are evaluated inside `/gateway/check` when an agent attempts a tool invocation.
- **Limitation**: An agent run that executes multiple expensive model inference cycles without invoking any external tools will not invoke `/gateway/check` and therefore will not be halted mid-run by gateway budget caps until its next tool call attempt (or until post-run ingestion).

---

## 12. Heuristic Prompt-Injection Screening: Defense-in-Depth Baseline

- **Heuristic Nature**: The prompt injection screening layer employs bounded regex patterns and Unicode normalization to detect obvious instruction overrides, role spoofing, hidden text, and base64-encoded instructions.
- **Evasion Vectors**:
  - Novel, subtle, conversational rephrasings that do not trigger keyword patterns bypass syntactic regexes.
  - While base64 is decoded recursively up to depth 2, other encodings (URL percent-encoding, hex escapes, compression) are unhandled.
  - Regexes cannot defend against sophisticated adversarial perturbations (e.g., suffix attacks, multi-turn state poisoning).
- **Oversized Payloads**: Outputs exceeding 500KB fail closed with a security error to prevent truncation bypass.

---

## 13. Incident Replay: Redaction Markers & Circular Dynamic Labeling

- **Redaction Artifacts in Replay**: Stored traces have sensitive credentials redacted with `[REDACTED:...]` tokens. When replaying a trace against a candidate model, the agent receives redacted tokens instead of raw credentials.
- **Frozen-Output Matching Brittleness**: Raw-string argument matching fails when queries undergo minor surface changes that fall below the 0.85 cache-match threshold (e.g. 0.7710 for table prefixes in `test_ben_04` and 0.8000 / 0.8161 for comment prefixes in `test_ben_11`), causing cache misses that flip task outcomes and zero out run fidelity. An AST-aware SQL matcher would easily resolve these variations.
- **Dynamic Labeling Circularity**: Ground-truth labels must not be derived from the replay mechanism itself, as replay cache misses will falsely classify benign paraphrases as regressions. Ground-truth labels must be determined by construction or against a live environment.

---

## 14. Model Comparison Analytics (RQ3): Implemented, Not Empirically Validated

- **Implementation Scope**: Analytical algorithms for tracking run costs, task completion rates, outlier latency detection (IQR method), and cross-model pairwise performance comparisons are implemented in `server/app/services/analytics_service.py` and covered by unit tests in `tests/test_analytics_anomalies.py`.
- **Validation Boundary**: These metrics have **not been empirically validated** against actual model or prompt selection outcomes in live trials. They represent an unvalidated software feature, not an empirical research finding; no claims are made regarding their ability to predict model quality.

---

## 15. SQL Multi-Statement Parsing: Per-Statement AST Scoping

- **Behavior & Rationale**: Rather than rejecting multi-statement queries outright (since agents may issue batched queries or semicolon-delimited read-only scripts such as `SELECT id FROM users; SELECT * FROM orders;`), `sql_select_only` enforces **fail-closed per-statement AST verification**. `sqlglot` parses all statements in the input, and each statement is independently checked against operation allowlists and WHERE clause mandates. If any statement in the input is unpermitted or lacks required clauses, the entire invocation is rejected immediately.
- **Latency & Bug Fix**: A latent scoping bug in earlier iterations where AST traversal nodes were overwritten by subsequent statements was fixed post-freeze by scoping AST walks per statement (`stmt.walk()`). The evaluation policies default to SELECT-only, so the latent bug never affected any evaluation outputs.

---

## 16. Live Real-World API Integrations: Demo Surface, Not Evaluation Evidence

- **Out of Evaluation Scope**: The live integrations under `server/app/services/live_integrations.py` (surfaced via `/live-agent/*` and the dashboard's *Live Agent Lab*) are a **demonstration and integration surface**. They are **not** part of the RQ1–RQ3 evaluation, and none of the benchmark claims in `CLAIMS.md` depend on them. The published prevention, false-block, replay, and overhead numbers continue to derive exclusively from the scripted mock agents.
- **Default State is Simulated**: With no credentials configured, every keyed provider (Gemini, OpenAI, Stripe, SendGrid, Slack, Twilio) runs a labelled simulation. Simulated calls carry `execution_mode: "simulated"` in the API response and on the telemetry span, and the dashboard renders this as a distinct badge — a simulated call is never presented as a real one.
- **Unverified Live Keyed Paths**: The live code paths for Stripe, SendGrid, Slack, and Twilio were **not exercised against real credentials** during development and are unverified. Only the zero-key public providers (GitHub, Open-Meteo, Hacker News) and urlscan.io reputation lookups were validated end-to-end against live network calls.
- **Denylist is a Curated Sample**: The URL reputation check consults a small curated phishing-domain sample as an offline fallback. This is illustrative of the gate's wiring and is **not** a comprehensive threat feed; do not treat it as production-grade phishing detection.
- **Pricing Table Snapshot**: LLM cost figures are computed from a table stamped with an as-of date and overridable via `PRICING_CONFIG_PATH`. Provider list prices drift, so absolute cost figures are estimates at best; unknown models return a null cost rather than appearing free.
- **Network Egress Dependency**: Live mode requires outbound internet access. Set `LIVE_ALLOW_NETWORK=false` to force all providers into their labelled simulations for hermetic demonstrations or CI.

