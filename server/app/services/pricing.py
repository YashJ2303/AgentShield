import json
import os
from typing import Optional

from server.app.config import settings

# Price per 1,000,000 tokens (USD).
#
# PRICING_AS_OF records when this table was last verified against provider list prices.
# Provider list prices change without notice; treat this table as a snapshot, not a
# guarantee. Override it without editing code by pointing PRICING_CONFIG_PATH at a JSON
# file of the same shape ({"<model substring>": {"input": <usd/1M>, "output": <usd/1M>}}).
PRICING_AS_OF = "2025-06"

DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "o4-mini": {"input": 1.10, "output": 4.40},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "mock-model": {"input": 0.00, "output": 0.00},
}

# Lazily-loaded overrides from PRICING_CONFIG_PATH. None means "not loaded yet"; an empty
# dict means "loaded, no overrides present".
_pricing_overrides: Optional[dict[str, dict[str, float]]] = None


def _load_overrides() -> dict[str, dict[str, float]]:
    """Load optional pricing overrides from PRICING_CONFIG_PATH. Fail-soft: a malformed
    override file must never take down the gateway, so it degrades to built-in pricing."""
    global _pricing_overrides
    if _pricing_overrides is not None:
        return _pricing_overrides

    overrides: dict[str, dict[str, float]] = {}
    path = settings.PRICING_CONFIG_PATH
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                for model_key, entry in raw.items():
                    if isinstance(entry, dict) and "input" in entry and "output" in entry:
                        overrides[str(model_key)] = {
                            "input": float(entry["input"]),
                            "output": float(entry["output"]),
                        }
        except Exception:
            overrides = {}
    _pricing_overrides = overrides
    return overrides


def reset_pricing_cache() -> None:
    """Reset the cached override file so tests (or a live reload) re-read PRICING_CONFIG_PATH."""
    global _pricing_overrides
    _pricing_overrides = None


def effective_pricing_table() -> dict[str, dict[str, float]]:
    """Built-in pricing merged with file overrides (file wins)."""
    merged = dict(DEFAULT_PRICING)
    merged.update(_load_overrides())
    return merged


def _match_model_key(model: str, table: dict[str, dict[str, float]]) -> Optional[str]:
    """Find the pricing entry for a model name by substring, longest key first.

    Longest-first is required: model names nest (gpt-4o is a prefix of gpt-4o-mini,
    gemini-2.5-flash is a prefix of gemini-2.5-flash-lite). Matching in insertion order
    silently overcharged gpt-4o-mini at gpt-4o rates.
    """
    lowered = model.lower()
    for key in sorted(table, key=len, reverse=True):
        if key in lowered:
            return key
    return None


def calculate_cost(model: Optional[str], prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    """
    Calculate USD cost for model call based on token counts.
    If the model is unrecognized or absent from the pricing table,
    returns None (null), NEVER 0.0 or a silent fallback price,
    to prevent unknown models from falsely appearing free in comparisons.
    """
    if not model:
        return None

    table = effective_pricing_table()
    matched_key = _match_model_key(model, table)

    if not matched_key:
        return None

    pricing = table[matched_key]
    input_cost = (prompt_tokens / 1_000_000.0) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000.0) * pricing["output"]
    return round(input_cost + output_cost, 6)
