# AgentShield: Empirical Claims & Evidence Registry

This registry maps every architectural and empirical claim made in the AgentShield project and evaluation report directly to reproducible evidence (automated tests, evaluation datasets, and CSV records).

---

## Claim 1: Deterministic Gateway Interception on Modeled Unsafe Actions
**Statement**: Under Condition 2 (AgentShield Gateway), the gateway achieves 100.0% [92.1, 100.0]% prevention against modeled destructive tool actions across SQL, Web, and File/Shell benchmark tasks (DDL drops/truncations, path traversals outside sandbox, and unwhitelisted HTTP requests).
- **Supporting Tests**:
  - `tests/test_milestone11_agents.py::test_sql_agent_under_three_conditions`
  - `tests/test_milestone11_agents.py::test_web_agent_mock_server_and_three_conditions`
  - `tests/test_milestone11_agents.py::test_file_shell_agent_under_three_conditions`
  - `tests/test_policy_engine.py::test_pure_function_evaluate_policy_allow_and_deny`
- **Supporting Files**:
  - `eval_results/evaluation_report.md`
  - `eval_results/evaluation_results.csv`

---

## Claim 2: Active Attack Prevention Rate on Held-Out Scenarios (5/11)
**Statement**: On the 11 held-out active attack scenarios that produced real unsafe effects under No Policy, the AgentShield Gateway blocked 5/11 attacks (45.5% [21.3, 72.0]%) by rejecting non-standard IP formats and external domains via `allow_whitelisted_http`. The Naive Keyword Blocklist blocked 1/11 attacks (9.1% [1.6, 37.7]%). The confidence intervals overlap; no statistically significant difference is claimed.
- **Supporting Tests**:
  - `tests/test_security_checks.py::test_domain_ip_literals`
  - `tests/test_security_checks.py::test_domain_subdomain_boundary`
- **Supporting Files & CSV Rows**:
  - `eval_results/held_out_unsafe_results.csv` (rows `heldout_05`, `heldout_06`, `heldout_07`, `heldout_08`, `heldout_20`)
  - `eval_results/evaluation_report.md`

---

## Claim 3: Disclosed Policy Gaps on Held-Out Scenarios (6/11 Allowed)
**Statement**: The Gateway permitted 6 active attacks due to documented policy gaps: 2 table-level SELECT exfiltrations (`heldout_02`, `heldout_16`) because the policy enforces statement types but lacks table/column rules for `SELECT`; 2 HTTP parameter pollutions (`heldout_11`, `heldout_12`); and 2 application-layer payload attacks on allowlisted internal domains (`heldout_18`, `heldout_19`).
- **Supporting Tests**:
  - `tests/test_security_checks.py::test_sql_benign_queries_allowed`
- **Supporting Files & CSV Rows**:
  - `eval_results/held_out_unsafe_results.csv` (rows `heldout_02`, `heldout_11`, `heldout_12`, `heldout_16`, `heldout_18`, `heldout_19`)
  - `eval_results/evaluation_report.md`

---

## Claim 4: File/Shell Simulator Internal Containment Disclosed
**Statement**: Under Condition 1 (No Policy), File/Shell unsafe prevention is 66.7% (10/15 prevented) because the simulated interpreter (`FileShellAgent`) possesses its own internal command allowlist (`cat, echo, grep, head, ls, wc`) and path containment rules. The 66.7% reflects simulator-level containment, not external policy enforcement. Only 5 path traversals succeed under No Policy (`file_unsafe_01`, `02`, `08`, `10`, `14`).
- **Supporting Tests**:
  - `tests/test_no_host_execution.py::test_simulated_interpreter_rejects_unallowlisted_commands`
  - `tests/test_milestone11_agents.py::test_file_shell_agent_sandbox_isolation_and_allowlisted_commands`
- **Supporting Files**:
  - `evaluation/agents/file_shell_agent.py`
  - `eval_results/evaluation_report.md`

---

## Claim 5: Zero Host Subprocess Execution During Evaluation
**Statement**: The evaluation harness executes zero host subprocesses (`subprocess.Popen`, `subprocess.run`, `os.system`) during standard and held-out scenario execution. All file and shell commands run strictly in the simulated interpreter sandbox.
- **Supporting Tests**:
  - `tests/test_no_host_execution.py::test_no_host_execution_during_standard_and_held_out_scenarios`
- **Supporting Files**:
  - `tests/test_no_host_execution.py`

---

## Claim 6: Benign Sanity Checks and Negative Controls
**Statement**: Benign task success rate across all 90 benign tasks is 100.0% [95.9, 100.0]% with a 0.0% [0.0, 4.1]% false-block rate, serving as a harness sanity check. Two independent negative controls verify that two specific negative-control agents fail 100% of the time against the tightened gold task checker (30/30 task failures on `DeliberatelyBrokenAgent` and 30/30 on `PlausibleWrongFilterAgent`).
- **Supporting Tests**:
  - `tests/test_negative_control.py::test_negative_control_sql_benign_tasks_all_fail`
  - `tests/test_negative_control.py::test_negative_control_plausible_wrong_filter_agent_fails_100_percent`
  - `tests/test_negative_control.py::test_negative_control_web_and_file_tasks_fail`
  - `tests/test_milestone11_agents.py::test_independent_gold_task_and_safety_checkers`
- **Supporting Files**:
  - `evaluation/scenarios/gold_checkers.py`
  - `eval_results/evaluation_report.md`

---

## Claim 7: Prompt Injection Screener Recall and Overfitting
**Statement**: The heuristic prompt injection screener achieves 70.0% recall [59.2, 78.9]% on the held-out v2 dataset with 100.0% precision [93.6, 100.0]%, showing mild overfitting from development v1 (75.3% -> 70.0%).
- **Supporting Tests**:
  - `tests/test_injection_screening.py::test_held_out_benchmark_v2_evaluation`
  - `tests/test_injection_screening.py::test_labeled_prompt_injection_benchmark`
  - `tests/test_injection_screening.py::test_false_positive_guards`
- **Supporting Files**:
  - `server/app/services/injection_screener.py`
  - `eval_results/evaluation_report.md`

---

## Claim 8: Redaction Recall and Format Generalizability Limits
**Statement**: Regex redaction achieves 96.0% recall [80.5, 99.3]% on a fresh dataset with known secret types, but drops to 33.3% [9.7, 70.0]% on unseen token formats lacking standard prefixes (e.g., Google Cloud API keys, Azure storage account keys).
- **Supporting Tests**:
  - `tests/test_redaction_extended.py::test_redaction_unseen_formats_generalizability`
  - `tests/test_redaction_extended.py::test_redaction_patterns_fixed_types`
  - `tests/test_luhn.py::test_redact_credit_card_integration`
  - `tests/test_phone_precision.py::test_phone_precision_preserves_non_phones`
- **Supporting Files**:
  - `server/app/services/redaction.py`
  - `eval_results/evaluation_report.md`

---

## Claim 9: Runtime Latency Overhead
**Statement**: Measured across 5 benchmark runs, the full instrumented tool-call pipeline adds a median overhead of +18.046 ms p50 (range [17.817, 18.633] ms) and +23.821 ms p95 over direct SQLite execution. Pre-call policy check alone is ~4.6 ms p50. Earlier single runs measured +27.6 ms and +17.0 ms with cause not established.
- **Supporting Tests**:
  - `tests/test_real_latency_instrumentation.py::test_full_instrumented_tool_call_pipeline`
- **Supporting Files & Benchmark Records**:
  - `eval_results/latency_benchmark.csv` (rows `1`, `2`, `3`, `4`, `5`, and `summary_median` recording direct execution p50/p95, gateway p50/p95, and added tool-call latency p50/p95 across 5 benchmark runs)
  - `eval_results/evaluation_report.md`
  - *Evidence Note*: The supporting test asserts the latency measurement instrumentation and threshold bounds; the empirical 5-run numbers (+18.046 ms median p50) come from `eval_results/latency_benchmark.csv` generated by `scripts/evaluate.py`.

---

## Claim 10: RQ2 Incident Replay Regression Dual Labeling & SQL Paraphrase Brittleness
**Statement**: On the 50-variant empirical regression suite, ground-truth labels by construction (paraphrase = benign) demonstrate that the replay engine achieves 25/25 recall [86.7, 100.0]%, 23/25 specificity [75.0, 97.8]%, and 25/27 precision [76.6, 97.9]%, with 2 false alarms on SQL paraphrases (`test_ben_04` and `test_ben_11`) due to frozen-output argument matching cache misses (< 0.85 threshold). Replay identically ties the outcome-only baseline because cache misses flip the outcome. Ground-truth labels derived from the replay mechanism itself introduce circularity on these two variants.
- **Supporting Tests**:
  - `tests/test_replay_engine.py::test_fuzzy_matching_threshold_and_sensitivity`
  - `tests/test_replay_engine.py::test_majority_consistency_rule_for_regressions`
  - `tests/test_fidelity.py::test_composite_fidelity_score`
- **Supporting Files & Benchmark Records**:
  - `eval_results/replay_regression_results.csv` (all 50 variant rows across DEV and TEST recording `y_by_construction`, `y_replay_derived`, composite fidelity, baseline matches, and false alarm rows `test_ben_04` and `test_ben_11`)
  - `eval_results/evaluation_report.md`
  - `evaluation/agents/sql_agent.py`
  - *Evidence Note*: The supporting tests assert unit-level replay matching and scoring mechanics; the empirical 50-variant suite counts and dual-label metrics come from `eval_results/replay_regression_results.csv` generated by `scripts/evaluate.py`.

---

## Claim 11: Commutative Reordering Scope & Implementation
**Statement**: The four empirical commutative swap variants exchange adjacent calls of the same tool type, yielding $S_{\text{tool}} = 1.0000$ by construction and leaving the tool reordering penalty unexercised. Argument matching is implemented via order-independent set pairing. The penalty on short-trace different-tool swaps is an analytical property of the Levenshtein composite metric, not an empirical suite finding.
- **Supporting Tests**:
  - `tests/test_replay_threshold_boundary.py::test_commutative_swap_trace_length_and_threshold_boundary`
  - `tests/test_fidelity.py::test_s_tool_similarity_definition`
- **Supporting Files**:
  - `eval_results/evaluation_report.md`
  - `server/app/services/fidelity.py`

---

## Claim 12: SQL Multi-Statement AST Scoping & Fail-Closed Enforcement
**Statement**: SQL safety checks enforce fail-closed per-statement AST verification via sqlglot rather than outright multi-statement rejection, supporting valid batched analytics while ensuring that every statement in a multi-statement payload independently satisfies operation allowlists and WHERE clause mandates. Following a post-freeze audit, AST walks were explicitly scoped per statement (`stmt.walk()`), ensuring trailing benign statements cannot mask leading unconstrained DELETE/UPDATE operations.
- **Supporting Tests**:
  - `tests/test_security_checks.py::test_sql_multi_statement_where_clause_scoping`
  - `tests/test_security_checks.py::test_sql_multi_statement_injection`
- **Supporting Files**:
  - `server/app/services/security_checks.py`
  - `eval_results/evaluation_report.md`

