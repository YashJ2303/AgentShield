# Milestone 11: Demo Agents & Real Model Evaluation Guide

## 1. Overview
Milestone 11 establishes a grounded evaluation harness featuring 5 specialized demo agents, a seeded scenario generator (225 tasks total), independent code-based task checkers and safety predicates, and a pluggable LLM interface.

---

## 2. Pluggable LLM Interface

The LLM interface ([`evaluation/llm_provider.py`](file:///d:/E/AgentShield/evaluation/llm_provider.py)) supports two modes:
1. **MockLLMProvider**: Fast, deterministic, zero-cost provider for automated tests and unit checks.
2. **RealLLMProvider**: Live API provider targeting OpenAI, Ollama (local open-weights models), Groq, DeepSeek, or any OpenAI-compatible API.

### Configuring a Real Model for Evaluation

To run evaluations against a real model, configure the environment variables in your local `.env` file (which is git-ignored and never committed):

```bash
# Provider selector: 'mock' (default) or 'real'
EVAL_LLM_PROVIDER=real

# API Key (NEVER commit this key to version control)
EVAL_LLM_API_KEY=sk-proj-...

# Base URL (default is https://api.openai.com/v1)
EVAL_LLM_BASE_URL=https://api.openai.com/v1

# Target Model (e.g. gpt-4o-mini, gpt-4o, claude-3-5-sonnet via proxy, or llama3)
EVAL_LLM_MODEL=gpt-4o-mini
```

### Running with Local Models via Ollama (Zero Cost, No API Key Required)
You can run local open-weights models (e.g. LLaMA 3, Mistral, Qwen) via Ollama:
```bash
# 1. Start Ollama locally
ollama run llama3.2

# 2. Configure .env
EVAL_LLM_PROVIDER=real
EVAL_LLM_BASE_URL=http://localhost:11434/v1
EVAL_LLM_MODEL=llama3.2
EVAL_LLM_API_KEY=ollama
```

### Prompt-Only Guardrail Baseline Note
As detailed in the Milestone 11 design requirements:
- A scripted mock LLM ignores prompt guardrails unless explicitly scripted to simulate refusal.
- Running the three-condition comparison (No Policy vs Prompt-Only Guardrail vs AgentShield Gateway) with a real model provides meaningful empirical measurements of how soft system prompts degrade under adversarial pressure compared to deterministic gateway enforcement.

---

## 3. Demo Agents Architecture

| Agent | Module | Primary Tools | Critical Safety Sandbox Design |
| :--- | :--- | :--- | :--- |
| **SQL Agent** | [`SqlAgent`](file:///d:/E/AgentShield/evaluation/agents/sql_agent.py) | `execute_sql` | Uses a fresh throwaway SQLite copy (`tempfile.NamedTemporaryFile`) per run. Destructive queries in Condition 1 cannot corrupt subsequent runs. |
| **Web / API Agent** | [`WebAgent`](file:///d:/E/AgentShield/evaluation/agents/web_agent.py) | `fetch_url`, `api_request` | Interacts with local mock server (`MockWebServer`). Tests domain whitelisting and indirect prompt injections in retrieved HTML/JSON. |
| **Looping Agent** | [`LoopingAgent`](file:///d:/E/AgentShield/evaluation/agents/looping_agent.py) | `poll_status` | Tests runaway loops and loop-breaker budget enforcement when monitoring stuck asynchronous tasks. |
| **Stochastic Agent** | [`StochasticDemoAgent`](file:///d:/E/AgentShield/evaluation/agents/stochastic_agent.py) | Configurable | Parameterized simulation (paraphrase rate, tool-swap rate, recovery rate) labeled `[SIMULATION]` in all outputs. |
| **File / Shell Agent** | [`FileShellAgent`](file:///d:/E/AgentShield/evaluation/agents/file_shell_agent.py) | `read_file`, `write_file`, `run_safe_command` | **Strict Sandbox**: Operates inside `tempfile.TemporaryDirectory()`. Never executes arbitrary LLM shell commands; allowlists only `{cat, ls, grep, wc, echo, head}`. |
| **LangChain Adapter** | [`AgentShieldLangChainAdapter`](file:///d:/E/AgentShield/evaluation/agents/langchain_adapter.py) | Optional | Standard adapter enabling agents and policy checks to integrate into LangGraph workflows. |

---

## 4. Scenario Benchmark & Gold Labels

The scenario generator ([`evaluation/scenarios/generator.py`](file:///d:/E/AgentShield/evaluation/scenarios/generator.py)) is seeded (`seed=42`) and produces **225 total scenarios** (45 per agent: 30 benign + 15 unsafe).

Every task is paired with two independent code-based checkers ([`evaluation/scenarios/gold_checkers.py`](file:///d:/E/AgentShield/evaluation/scenarios/gold_checkers.py)):
1. **Task Checker (`evaluate_task_checker`)**: Confirms task completion, final answer, or expected refusal state.
2. **Safety Predicate (`check_*`)**: Invariant check executed directly against environment post-state (e.g. confirming database tables remain intact, no files outside the sandbox were touched, no disallowed domains were contacted).
