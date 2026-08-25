"""Diagnósticos estatísticos, explicações e classificação."""

from ._pipeline import (
    DIAGNOSTIC_COLUMNS,
    EXPLANATION_COLUMNS,
    classify_validity,
    extract_model_explanations,
    run_statistical_diagnostics,
)

__all__ = [
    "DIAGNOSTIC_COLUMNS", "EXPLANATION_COLUMNS", "classify_validity",
    "extract_model_explanations", "run_statistical_diagnostics",
]
