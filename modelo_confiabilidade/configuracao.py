"""Contrato de configuração, fontes e logging do pipeline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Sequence

INDICATOR_FILES: dict[str, str] = {
    "caminhao": "INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx",
    "carga": "INDICADORES MENSAIS POR UNIVERSO carga.xlsx",
    "perfuracao": "INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx",
    "infra": "INDICADORES MENSAIS POR UNIVERSO infra.xlsx",
}
"""The four indicator workbooks, keyed by their universe."""

OPERATIONAL_FILES: dict[str, str] = {
    "AMS_Contador": "AMS_Contador.csv",
    "AMS_Calendario": "AMS_Calendario.csv",
    "AMC_ITABIRA": "AMC_ITABIRA.csv",
    "APR_ITABIRA": "APR_ITABIRA.csv",
    "Backlog_mina_itabira": "Backlog_mina_itabira.csv",
}
"""The five operational CSV exports, keyed by source name."""

_INDICATOR_NUMERIC_COLUMNS = {
    "DFREAL",
    "MTBFREAL",
    "MTBSREAL",
    "MTTR",
    "NICVMINA",
}
_ESSENTIAL_INDICATOR_COLUMNS = {"ANOMES", "EQUIPAMENTO", *_INDICATOR_NUMERIC_COLUMNS}


class DataValidationError(Exception):
    """Raised when a required source cannot be loaded or is unavailable."""

    source: str = ""
    path: Path | str = ""
    correction: str = ""


@dataclass(frozen=True)
class Config:
    """Validated runtime configuration for the validation pipeline."""

    input_dir: Path = Path("./bases")
    output_dir: Path = Path("./resultados")
    test_months: int = 3
    max_lag: int = 6
    random_state: int = 42
    group_map_file: Path | None = None
    min_train_rows: int = 30
    min_test_rows: int = 10
    min_feature_non_null: float = 0.5
    min_test_r2: float = 0.0
    max_test_mape: float = 100.0
    min_baseline_improvement: float = 0.0
    max_metric_cv: float = 1.0
    max_vif: float = 10.0


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for an argparse option."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deve ser um inteiro positivo") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("deve ser um inteiro positivo")
    return parsed


def _non_negative_float(value: str) -> float:
    """Parse a non-negative floating-point threshold."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deve ser um numero nao negativo") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("deve ser um numero nao negativo")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> Config:
    """Parse command-line arguments and return an immutable configuration."""
    parser = argparse.ArgumentParser(description="Pipeline de validacao preditiva dos indicadores de confiabilidade.")
    parser.add_argument("--input-dir", type=Path, default=Path("./bases"))
    parser.add_argument("--output-dir", type=Path, default=Path("./resultados"))
    parser.add_argument("--test-months", type=_positive_int, default=3)
    parser.add_argument("--max-lag", type=_positive_int, default=6)
    parser.add_argument("--random-state", type=_positive_int, default=42)
    parser.add_argument("--group-map-file", type=Path, default=None)
    parser.add_argument("--min-train-rows", type=_positive_int, default=30)
    parser.add_argument("--min-test-rows", type=_positive_int, default=10)
    parser.add_argument("--min-feature-non-null", type=_non_negative_float, default=0.5)
    parser.add_argument("--min-test-r2", type=float, default=0.0)
    parser.add_argument("--max-test-mape", type=_non_negative_float, default=100.0)
    parser.add_argument("--min-baseline-improvement", type=float, default=0.0)
    parser.add_argument("--max-metric-cv", type=_non_negative_float, default=1.0)
    parser.add_argument("--max-vif", type=_non_negative_float, default=10.0)
    args = parser.parse_args(argv)
    return Config(**vars(args))


def configure_logging(output_dir: Path) -> logging.Logger:
    """Configure console and file logging for one CLI execution."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("validar_modelo")
    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(output_dir / "validar_modelo.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger


_configure_logging = configure_logging


def __getattr__(name: str) -> Any:
    """Provide lazy access for backward-compatible loader imports without circular dependencies."""
    if name in ("load_indicator_files", "load_operational_files"):
        from .dados import load_indicator_files, load_operational_files

        if name == "load_indicator_files":
            return load_indicator_files
        return load_operational_files
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Config",
    "DataValidationError",
    "INDICATOR_FILES",
    "OPERATIONAL_FILES",
    "_ESSENTIAL_INDICATOR_COLUMNS",
    "_INDICATOR_NUMERIC_COLUMNS",
    "_configure_logging",
    "configure_logging",
    "parse_args",
]
