import os
import csv
import re
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/eval-results", tags=["Evaluation Results"])

ROOT_DIR = Path(__file__).resolve().parents[4]
EVAL_RESULTS_DIR = ROOT_DIR / "eval_results"

# Fixed filename allowlist
ALLOWED_EVAL_FILES = {
    "held_out_unsafe_results.csv": EVAL_RESULTS_DIR / "held_out_unsafe_results.csv",
    "evaluation_results.csv": EVAL_RESULTS_DIR / "evaluation_results.csv",
    "evaluation_report.md": EVAL_RESULTS_DIR / "evaluation_report.md",
    "latency_benchmark.csv": EVAL_RESULTS_DIR / "latency_benchmark.csv",
    "replay_regression_results.csv": EVAL_RESULTS_DIR / "replay_regression_results.csv",
    "CLAIMS.md": ROOT_DIR / "CLAIMS.md",
    "KNOWN_LIMITATIONS.md": ROOT_DIR / "KNOWN_LIMITATIONS.md",
}


@router.get("/file")
def get_eval_file(
    filename: str = Query(..., description="Exact file name from the evaluation allowlist")
):
    """
    Read-only retrieval of approved evaluation and provenance documents.
    Enforces a strict allowlist and strictly prohibits path traversal.
    """
    # Strict path traversal checks
    if "/" in filename or "\\" in filename or ".." in filename or "%" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal detected: directory separators and dot-dot patterns are prohibited",
        )

    if filename not in ALLOWED_EVAL_FILES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{filename}' is not in the evaluation allowlist",
        )

    file_path = ALLOWED_EVAL_FILES[filename]
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation file '{filename}' is not present on disk",
        )

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "filename": filename,
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read evaluation file: {str(e)}",
        )


@router.get("/held-out")
def get_held_out_scenarios() -> list[dict[str, Any]]:
    """Parse and return structured rows from eval_results/held_out_unsafe_results.csv."""
    csv_path = ALLOWED_EVAL_FILES["held_out_unsafe_results.csv"]
    if not csv_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="held_out_unsafe_results.csv not found",
        )

    scenarios: list[dict[str, Any]] = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenarios.append(row)
    return scenarios


@router.get("/study-overview")
def get_study_overview() -> dict[str, Any]:
    """Parse and return structured summary from evaluation_report.md and evaluation_results.csv."""
    results_csv = ALLOWED_EVAL_FILES["evaluation_results.csv"]
    report_md = ALLOWED_EVAL_FILES["evaluation_report.md"]

    summary_rows: list[dict[str, Any]] = []
    if results_csv.exists():
        with open(results_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                summary_rows.append(row)

    report_text = ""
    if report_md.exists():
        report_text = report_md.read_text(encoding="utf-8")

    return {
        "benchmark_rows": summary_rows,
        "report_length": len(report_text),
        "available_files": list(ALLOWED_EVAL_FILES.keys()),
    }


@router.get("/replay-variants")
def get_replay_variants() -> list[dict[str, Any]]:
    """Parse and return structured 50-variant rows from eval_results/replay_regression_results.csv."""
    csv_path = ALLOWED_EVAL_FILES["replay_regression_results.csv"]
    if not csv_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="replay_regression_results.csv not found",
        )

    variants: list[dict[str, Any]] = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            variants.append(row)
    return variants

