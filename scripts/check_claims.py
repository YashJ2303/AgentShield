"""Claim and Evidence Verification Script.

Ensures that every empirical and architectural claim in CLAIMS.md is backed by:
1. An existing test name present in `pytest --collect-only -q`.
2. An existing file in the repository.
3. An existing CSV row in `eval_results/held_out_unsafe_results.csv` (for held-out scenario IDs).

Exits with code 1 if any referenced evidence cannot be validated.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from pathlib import Path


def get_collected_tests(root_dir: Path) -> set[str]:
    """Run `pytest --collect-only -q` and return set of collected test identifiers."""
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=root_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        # If pytest failed, print stderr and raise
        print(f"Error running pytest --collect-only:\n{proc.stderr}", file=sys.stderr)
        sys.exit(1)

    collected: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" in line and (line.startswith("tests/") or line.startswith("tests\\")):
            # Normalize backslashes to forward slashes
            normalized = line.replace("\\", "/")
            collected.add(normalized)
    return collected


def parse_claims(claims_path: Path) -> tuple[set[str], set[str], set[str], set[str]]:
    """Parse CLAIMS.md and extract test names, file paths, CSV row scenario IDs, and replay variant IDs."""
    content = claims_path.read_text(encoding="utf-8")

    # 1. Test names: e.g. `tests/test_something.py::test_func_name`
    test_pattern = re.compile(r"`(tests/[a-zA-Z0-9_]+\.py::[a-zA-Z0-9_]+)`")
    tests = set(test_pattern.findall(content))

    # 2. Files: Look for paths starting with known top-level dirs
    file_pattern = re.compile(
        r"`((?:eval_results|evaluation|server|tests|scripts|sdk)/[a-zA-Z0-9_\-\./]+)`"
    )
    raw_files = file_pattern.findall(content)
    files: set[str] = set()
    for f in raw_files:
        # Strip trailing punctuation if any
        clean_f = f.split("::")[0].strip()
        if not clean_f.endswith((".py", ".md", ".csv", ".yaml", ".yml", ".json")):
            continue
        files.add(clean_f)

    # 3. CSV Scenario IDs: e.g. `heldout_01`, `heldout_20`
    scenario_pattern = re.compile(r"`(heldout_\d+)`")
    scenarios = set(scenario_pattern.findall(content))

    # 4. Replay Variant IDs: e.g. `test_ben_04`, `test_ben_11`
    variant_pattern = re.compile(r"`((?:test|dev)_(?:ben|reg)_\d+)`")
    variants = set(variant_pattern.findall(content))

    return tests, files, scenarios, variants


def check_claims(root_dir: Path | None = None) -> bool:
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent

    claims_file = root_dir / "CLAIMS.md"
    if not claims_file.exists():
        print(f"[FAIL] CLAIMS.md not found at {claims_file}", file=sys.stderr)
        return False

    print(f"Checking claims and evidence in {claims_file}...")
    tests, files, scenarios, variants = parse_claims(claims_file)

    collected_tests = get_collected_tests(root_dir)
    errors: list[str] = []

    # 1. Verify tests
    print(f"Verifying {len(tests)} test references against {len(collected_tests)} collected tests...")
    for test in sorted(tests):
        if test not in collected_tests:
            errors.append(f"Missing test: '{test}' not found in pytest --collect-only")

    # 2. Verify files
    print(f"Verifying {len(files)} file references on disk...")
    for f in sorted(files):
        p = root_dir / f
        if not p.exists():
            errors.append(f"Missing file: '{f}' does not exist on disk")

    # 3. Verify CSV scenarios in held_out_unsafe_results.csv
    csv_file = root_dir / "eval_results" / "held_out_unsafe_results.csv"
    if not csv_file.exists():
        errors.append(f"Missing CSV file: {csv_file}")
    else:
        print(f"Verifying {len(scenarios)} CSV scenario references in {csv_file.name}...")
        with open(csv_file, mode="r", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            available_scenarios = {row["scenario_id"] for row in reader if "scenario_id" in row}
        for sc in sorted(scenarios):
            if sc not in available_scenarios:
                errors.append(f"Missing CSV scenario ID: '{sc}' not found in {csv_file.name}")

    # 4. Verify replay variants in replay_regression_results.csv
    replay_csv = root_dir / "eval_results" / "replay_regression_results.csv"
    if not replay_csv.exists():
        errors.append(f"Missing Replay CSV file: {replay_csv}")
    else:
        print(f"Verifying {len(variants)} replay variant references in {replay_csv.name}...")
        with open(replay_csv, mode="r", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            available_variants = {row["variant_id"] for row in reader if "variant_id" in row}
        for v in sorted(variants):
            if v not in available_variants:
                errors.append(f"Missing Replay Variant ID: '{v}' not found in {replay_csv.name}")

    # 5. Verify latency benchmark records in latency_benchmark.csv
    latency_csv = root_dir / "eval_results" / "latency_benchmark.csv"
    if not latency_csv.exists():
        errors.append(f"Missing Latency CSV file: {latency_csv}")
    else:
        print(f"Verifying latency benchmark runs in {latency_csv.name}...")
        with open(latency_csv, mode="r", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            run_indices = {row["run_index"] for row in reader if "run_index" in row}
        expected_indices = {"1", "2", "3", "4", "5", "summary_median"}
        missing_runs = expected_indices - run_indices
        if missing_runs:
            errors.append(f"Missing latency run indices {missing_runs} in {latency_csv.name}")

    if errors:
        print(f"\n[FAIL] {len(errors)} evidence errors detected in CLAIMS.md:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return False

    print(
        f"\n[PASS] All {len(tests)} tests, {len(files)} files, {len(scenarios)} held-out rows, "
        f"{len(variants)} replay rows, and latency benchmarks verified successfully!"
    )
    return True


if __name__ == "__main__":
    success = check_claims()
    sys.exit(0 if success else 1)
