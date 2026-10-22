"""
Test No Host Execution Invariant.
Milestone 12 Rigor Audit.

Asserts that NO evaluation path executes host shell commands (subprocess.run,
os.system, etc.) on scenario strings or LLM-originated tools. All file and shell
tasks must execute strictly through the simulated allowlisted interpreter.
"""
import pytest
import os
import subprocess
from unittest.mock import patch
from evaluation.scenarios.generator import generate_all_scenarios, generate_held_out_unsafe_scenarios
from evaluation.agents.file_shell_agent import FileShellAgent
from scripts.evaluate import ConditionExecutor


def test_no_host_execution_during_standard_and_held_out_scenarios():
    """
    Verifies that running File/Shell agent across benign, unsafe, and held-out
    scenarios NEVER invokes subprocess or os.system on host.
    """
    scenarios = generate_all_scenarios(seed=42)["file_shell"]
    held_out = [s for s in generate_held_out_unsafe_scenarios() if s.agent_type == "file_shell"]

    all_test_scenarios = scenarios + held_out

    # Mock all host execution primitives
    with patch("subprocess.run") as mock_sub_run, \
         patch("subprocess.Popen") as mock_sub_popen, \
         patch("subprocess.call") as mock_sub_call, \
         patch("os.system") as mock_os_system, \
         patch("os.popen") as mock_os_popen:

        for sc in all_test_scenarios:
            for cond in ["no_policy", "gateway", "naive_blocklist"]:
                res, post = ConditionExecutor.run_scenario(sc, cond, rng_seed=42)
                assert res is not None

        # Verify that NONE of the host shell primitives were ever called
        assert mock_sub_run.call_count == 0, f"Host subprocess.run was called {mock_sub_run.call_count} times!"
        assert mock_sub_popen.call_count == 0, f"Host subprocess.Popen was called {mock_sub_popen.call_count} times!"
        assert mock_sub_call.call_count == 0, f"Host subprocess.call was called {mock_sub_call.call_count} times!"
        assert mock_os_system.call_count == 0, f"Host os.system was called {mock_os_system.call_count} times!"
        assert mock_os_popen.call_count == 0, f"Host os.popen was called {mock_os_popen.call_count} times!"


def test_simulated_interpreter_rejects_unallowlisted_commands():
    """Verify that FileShellAgent strictly rejects non-allowlisted commands without host execution."""
    agent = FileShellAgent()
    try:
        # Non-allowlisted command
        with pytest.raises(PermissionError) as exc_info:
            agent.execute_sandboxed_command("env", ["|", "grep", "SECRET"])
        assert "Prohibited command" in str(exc_info.value)
        assert "env" in str(exc_info.value)

        with pytest.raises(PermissionError) as exc_info2:
            agent.execute_sandboxed_command("Execute", ["echo", "test"])
        assert "Prohibited command" in str(exc_info2.value)

        with pytest.raises(PermissionError) as exc_info3:
            agent.execute_sandboxed_command("type", ["credentials"])
        assert "Prohibited command" in str(exc_info3.value)
    finally:
        agent.cleanup()
