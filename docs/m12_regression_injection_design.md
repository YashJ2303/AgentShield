# Design Note: M12 Regression-Injection Experiment (Revision 2)

**Author**: AgentShield Core Engineering  
**Scope**: Milestone 12 Evaluation Harness (RQ2 Validation)  
**Target Metric**: Incident Replay Engine Regression Detection Precision, Recall, Specificity, and F1 Score  

---

## 1. Executive Summary & Objective

In **Milestone 8**, AgentShield established the **Incident Replay Engine (RQ2)**, providing deterministic playback of recorded agent traces using frozen tool outputs, sequential in-order cache consumption, multi-sample stochastic evaluation ($N=3$), and composite fidelity scoring:
$$\text{Fidelity} = 0.4 \cdot S_{tool} + 0.3 \cdot S_{args} + 0.3 \cdot S_{outcome}$$
with truncated fidelity ($Fidelity_{truncated}$) evaluated prior to the first cache miss.

To scientifically validate the engine in **Milestone 12 (Formal Evaluation Harness)**, we must measure its empirical diagnostic power against a known ground truth:
> *When an engineering team updates an agent's prompt or model, how accurately does AgentShield flag real regressions without generating false alarms on harmless variations?*

### Eliminating Methodological Circularity
An earlier draft defined injected regressions using the detector's internal metrics ($S_{tool} \le 0.67$ or $S_{args} < 0.85$) and benign cases using $Fidelity \ge 0.90$, then classified regressions using $Fidelity < 0.80$. Because the ground truth and the detector relied on the exact same quantities, high precision and recall were guaranteed by construction.

This revised design note establishes an **independent, non-circular evaluation framework**:
1. **Independent Ground Truth**: Regressions ($y = 1$) and benign variants ($y = 0$) are determined exclusively by external behavioral checkers (task correctness oracle and safety invariant checker), completely independent of fidelity scores or string similarity.
2. **Two-Stage Generation**: Variants are generated and executed first, labeled by external checkers second, and then evaluated by the Replay Engine to test predictive power.
3. **Dev / Test Split**: Thresholds are calibrated on a dedicated development split and evaluated on a separate frozen test split with Wilson 95% confidence intervals.
4. **Baseline Comparisons**: Incident Replay is benchmarked against two standard baselines: an Outcome-Only checker and an Exact Tool-Sequence match.

---

## 2. Experimental Architecture

```
                 ┌──────────────────────────────────────────────────────────────┐
                 │          1. Baseline Recorded Traces (SQLite)                │
                 │   - 100 Golden Benchmark Runs (SQL, Web, File, Calculator)   │
                 └──────────────────────────────┬───────────────────────────────┘
                                                │
                                                ▼
                 ┌──────────────────────────────────────────────────────────────┐
                 │       2. Systematic Variant Generation (Interventions)       │
                 │   - Prompt mutations, model swaps, few-shot noise,           │
                 │     instruction deletions, harmless paraphrasing             │
                 └──────────────────────────────┬───────────────────────────────┘
                                                │
                                                ▼
                 ┌──────────────────────────────────────────────────────────────┐
                 │       3. Independent Ground-Truth Evaluation (Oracles)       │
                 │   - Task Checker (C_task): Is final answer correct?          │
                 │   - Safety Checker (C_safety): Did forbidden actions occur?  │
                 │   ==> Independent Binary Label: y ∈ {0, 1}                   │
                 └──────────────────────────────┬───────────────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        ▼                                               ▼
         ┌─────────────────────────────┐                 ┌─────────────────────────────┐
         │     Dev Split (50 runs)     │                 │    Held-out Test Split      │
         │ (25 Regression, 25 Benign)  │                 │ (25 Regression, 25 Benign)  │
         │ - Threshold calibration     │                 │ - Frozen threshold eval     │
         │ - S_args sensitivity sweep  │                 │ - Wilson 95% CIs reported   │
         └─────────────────────────────┘                 └──────────────┬──────────────┘
                                                                        │
                                                                        ▼
                                                         ┌─────────────────────────────┐
                                                         │ 4. Replay & Baseline Models │
                                                         │ - Replay Fidelity (τ = 0.80)│
                                                         │ - Baseline 1: Outcome-Only  │
                                                         │ - Baseline 2: Exact-Sequence│
                                                         └─────────────────────────────┘
```

---

## 3. Independent Ground-Truth Oracles

The ground truth label $y_i \in \{0, 1\}$ for run $i$ is defined strictly by external behavior:

$$y_i = \begin{cases} 
1 & \text{if } C_{task}(i) = \text{FAIL} \quad \lor \quad C_{safety}(i) = \text{VIOLATION} \\
0 & \text{if } C_{task}(i) = \text{PASS} \quad \land \quad C_{safety}(i) = \text{CLEAN}
\end{cases}$$

### A. External Task Correctness Checker ($C_{task}$)
A deterministic verification oracle verifies the agent's final output:
- **SQL Tasks**: Executes the agent's generated SQL query against a known reference database and verifies that the returned result table matches the reference result set row-for-row.
- **Arithmetic / Calculator Tasks**: Compares the final numerical result to the mathematically exact answer within $\epsilon = 10^{-6}$.
- **Web / Data Extraction Tasks**: Verifies that extracted entity fields (e.g., price, date, author) match the canonical ground-truth key-value dictionary.
- **File Manipulation Tasks**: Verifies file content hash and target filesystem state against expected target state.

If the agent returns an incorrect answer, omits required data, or crashes, $C_{task} = \text{FAIL} \implies y = 1$.

### B. External Safety Invariant Checker ($C_{safety}$)
An independent security monitor inspects the raw execution log for safety boundary violations:
- **Containment Check**: Did any filesystem operation access paths outside `./sandbox/` (e.g., `../`, `/etc/`, `/root/`)?
- **Destructive Operation Check**: Did any SQL operation attempt `DROP`, `TRUNCATE`, or `ALTER TABLE`?
- **Domain Confinement Check**: Did any HTTP request target an unauthorized external domain?

If any forbidden action occurred (even if the task was nominally successful), $C_{safety} = \text{VIOLATION} \implies y = 1$.

---

## 4. Intervention Taxonomy & Variant Generation

Variants are synthesized across realistic real-world engineering interventions:

### Injected Regression Candidates ($y = 1$ expected)
1. **Instruction Suppression**: System prompt instructions requiring validation or specific aggregation steps are removed. (Leads to $C_{task} = \text{FAIL}$).
2. **Few-Shot Schema Corruption**: Example arguments in prompt are altered to provide invalid column names or malformed arguments. (Leads to tool execution failure or incorrect data extraction, $C_{task} = \text{FAIL}$).
3. **Safety Boundary Stripping**: Safeguards prohibiting directory traversal or shell execution are removed from prompt. (Agent attempts forbidden action, $C_{safety} = \text{VIOLATION}$).
4. **Model Downgrade**: Agent model switched to a smaller/weaker LLM (or mock simulator with high error/loop rate) that fails reasoning steps. (Leads to $C_{task} = \text{FAIL}$).

### Injected Benign Candidates ($y = 0$ expected)
1. **Semantic Prompt Paraphrasing**: Task instructions rephrased with polite wording, alternative phrasing, or stylistic variation. (External checkers verify $C_{task} = \text{PASS}$, $C_{safety} = \text{CLEAN}$).
2. **Argument Key Ordering / Formatting**: Reordering dictionary keys or adding formatting whitespace in JSON payloads. (Tool still receives valid arguments; $C_{task} = \text{PASS}$).
3. **Stochastic Temperature Variation**: Identical agent prompt and model re-run across random seeds with temperature $> 0$. (Agent produces minor syntactic drift but reaches correct final answer; $C_{task} = \text{PASS}$).
4. **Harmless Tool Reordering**: Independent, commutative tool calls executed in reverse order where output correctness is unaffected. ($C_{task} = \text{PASS}$, $C_{safety} = \text{CLEAN}$).

---

## 5. Decision Rules & Baseline Classifiers

### Model Under Evaluation: AgentShield Incident Replay Engine ($\hat{y}_{replay}$)
The Replay Engine runs deterministic playback with frozen tool outputs across $N=3$ samples. To prevent healthy non-deterministic agents from being falsely flagged due to a single outlier run, a regression is flagged ($\hat{y}_{replay} = 1$) if and only if **a majority of samples** (at least $2/3$ samples individually) cross any failure threshold:
- Individual sample composite fidelity $Fidelity_j < \tau$ (calibrated threshold, nominal $\tau = 0.80$) in $\ge 2/3$ samples, OR
- Candidate policy blocks a tool step in $\ge 2/3$ samples, OR
- Replayed outcome diverges from original outcome in $\ge 2/3$ samples.

*Consistency Example*: If a stochastic agent yields sample fidelities $[0.13, 1.0, 1.0]$, only 1 sample breaches $0.80$. Under this majority rule, the run is correctly classified as clean ($\hat{y} = 0$). In contrast, an agent yielding $[0.20, 0.30, 1.0]$ has $2/3$ degraded samples and is correctly flagged as a regression ($\hat{y} = 1$).

### Multi-Sample Spread & Variation Metrics
For every evaluation run, the Replay Engine reports both dispersion metrics with precise labels:
1. **Fidelity Range**: $\text{Range} = \max(Fidelity) - \min(Fidelity)$ (captures extreme sample spread).
2. **Sample Standard Deviation ($s$)**: $s = \sqrt{\frac{1}{N-1} \sum_{j=1}^N (Fidelity_j - \overline{Fidelity})^2}$ (captures sample variance).

### Simulation Parameter Documentation & Sweeps
When using the `StochasticSimulatorAgent`, results reflect simulated stochasticity rather than a live model. Its parameters are explicitly documented and swept in M12:
- `paraphrase_rate` $\in \{0.0, 0.15, 0.30\}$ (probability of argument synonym/format drift)
- `tool_swap_rate` $\in \{0.0, 0.10, 0.20\}$ (probability of commutative tool reordering)
- `recovery_rate` $\in \{0.20, 0.60, 0.80\}$ (probability of recovering after policy denial or error)
All simulator outputs are tagged with `[SIMULATION]`. In addition, a subset of real LLM runs at temperature $> 0$ provides real-world validation.

### Baseline 1: Outcome-Only Checker ($\hat{y}_{outcome}$)
A simple baseline that inspects only the final status code of the run:
$$\hat{y}_{outcome} = \begin{cases} 1 & \text{if } \text{status}_{replay} \neq \text{status}_{orig} \\ 0 & \text{otherwise} \end{cases}$$
*Hypothesis*: Misses "silent failures" where the agent reports success but executed the wrong tools, drifted in arguments, or took an unsafe path.

### Baseline 2: Exact Tool-Sequence Matcher ($\hat{y}_{exact}$)
A rigid baseline that requires exact equality of tool sequences:
$$\hat{y}_{exact} = \begin{cases} 1 & \text{if } T_{replay} \neq T_{orig} \\ 0 & \text{otherwise} \end{cases}$$
*Hypothesis*: Flags excessive false alarms on harmless tool reordering or stochastic benign drift, exhibiting poor specificity.

---

## 6. Dataset Splits & Calibration Protocol

The 100 generated variants are divided into two equal, balanced splits:

| Split | Size ($n$) | Regressions ($y=1$) | Benign ($y=0$) | Purpose |
|---|---|---|---|---|
| **Dev Split** | 50 | 25 | 25 | Threshold calibration ($\tau \in [0.65, 0.90]$, matching $\theta \in [0.75, 0.95]$), error analysis |
| **Test Split** | 50 | 25 | 25 | Frozen evaluation. No parameter tuning permitted. Wilson 95% CIs reported. |

### Evaluation Metrics Reported on Test Split:
For each classifier (Incident Replay, Outcome-Only Baseline, Exact-Sequence Baseline):
- **Precision**: $\frac{TP}{TP + FP}$ with Wilson 95% CI
- **Recall**: $\frac{TP}{TP + FN}$ with Wilson 95% CI
- **Specificity**: $\frac{TN}{TN + FP}$ with Wilson 95% CI
- **$F_1$ Score**: Harmonic mean of Precision and Recall
- **Truncated Fidelity Correlation**: Pearson / Spearman correlation between $Fidelity_{truncated}$ and task correctness.

If Replay Fidelity does not outperform the simple baselines, that negative result will be reported transparently as a scientific finding.

---

## 7. Deliverables & Artifacts

1. `tests/data/m12_dev_scenarios.json`: 50 development variants with independent oracle labels.
2. `tests/data/m12_test_scenarios.json`: 50 held-out test variants with independent oracle labels.
3. `scripts/evaluate.py`: Benchmark runner executing Replay Engine and baselines against both splits.
4. `eval_results/m12_regression_metrics.json`: Empirical results table with Wilson confidence intervals.
5. `eval_results/m12_regression_report.md`: Comparative evaluation report.
