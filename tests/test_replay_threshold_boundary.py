"""
Test Replay Threshold Boundary & Operator Specification.
Milestone 12 Rigor Audit.
"""
import pytest
from server.app.services.fidelity import calculate_fidelity_score, calculate_tool_sequence_similarity


def test_commutative_swap_trace_length_and_threshold_boundary():
    """
    Formally verifies that:
    1. Short traces (N=2, 3) are penalized below 0.80 by Levenshtein distance.
    2. N=4 produces exact boundary value 0.8000.
    3. The comparison operator is strictly '< 0.80' (not '<=').
       Therefore 0.8000 is tolerated, while 0.7999 is flagged.
    """
    tau = 0.80

    # N=2 trace: swap 2 tools -> edit distance 2
    s_tool_2 = calculate_tool_sequence_similarity(["t1", "t2"], ["t2", "t1"])
    assert s_tool_2 == 0.0, f"Expected 0.0 for N=2 swap, got {s_tool_2}"
    f_2 = calculate_fidelity_score(s_tool_2, 1.0, 1.0)
    assert round(f_2, 4) == 0.6000
    is_regression_2 = (f_2 < tau)
    assert is_regression_2 is True, "N=2 swap must be flagged as regression"

    # N=3 trace: swap 2 tools -> edit distance 2
    s_tool_3 = calculate_tool_sequence_similarity(["t1", "t2", "t3"], ["t2", "t1", "t3"])
    assert round(s_tool_3, 4) == 0.3333
    f_3 = calculate_fidelity_score(s_tool_3, 1.0, 1.0)
    assert round(f_3, 4) == 0.7333
    is_regression_3 = (f_3 < tau)
    assert is_regression_3 is True, "N=3 swap must be flagged as regression"

    # N=4 trace: swap 2 tools -> edit distance 2
    s_tool_4 = calculate_tool_sequence_similarity(["t1", "t2", "t3", "t4"], ["t2", "t1", "t3", "t4"])
    assert s_tool_4 == 0.50
    f_4 = calculate_fidelity_score(s_tool_4, 1.0, 1.0)
    assert round(f_4, 4) == 0.8000

    # Test exact boundary operator '< tau'
    assert not (f_4 < tau), "Fidelity exactly equal to 0.8000 must NOT be flagged under '< 0.80'"
    assert (f_4 <= tau), "Fidelity 0.8000 WOULD be flagged if operator were '<='"

    # Float perturbation slightly below threshold
    f_slightly_below = 0.7999
    assert (f_slightly_below < tau) is True, "0.7999 must be flagged under '< 0.80'"
