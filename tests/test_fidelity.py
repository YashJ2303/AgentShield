import pytest
from server.app.services.fidelity import (
    levenshtein_distance,
    calculate_tool_sequence_similarity,
    calculate_fidelity_score,
)


def test_s_tool_similarity_definition():
    # 1. Identical sequences -> distance 0 -> similarity 1.0
    seq1 = ["fetch_url", "parse_html", "sql_query"]
    assert levenshtein_distance(seq1, seq1) == 0
    assert calculate_tool_sequence_similarity(seq1, seq1) == 1.0

    # 2. Both empty -> similarity 1.0
    assert calculate_tool_sequence_similarity([], []) == 1.0

    # 3. Completely disjoint sequences of length 3 -> distance 3 -> similarity 0.0
    seq_a = ["tool_a", "tool_b", "tool_c"]
    seq_b = ["tool_x", "tool_y", "tool_z"]
    assert levenshtein_distance(seq_a, seq_b) == 3
    assert calculate_tool_sequence_similarity(seq_a, seq_b) == 0.0

    # 4. Partial similarity: 1 substitution out of 3 -> distance 1 -> similarity 1 - 1/3 = 0.6667
    seq_c = ["fetch_url", "parse_html", "sql_query"]
    seq_d = ["fetch_url", "parse_json", "sql_query"]
    assert levenshtein_distance(seq_c, seq_d) == 1
    sim = calculate_tool_sequence_similarity(seq_c, seq_d)
    assert pytest.approx(sim, 0.001) == 2.0 / 3.0

    # 5. Higher means more similar property:
    # seq_d (1 edit) must have higher similarity than seq_e (2 edits)
    seq_e = ["fetch_url", "parse_json", "write_file"]
    sim_d = calculate_tool_sequence_similarity(seq_c, seq_d)
    sim_e = calculate_tool_sequence_similarity(seq_c, seq_e)
    assert sim_d > sim_e, "Expected fewer edits to yield higher S_tool similarity"


def test_composite_fidelity_score():
    # Perfect match: S_tool=1.0, S_args=1.0, S_outcome=1.0 -> 1.0
    assert calculate_fidelity_score(1.0, 1.0, 1.0) == 1.0

    # Half tool similarity (0.5), perfect args (1.0), perfect outcome (1.0):
    # 0.4 * 0.5 + 0.3 * 1.0 + 0.3 * 1.0 = 0.2 + 0.3 + 0.3 = 0.8
    assert calculate_fidelity_score(0.5, 1.0, 1.0) == 0.8

    # All zero -> 0.0
    assert calculate_fidelity_score(0.0, 0.0, 0.0) == 0.0
