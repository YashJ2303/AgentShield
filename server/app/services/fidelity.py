"""
Fidelity score calculation for incident replay (M8) and trajectory comparison.
"""
from typing import Sequence


def levenshtein_distance(seq_a: Sequence[str], seq_b: Sequence[str]) -> int:
    """Compute standard Levenshtein edit distance between two sequences of tokens/strings."""
    n = len(seq_a)
    m = len(seq_b)
    if n == 0:
        return m
    if m == 0:
        return n

    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if seq_a[i - 1] == seq_b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,        # deletion
                dp[i][j - 1] + 1,        # insertion
                dp[i - 1][j - 1] + cost, # substitution
            )

    return dp[n][m]


def calculate_tool_sequence_similarity(seq_a: Sequence[str], seq_b: Sequence[str]) -> float:
    """
    Calculate S_tool: sequence similarity between recorded and replayed tool call sequences.
    Defined as: 1.0 - normalized Levenshtein distance, so higher means more similar.
    Returns 1.0 for identical sequences, 0.0 for completely disjoint sequences.
    """
    if not seq_a and not seq_b:
        return 1.0
    max_len = max(len(seq_a), len(seq_b))
    dist = levenshtein_distance(seq_a, seq_b)
    normalized_distance = dist / max_len
    return max(0.0, min(1.0, 1.0 - normalized_distance))


def calculate_arg_similarity(args_a: object, args_b: object) -> float:
    """
    Calculate S_args: similarity between two argument dictionaries in [0.0, 1.0].
    Uses normalized Levenshtein distance on canonical JSON strings.
    """
    import json
    if args_a == args_b:
        return 1.0
    if args_a is None or args_b is None:
        return 0.0

    try:
        str_a = json.dumps(args_a, sort_keys=True, ensure_ascii=False)
        str_b = json.dumps(args_b, sort_keys=True, ensure_ascii=False)
    except Exception:
        str_a = str(args_a)
        str_b = str(args_b)

    if not str_a and not str_b:
        return 1.0
    max_len = max(len(str_a), len(str_b))
    if max_len == 0:
        return 1.0

    dist = levenshtein_distance(str_a, str_b)
    return round(max(0.0, min(1.0, 1.0 - (dist / max_len))), 4)


def calculate_fidelity_score(
    s_tool: float,
    s_args: float,
    s_outcome: float,
    w_tool: float = 0.4,
    w_args: float = 0.3,
    w_outcome: float = 0.3,
) -> float:
    """
    Compute documented composite fidelity score:
    FidelityScore = 0.4 * S_tool + 0.3 * S_args + 0.3 * S_outcome
    where S_tool = 1 - normalized_levenshtein_distance.
    """
    score = (w_tool * s_tool) + (w_args * s_args) + (w_outcome * s_outcome)
    return round(max(0.0, min(1.0, score)), 4)

