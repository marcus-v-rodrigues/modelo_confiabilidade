"""Temporal reliability validation pipeline, from source loading to reporting.

Groups come from an explicit mapping file when supplied; otherwise they are
derived from the final two validated segments of each operational ``TPLNR``.
"""

from __future__ import annotations

import argparse
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.model_selection import GridSearchCV
from sklearn.inspection import permutation_importance
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import OLSInfluence, variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson
import statsmodels.api as sm
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


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

AUDIT_COLUMNS = ["fonte", "categoria", "campo", "valor", "severidade", "mensagem"]
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
    parser = argparse.ArgumentParser(description=__doc__)
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


def _read_required(
    input_dir: Path,
    files: dict[str, str],
    reader: str,
    **kwargs: object,
) -> dict[str, pd.DataFrame]:
    """Read a named collection and convert failures to actionable errors."""
    loaded: dict[str, pd.DataFrame] = {}
    for source, filename in files.items():
        path = input_dir / filename
        if not path.is_file():
            error = DataValidationError(
                f"Fonte obrigatoria ausente: {source} ({path}). "
                f"Correcao esperada: forneca o arquivo {filename} em {input_dir}."
            )
            error.source, error.path, error.correction = source, path, f"forneca o arquivo {filename} em {input_dir}"
            raise error
        try:
            if reader == "excel":
                loaded[source] = pd.read_excel(path, sheet_name="Export", **kwargs)
            else:
                loaded[source] = pd.read_csv(path, sep=";", encoding="utf-8-sig", **kwargs)
        except Exception as exc:
            detail = "aba Export" if reader == "excel" else "separador ';' e codificacao UTF-8-SIG"
            error = DataValidationError(
                f"Nao foi possivel ler {source} em {path}: {exc}. "
                f"Correcao esperada: valide o arquivo e sua {detail}."
            )
            error.source, error.path, error.correction = source, path, f"valide o arquivo e sua {detail}"
            raise error from exc
    return loaded


def load_indicator_files(input_dir: Path) -> dict[str, pd.DataFrame]:
    """Load the four indicator workbooks from ``input_dir``."""
    return _read_required(input_dir, INDICATOR_FILES, "excel")


def load_operational_files(input_dir: Path) -> dict[str, pd.DataFrame]:
    """Load the five operational CSV exports from ``input_dir``."""
    return _read_required(input_dir, OPERATIONAL_FILES, "csv")


def _comparison_text(value: object) -> str:
    """Return an accent-free, whitespace-normalized value for comparisons."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(text.upper().strip().split())


def _column_key(value: object) -> str:
    """Create an accent-insensitive key without changing the stored label."""
    return "".join(character for character in _comparison_text(value) if character.isalnum())


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim column labels while preserving their spelling and accents."""
    result = df.copy()
    result.columns = [
        " ".join(str(column).lstrip("\ufeff").strip().split())
        for column in result.columns
    ]
    return result


def parse_month_series(series: pd.Series, column_name: str) -> pd.Series:
    """Parse common YYYYMM and YYYY-MM values into monthly periods."""
    values = series.astype("string").str.strip()
    compact = values.str.replace(r"^(\d{4})[-/]?(\d{2})$", r"\1\2", regex=True)
    parsed = pd.to_datetime(compact, format="%Y%m", errors="coerce")
    if parsed.isna().any():
        fallback_values = values.where(values.str.match(r"^\d{4}-\d{2}$"))
        fallback = pd.to_datetime(fallback_values, format="%Y-%m", errors="coerce")
        parsed = parsed.fillna(fallback)
    return parsed.dt.to_period("M").rename(column_name)


def normalize_indicator_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Clean structural rows and safely coerce known indicator measures."""
    result = normalize_columns(df)
    if result.empty:
        return result

    text = result.astype("string").fillna("")
    empty_row = text.apply(lambda column: column.str.strip().eq("")).all(axis=1)
    marker_row = text.apply(
        lambda column: column.map(_comparison_text).str.contains(r"TOTAL|FILTRO|FILTER", regex=True)
    ).any(axis=1)
    structural = empty_row | marker_row
    result = result.loc[~structural].copy()

    columns_by_key = {_column_key(column): column for column in result.columns}
    equipment_column = columns_by_key.get("EQUIPAMENTO")
    month_column = columns_by_key.get("ANOMES")
    if equipment_column:
        equipment = result[equipment_column].astype("string").str.strip()
        result = result.loc[equipment.notna() & equipment.ne("")].copy()
    if month_column:
        result[month_column] = parse_month_series(result[month_column], month_column)
        result = result.loc[result[month_column].notna()].copy()

    coercion_events: list[dict[str, object]] = []
    for column in result.columns:
        key = _column_key(column)
        if key in {"ANOMES", "EQUIPAMENTO"}:
            continue
        numeric_values = pd.to_numeric(
            result[column].astype("string").str.replace(",", ".", regex=False), errors="coerce"
        )
        non_empty = result[column].notna() & result[column].astype("string").str.strip().ne("")
        clearly_numeric = non_empty.any() and numeric_values[non_empty].notna().mean() >= 0.95
        if key in _INDICATOR_NUMERIC_COLUMNS or clearly_numeric:
            invalid_values = result.loc[non_empty & numeric_values.isna(), column].tolist()
            if invalid_values:
                coercion_events.append({
                    "fonte": source,
                    "campo": column,
                    "contagem": len(invalid_values),
                    "amostra": [str(value) for value in invalid_values[:3]],
                })
            result[column] = pd.to_numeric(
                result[column].astype("string").str.replace(",", ".", regex=False),
                errors="coerce",
            )
    result = result.reset_index(drop=True)
    result.attrs["data_quality_events"] = coercion_events
    return result


def audit_data_quality(sources: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Report structural quality issues without requiring semantic mappings."""
    findings: list[dict[str, object]] = []
    periods: dict[str, set[pd.Period]] = {}

    def add(source: str, category: str, field: str, value: object, severity: str, message: str) -> None:
        findings.append({
            "fonte": source, "categoria": category, "campo": field,
            "valor": value, "severidade": severity, "mensagem": message,
        })

    required_sources = set(INDICATOR_FILES) | set(OPERATIONAL_FILES)
    for missing in sorted(required_sources - set(sources)):
        add(missing, "fonte", "", "ausente", "ERROR", "Fonte obrigatoria ausente")

    for source, frame in sources.items():
        if not isinstance(frame, pd.DataFrame):
            add(source, "fonte", "", "ausente/ilegiveis", "ERROR", "Fonte ausente ou ilegivel")
            continue
        data = normalize_columns(frame)
        add(source, "dimensao", "", f"{len(data)}x{len(data.columns)}", "INFO", "Dimensao observada")
        columns_by_key = {_column_key(column): column for column in data.columns}
        recorded_coercions = set()
        for event in frame.attrs.get("data_quality_events", []):
            recorded_coercions.add(event["campo"])
            add(source, "coercao", event["campo"], event["contagem"], "ERROR", f"Valores originais invalidos: {event['amostra']}")
        for column in data.columns:
            add(source, "dtype", column, str(data[column].dtype), "INFO", "Tipo estrutural observado")
            nulls = int(data[column].isna().sum())
            if nulls:
                add(source, "nulos", column, nulls, "WARNING", "Campo contem valores nulos")
            if data[column].nunique(dropna=True) <= 1 and len(data) > 1:
                add(source, "constante", column, data[column].dropna().iloc[0] if data[column].notna().any() else "", "INFO", "Campo constante")
            key = _column_key(column)
            numeric = pd.to_numeric(data[column].astype("string").str.replace(",", ".", regex=False), errors="coerce")
            non_empty = data[column].notna() & data[column].astype("string").str.strip().ne("")
            clearly_numeric = non_empty.any() and numeric[non_empty].notna().mean() >= 0.95
            if key in _INDICATOR_NUMERIC_COLUMNS or clearly_numeric:
                invalid_values = data.loc[non_empty & numeric.isna(), column].astype(str).tolist()
                if column not in recorded_coercions:
                    add(source, "coercao", column, len(invalid_values), "WARNING" if invalid_values else "INFO", f"Coercao numerica; amostra: {invalid_values[:3]}")
                if (numeric < 0).any():
                    add(source, "negativos", column, int((numeric < 0).sum()), "WARNING", "Valores negativos encontrados")
                if key.startswith(("DF", "UF", "RO")) and (numeric > 100).any():
                    add(source, "impossiveis", column, int((numeric > 100).sum()), "ERROR", "Percentual acima de 100")

        if source in INDICATOR_FILES:
            for essential in sorted(_ESSENTIAL_INDICATOR_COLUMNS - set(columns_by_key)):
                add(source, "resposta", essential, "ausente", "ERROR", "Campo essencial ausente")

        month_key = next(
            (key for key in ("ANOMES", "CALMONTH", "AMSMON", "DATA", "DATACRIACAO") if key in columns_by_key),
            None,
        )
        month_column = columns_by_key.get(month_key) if month_key else None
        if month_column:
            month = parse_month_series(data[month_column], month_column)
            invalid = int(month.isna().sum())
            if invalid:
                add(source, "periodo", month_column, invalid, "ERROR", "Periodos invalidos ou ausentes")
            periods[source] = set(month.dropna())
        else:
            add(source, "periodo", "", "ausente", "ERROR", "Nenhuma coluna temporal reconhecivel")
        key_columns = [columns_by_key[key] for key in ("ANOMES", "CALMONTH", "EQUIPAMENTO", "TPLNR") if key in columns_by_key]
        if len(key_columns) >= 2:
            duplicate_count = int(data.duplicated(key_columns, keep=False).sum())
            if duplicate_count:
                add(source, "duplicidade", ",".join(key_columns), duplicate_count, "WARNING", "Chaves estruturais duplicadas")
        for column in data.columns:
            cardinality = data[column].nunique(dropna=True)
            if len(data) and cardinality / len(data) > 0.95 and len(data) >= 10:
                add(source, "cardinalidade", column, cardinality, "INFO", "Cardinalidade elevada")

    if len(periods) > 1:
        common = set.intersection(*periods.values())
        if not common:
            add(";".join(periods), "intersecao_temporal", "", 0, "ERROR", "Fontes nao possuem periodo temporal comum")
        else:
            add(";".join(periods), "intersecao_temporal", "", len(common), "INFO", "Periodos comuns observados")
    return pd.DataFrame(findings, columns=AUDIT_COLUMNS)


FEATURE_METADATA_COLUMNS = [
    "feature", "fonte", "campo_original", "transformacao", "mes_referencia",
    "defasagem", "observacoes_validas", "risco_vazamento", "status_semantico",
]


def _mapping_key(frame: pd.DataFrame) -> str | None:
    keys = {_column_key(column): column for column in frame.columns}
    return keys.get("EQUIPAMENTO") or keys.get("TPLNR")


def _mapping_error(message: str) -> DataValidationError:
    error = DataValidationError(message)
    error.source = "mapeamento"
    error.correction = "forneca --group-map-file com uma chave EQUIPAMENTO ou TPLNR e GRUPO"
    return error


def _normalize_group_values(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize group labels and reject missing or whitespace-only groups."""
    result = frame.copy()
    if "GRUPO" not in result.columns:
        return result
    values = result["GRUPO"].astype("string")
    invalid = result["GRUPO"].isna() | values.str.strip().eq("")
    if invalid.any():
        sample = values[invalid].head(3).tolist()
        raise _mapping_error(f"GRUPO nulo ou vazio na fonte {source}: {int(invalid.sum())}; amostra: {sample}")
    result["GRUPO"] = values.str.strip()
    return result


def derive_tplnr_hierarchy(
    frame: pd.DataFrame,
    tplnr_column: str = "TPLNR",
) -> pd.DataFrame:
    """Derive the group and equipment from the final TPLNR segments."""
    if tplnr_column not in frame.columns:
        raise DataValidationError(f"Coluna TPLNR ausente: {tplnr_column}")

    values = frame[tplnr_column].astype("string").str.strip()
    invalid = values.isna() | values.eq("")
    parts = values.str.split("-")
    valid_parts = parts.map(
        lambda value: isinstance(value, list)
        and len(value) >= 2
        and all(str(part).strip() for part in value[-2:])
    )
    invalid |= ~valid_parts
    if invalid.any():
        sample = values[invalid].head(3).tolist()
        raise DataValidationError(
            f"TPLNR invalido na coluna {tplnr_column}: {int(invalid.sum())}; amostra: {sample}"
        )

    result = frame.copy()
    result["GRUPO"] = parts.map(lambda value: str(value[-2]).strip())
    result["EQUIPAMENTO"] = parts.map(lambda value: str(value[-1]).strip())
    return result


def build_hierarchy_group_mapping(
    indicators: pd.DataFrame,
    operational: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Derive operational groups from TPLNR and join them to indicators."""
    derived_operational: dict[str, pd.DataFrame] = {}
    for source, frame in operational.items():
        try:
            derived_operational[source] = derive_tplnr_hierarchy(frame)
        except DataValidationError as exc:
            raise DataValidationError(f"Fonte {source}: {exc}") from exc

    lookup_source = pd.concat(
        [frame[["EQUIPAMENTO", "GRUPO"]] for frame in derived_operational.values()],
        ignore_index=True,
    ) if derived_operational else pd.DataFrame(columns=["EQUIPAMENTO", "GRUPO"])
    lookup_source["EQUIPAMENTO"] = lookup_source["EQUIPAMENTO"].astype("string").str.strip()
    lookup_source["GRUPO"] = lookup_source["GRUPO"].astype("string").str.strip()
    groups_per_equipment = lookup_source.groupby("EQUIPAMENTO")["GRUPO"].nunique()
    ambiguous = groups_per_equipment[groups_per_equipment > 1]
    if not ambiguous.empty:
        error = DataValidationError(
            "Equipamento associado a multiplos grupos: " + ", ".join(ambiguous.index.astype(str))
        )
        error.correction = "resolver equipamento em um unico grupo"
        raise error
    lookup = lookup_source.drop_duplicates("EQUIPAMENTO")

    if "EQUIPAMENTO" not in indicators.columns:
        raise DataValidationError("Indicadores requerem a coluna EQUIPAMENTO para o mapeamento")
    mapped_indicators = indicators.copy()
    mapped_indicators["EQUIPAMENTO"] = mapped_indicators["EQUIPAMENTO"].astype("string").str.strip()
    if "GRUPO" in mapped_indicators.columns:
        mapped_indicators = mapped_indicators.drop(columns=["GRUPO"])
    mapped_indicators = mapped_indicators.merge(lookup, on="EQUIPAMENTO", how="left", sort=False)
    missing_group = mapped_indicators["GRUPO"].isna() | mapped_indicators["GRUPO"].astype("string").str.strip().eq("")
    if missing_group.any():
        sample = mapped_indicators.loc[missing_group, "EQUIPAMENTO"].head(3).astype(str).tolist()
        error = DataValidationError(
            "Cobertura incompleta da hierarquia para equipamentos dos indicadores; amostra: "
            + ", ".join(sample)
        )
        error.correction = "incluir cobertura hierarquica para o equipamento"
        raise error
    return mapped_indicators, derived_operational


def build_group_mapping(
    indicators: pd.DataFrame,
    operational: Mapping[str, pd.DataFrame],
    map_file: Path | None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Apply only an explicit equipment-to-group mapping to every source."""
    frames = {"indicadores": _normalize_group_values(indicators, "indicadores"), **{
        name: _normalize_group_values(frame, name) for name, frame in operational.items()
    }}
    if map_file is None:
        missing = [name for name, frame in frames.items() if "GRUPO" not in frame.columns]
        if missing:
            raise _mapping_error(
                "mapeamento de GRUPO ausente nas fontes: " + ", ".join(missing) + ". "
                "Nao e permitido inferir grupo a partir de TPLNR; use --group-map-file."
            )
        return frames["indicadores"], {name: frames[name] for name in operational}

    if not map_file.is_file():
        raise _mapping_error(f"Arquivo de mapeamento nao encontrado: {map_file}")
    try:
        mapping = pd.read_csv(map_file, sep=None, engine="python")
    except Exception as exc:
        raise _mapping_error(f"Nao foi possivel ler o mapeamento {map_file}: {exc}") from exc
    mapping = normalize_columns(mapping)
    key = _mapping_key(mapping)
    group = next((column for column in mapping.columns if _column_key(column) == "GRUPO"), None)
    if key is None or group is None:
        raise _mapping_error("O mapeamento deve conter EQUIPAMENTO ou TPLNR e GRUPO")
    for column in (key, group):
        values = mapping[column].astype("string")
        mapping[column] = values.str.strip().replace("", pd.NA)
    invalid_map = int((mapping[key].isna() | mapping[group].isna()).sum())
    if invalid_map:
        raise _mapping_error(
            f"Arquivo de mapeamento contem linhas nulos ({invalid_map}) em {key}/GRUPO; "
            "corrija as chaves e grupos antes do join"
        )
    if mapping[key].duplicated().any():
        raise _mapping_error(f"Chave {key} duplicada no arquivo de mapeamento")
    lookup = mapping.set_index(key)[group]
    mapped: dict[str, pd.DataFrame] = {}
    for name, frame in frames.items():
        result = frame.copy()
        source_key = _mapping_key(result)
        expected = result[source_key].map(lookup) if source_key is not None else None
        if expected is not None and (result[source_key].notna() & expected.isna()).any():
            raise _mapping_error(f"Cobertura incompleta do mapeamento na fonte {name}")
        if "GRUPO" in result.columns and expected is not None:
            existing = result["GRUPO"]
            inconsistent = existing.notna() & expected.notna() & (existing.astype("string") != expected.astype("string"))
            if inconsistent.any():
                raise _mapping_error(f"GRUPO explicito inconsistente com a chave na fonte {name}")
            result["GRUPO"] = existing.where(existing.notna(), expected)
        elif "GRUPO" not in result.columns:
            if expected is None:
                raise _mapping_error(f"Fonte {name} nao possui EQUIPAMENTO/TPLNR para aplicar o mapeamento")
            result["GRUPO"] = expected
        if result["GRUPO"].isna().any():
            sample = result.loc[result["GRUPO"].isna(), _mapping_key(result) or "GRUPO"].astype(str).head(3).tolist()
            raise _mapping_error(f"Cobertura incompleta do mapeamento na fonte {name}; amostra: {sample}")
        mapped[name] = result
    return mapped.pop("indicadores"), mapped


def _month_column(frame: pd.DataFrame) -> str | None:
    keys = {_column_key(column): column for column in frame.columns}
    if "AMSYEAR" in keys and "AMSMON" in keys:
        return f"{keys['AMSYEAR']}+{keys['AMSMON']}"
    return next((keys[key] for key in ("MES", "ANOMES", "CALMONTH", "AMSMON") if key in keys), None)


def _parse_month_column(frame: pd.DataFrame, month: str) -> pd.Series:
    if "+" not in month:
        return frame[month] if isinstance(frame[month].dtype, pd.PeriodDtype) else parse_month_series(frame[month], "MES")
    year_column, month_column = month.split("+", 1)
    raw_month = frame[month_column].astype("string").str.strip()
    six_digits = raw_month.str.fullmatch(r"\d{6}")
    combined = raw_month.where(
        six_digits,
        frame[year_column].astype("string").str.strip() + raw_month.str.zfill(2),
    )
    return parse_month_series(combined, "MES")


def aggregate_monthly_data(frame: pd.DataFrame, excluded_columns: Sequence[str] = ()) -> pd.DataFrame:
    """Aggregate eligible columns at ``GRUPO``/month and attach coverage stats."""
    if "GRUPO" not in frame.columns or _month_column(frame) is None:
        raise DataValidationError("Base operacional requer GRUPO e uma coluna mensal")
    result = frame.copy()
    month = _month_column(result)
    assert month is not None
    result["MES"] = _parse_month_column(result, month)
    input_rows = len(result)
    result = result.loc[result["GRUPO"].notna() & result["MES"].notna()].copy()
    keys = {"GRUPO", "MES", month, "EQUIPAMENTO", "TPLNR", *excluded_columns}
    if "+" in month:
        keys.update(month.split("+"))
    aggregations: dict[str, pd.Series] = {}
    for column in result.columns:
        if column in keys:
            continue
        numeric = pd.to_numeric(result[column], errors="coerce")
        if numeric.notna().any() and numeric.notna().mean() >= 0.95:
            values = numeric
            aggregations[f"{column}_sum"] = values.groupby([result["GRUPO"], result["MES"]]).sum()
            aggregations[f"{column}_mean"] = values.groupby([result["GRUPO"], result["MES"]]).mean()
            aggregations[f"{column}_median"] = values.groupby([result["GRUPO"], result["MES"]]).median()
            aggregations[f"{column}_min"] = values.groupby([result["GRUPO"], result["MES"]]).min()
            aggregations[f"{column}_max"] = values.groupby([result["GRUPO"], result["MES"]]).max()
            aggregations[f"{column}_count"] = values.groupby([result["GRUPO"], result["MES"]]).count()
            aggregations[f"{column}_nunique"] = values.groupby([result["GRUPO"], result["MES"]]).nunique()
        else:
            if len(result) >= 10 and result[column].nunique(dropna=True) / max(len(result), 1) > 0.95:
                continue
            groups = result.groupby(["GRUPO", "MES"])[column]
            aggregations[f"{column}_count"] = groups.count()
            aggregations[f"{column}_nunique"] = groups.nunique()
            proportions = result.assign(_value=result[column].astype("string")).groupby(["GRUPO", "MES", "_value"]).size()
            for value in result[column].dropna().astype("string").unique():
                aggregations[f"{column}_prop_{value}"] = proportions.groupby(level=[0, 1]).sum() * 0.0
                for index in proportions.index:
                    if index[2] == value:
                        aggregations[f"{column}_prop_{value}"].loc[index[:2]] = proportions.loc[index]
                aggregations[f"{column}_prop_{value}"] = aggregations[f"{column}_prop_{value}"].div(groups.size()).fillna(0)
    output = pd.DataFrame(aggregations).reset_index() if aggregations else result[["GRUPO", "MES"]].drop_duplicates()
    output = output.sort_values(["GRUPO", "MES"]).reset_index(drop=True)
    observed = set(result["MES"].dropna())
    output.attrs["coverage_report"] = pd.DataFrame([{
        "fonte": "desconhecida", "linhas_entrada": input_rows,
        "linhas_validas": len(result), "linhas_perdidas": input_rows - len(result),
        "meses_observados": len(observed), "meses_sem_cobertura": 0,
        "cardinalidade_join": len(output), "linhas_perdidas_join": 0,
        "taxa_cobertura": len(result) / input_rows if input_rows else 0.0,
    }])
    output.attrs["observed_months"] = observed
    output.attrs["observed_keys"] = set(zip(result["GRUPO"], result["MES"]))
    return output


def build_operational_features(
    operational: Mapping[str, pd.DataFrame],
    feature_config: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Discover monthly candidates and explicitly configured derivations.

    ``feature_config`` accepts either a list of specs or a mapping with a
    ``derived`` list, optional ``future_columns`` list and optional
    ``reference_frame`` at the indicator grain. Each spec has
    ``name``, ``source``, ``fields``, ``transform`` (``sum``, ``mean``,
    ``difference`` or a callable), ``aggregation`` and ``semantic_status``.
    A derived feature is created only when all fields validate and a transform
    is present. No AMS/AMC/APR/backlog alias is inferred from a column name.
    """
    fixed_excluded = pd.DataFrame(columns=["fonte", "campo_original", "motivo"])
    if isinstance(feature_config, Mapping):
        specs = feature_config.get("derived", [])
        reference_frame = feature_config.get("reference_frame")
        configured_future = feature_config.get("future_columns", [])
        future_columns = set(configured_future) if not isinstance(configured_future, Mapping) else {
            field for fields in configured_future.values() for field in fields
        }
        if isinstance(future_columns, Mapping):
            future_columns = set(future_columns.get("*") or [])
    else:
        specs = feature_config or []
        reference_frame = None
        future_columns = set()
    if not isinstance(specs, Sequence) or isinstance(specs, (str, bytes)):
        raise DataValidationError("feature_config.derived deve ser uma lista de specs")
    frames: list[pd.DataFrame] = []
    metadata: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    coverage: list[pd.DataFrame] = []
    reference_keys = set()
    if isinstance(reference_frame, pd.DataFrame) and "GRUPO" in reference_frame.columns:
        reference = _normalize_group_values(reference_frame, "indicadores")
        reference_month = _month_column(reference)
        if reference_month is not None:
            reference["MES"] = _parse_month_column(reference, reference_month)
            reference_keys = set(zip(reference.loc[reference["MES"].notna(), "GRUPO"], reference.loc[reference["MES"].notna(), "MES"]))
    id_names = {"AUFNR", "QMNUM", "AUFPL", "APLZL", "VORNR", "ID", "IDATE", "QMART"}
    for source, frame in operational.items():
        month = _month_column(frame)
        month_parts = set(month.split("+")) if month and "+" in month else {month}
        source_excluded: set[str] = set()
        structural_columns = {"GRUPO", "EQUIPAMENTO", "TPLNR"}
        if month:
            structural_columns.update(month.split("+"))
            if "+" not in month:
                structural_columns.add(month)
        for column in frame.columns:
            key = _column_key(column)
            structural_name = column in structural_columns or any(token in key for token in (
                "PRIMARYKEYJOIN", "AMSWEEK", "AMSDAYDATE", "EVENTDATE", "DATACRIACAO",
                "DATAEVENTO", "DATAPREVISTA", "DATAEXECUCAO", "YEAR", "MONTH", "WEEK", "DAY",
            ))
            if structural_name:
                source_excluded.add(column)
                excluded.append({"fonte": source, "campo_original": column, "motivo": "chave estrutural"})
        for column in frame.columns:
            key = _column_key(column)
            if column in source_excluded:
                continue
            future = column in future_columns or key in {_column_key(item) for item in future_columns}
            posterior = any(token in key for token in ("FUTURE", "POSTERIOR", "DATACONCLUSAO", "DATAREALIZACAO"))
            identifier = key in id_names or key.endswith("ID") or key.startswith("ID")
            numeric_high_cardinality = len(frame) >= 10 and frame[column].nunique(dropna=True) / max(len(frame), 1) > 0.95
            text_high_cardinality = frame[column].dtype == object and numeric_high_cardinality
            if future or posterior:
                source_excluded.add(column)
                excluded.append({"fonte": source, "campo_original": column, "motivo": "disponibilidade posterior"})
            elif identifier or text_high_cardinality:
                source_excluded.add(column)
                excluded.append({"fonte": source, "campo_original": column, "motivo": "identificador/chave ou alta cardinalidade"})
        source_excluded -= {"GRUPO", "EQUIPAMENTO", "TPLNR", *month_parts}
        aggregate = aggregate_monthly_data(frame, source_excluded)
        report = aggregate.attrs.get("coverage_report", pd.DataFrame())
        if not report.empty:
            report = report.copy()
            report["fonte"] = source
            report["meses_observados_set"] = [aggregate.attrs.get("observed_months", set())]
            observed_keys = aggregate.attrs.get("observed_keys", set())
            report["cardinalidade_join"] = len(observed_keys)
            report["chaves_sem_correspondencia"] = len(observed_keys - reference_keys) if reference_keys else 0
            report["chaves_referencia_sem_fonte"] = len(reference_keys - observed_keys) if reference_keys else 0
            report["linhas_perdidas_join"] = report["chaves_sem_correspondencia"]
            report["operational_keys_without_indicator"] = report["chaves_sem_correspondencia"]
            report["indicator_keys_without_operational"] = report["chaves_referencia_sem_fonte"]
            report["percentual_cobertura"] = (
                len(observed_keys & reference_keys) / len(reference_keys) * 100 if reference_keys else 0.0
            )
            coverage.append(report)
        aggregate = aggregate.rename(columns={column: f"{source}__{column}" for column in aggregate.columns if column not in {"GRUPO", "MES"}})
        aggregate.attrs.clear()
        frames.append(aggregate)
        for feature in aggregate.columns:
            if feature in {"GRUPO", "MES"}:
                continue
            original = feature[len(source) + 2:].rsplit("_", 1)[0]
            metadata.append({"feature": feature, "fonte": source, "campo_original": original,
                             "transformacao": feature.rsplit("_", 1)[-1], "mes_referencia": "t",
                             "defasagem": 0, "observacoes_validas": int(aggregate[feature].notna().sum()),
                             "risco_vazamento": "baixo", "status_semantico": "nao_confirmado"})
    if not frames:
        empty = pd.DataFrame(columns=["GRUPO", "MES"])
        metadata_frame = pd.DataFrame(columns=FEATURE_METADATA_COLUMNS)
        metadata_frame.attrs["coverage_report"] = pd.DataFrame(columns=["fonte", "linhas_entrada", "linhas_validas", "linhas_perdidas", "meses_observados", "meses_sem_cobertura", "cardinalidade_join", "linhas_perdidas_join", "taxa_cobertura", "chaves_sem_correspondencia", "chaves_referencia_sem_fonte", "operational_keys_without_indicator", "indicator_keys_without_operational", "percentual_cobertura"])
        return empty, metadata_frame, fixed_excluded
    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on=["GRUPO", "MES"], how="outer", validate="one_to_one")
    for spec in specs:
        if not isinstance(spec, Mapping) or not spec.get("name") or not spec.get("source") or not spec.get("fields") or not spec.get("transform"):
            raise DataValidationError("Cada spec derivada requer name, source, fields e transform")
        source = str(spec["source"])
        if source not in operational:
            raise DataValidationError(f"Fonte ausente na spec derivada: {source}")
        fields = list(spec["fields"])
        missing = [field for field in fields if field not in operational[source].columns]
        if missing:
            raise DataValidationError(f"Campos ausentes na spec {spec['name']}: {missing}")
        source_frame = operational[source].copy()
        month = _month_column(source_frame)
        assert month is not None
        source_frame["MES"] = _parse_month_column(source_frame, month)
        values = source_frame[fields].apply(pd.to_numeric, errors="coerce")
        transform = spec["transform"]
        if callable(transform):
            derived_values = transform(values)
        elif transform == "sum":
            derived_values = values.sum(axis=1)
        elif transform == "mean":
            derived_values = values.mean(axis=1)
        elif transform == "difference" and len(fields) == 2:
            derived_values = values.iloc[:, 0] - values.iloc[:, 1]
        else:
            raise DataValidationError(f"Transformacao nao suportada na spec {spec['name']}")
        aggregation = spec.get("aggregation", "sum")
        grouped = derived_values.groupby([source_frame["GRUPO"], source_frame["MES"]])
        if aggregation not in {"sum", "mean", "median", "min", "max", "count", "nunique"}:
            raise DataValidationError(f"Agregacao nao suportada na spec {spec['name']}")
        value = getattr(grouped, aggregation)().rename(str(spec["name"]))
        result = result.merge(value.reset_index(), on=["GRUPO", "MES"], how="left", validate="one_to_one")
        metadata.append({"feature": str(spec["name"]), "fonte": source, "campo_original": ",".join(fields),
                         "transformacao": str(transform), "mes_referencia": "t", "defasagem": 0,
                         "observacoes_validas": int(value.notna().sum()), "risco_vazamento": "baixo",
                         "status_semantico": spec.get("semantic_status", "nao_confirmado")})
    metadata_frame = pd.DataFrame(metadata, columns=FEATURE_METADATA_COLUMNS)
    coverage_frame = pd.concat(coverage, ignore_index=True) if coverage else pd.DataFrame()
    if not coverage_frame.empty:
        all_months = set().union(*coverage_frame["meses_observados_set"].tolist())
        coverage_frame["meses_sem_cobertura"] = coverage_frame["meses_observados_set"].map(lambda months: len(all_months - months))
        coverage_frame = coverage_frame.drop(columns=["meses_observados_set"])
        coverage_frame["meses_sem_cobertura"] = coverage_frame["meses_sem_cobertura"].astype(int)
    metadata_frame.attrs["coverage_report"] = coverage_frame
    excluded_frame = pd.DataFrame(excluded, columns=["fonte", "campo_original", "motivo"])
    result = result.sort_values(["GRUPO", "MES"]).reset_index(drop=True)
    result.attrs["feature_metadata"] = metadata_frame
    result.attrs["coverage_report"] = coverage_frame
    return result, metadata_frame, excluded_frame


def create_lag_features(
    frame: pd.DataFrame, feature_columns: Sequence[str], max_lag: int,
    response_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create current and historical values within each group only.

    Response columns are rejected explicitly. They can be supplied through
    ``response_columns``; otherwise canonical reliability response names and
    names derived from them are detected conservatively.
    """
    if max_lag < 0:
        raise DataValidationError("max_lag deve ser nao negativo")
    if not {"GRUPO", "MES"}.issubset(frame.columns):
        raise DataValidationError("Lags requerem as colunas GRUPO e MES")
    canonical_responses = set(response_columns or ()) | {"DF (REAL)", "MTBF (REAL)", "MTBS (REAL)", "MTTR", "NIC (VMINA)"}
    response_keys = {_column_key(column) for column in canonical_responses}
    source_metadata = frame.attrs.get("feature_metadata")
    metadata_by_feature = {}
    if isinstance(source_metadata, pd.DataFrame) and "feature" in source_metadata.columns:
        metadata_by_feature = source_metadata.set_index("feature").to_dict("index")
    for feature in feature_columns:
        feature_key = _column_key(feature)
        original_key = _column_key(metadata_by_feature.get(feature, {}).get("campo_original", ""))
        if any(token in feature_key or token in original_key for token in response_keys):
            raise DataValidationError(f"Feature {feature} e resposta ou derivada de resposta; nao pode virar lag")
    result = frame.sort_values(["GRUPO", "MES"]).reset_index(drop=True).copy()
    records: list[dict[str, object]] = []
    metadata_events: list[dict[str, str]] = []
    for feature in feature_columns:
        if feature not in result.columns:
            raise DataValidationError(f"Feature ausente para lag: {feature}")
        if feature not in metadata_by_feature:
            metadata_events.append({"tipo": "metadata_ausente", "feature": feature,
                                    "mensagem": "Fonte, status semantico e risco nao foram fornecidos"})
        grouped = result.groupby("GRUPO", sort=False)[feature]
        for lag in range(max_lag + 1):
            name = f"{feature}_lag_{lag}"
            result[name] = grouped.shift(lag) if lag else result[feature]
            original = metadata_by_feature.get(feature, {})
            records.append({"feature": name, "fonte": original.get("fonte", "desconhecida"),
                            "campo_original": original.get("campo_original", feature),
                            "transformacao": "shift", "mes_referencia": "t", "defasagem": lag,
                            "observacoes_validas": int(result[name].notna().sum()),
                            "risco_vazamento": original.get("risco_vazamento", "nao_avaliado"),
                            "status_semantico": original.get("status_semantico", "nao_confirmado")})
    if "resposta" in result.columns:
        result["resposta_t1"] = result.groupby("GRUPO", sort=False)["resposta"].shift(-1)
    metadata = pd.DataFrame(records, columns=FEATURE_METADATA_COLUMNS)
    metadata.attrs["events"] = pd.DataFrame(metadata_events, columns=["tipo", "feature", "mensagem"])
    metadata.attrs["coverage_report"] = (
        source_metadata.attrs.get("coverage_report", pd.DataFrame())
        if isinstance(source_metadata, pd.DataFrame)
        else pd.DataFrame()
    )
    return result, metadata


PREDICTION_COLUMNS = [
    "resposta", "modelo", "periodo", "valor_real", "valor_previsto",
    "erro", "erro_absoluto", "erro_percentual", "divisao", "fora_amostra",
]


CANONICAL_RELIABILITY_RESPONSES = {
    "DF (REAL)", "MTBF (REAL)", "MTBS (REAL)", "MTTR", "NIC (VMINA)",
}


def _is_reliability_response_feature(
    column: str,
    metadata_by_feature: Mapping[str, Mapping[str, object]],
) -> bool:
    """Identify a canonical response or any feature explicitly derived from one."""
    response_keys = {_column_key(name) for name in CANONICAL_RELIABILITY_RESPONSES}
    details = metadata_by_feature.get(column, {})
    values = (column, details.get("campo_original", ""), details.get("papel", ""))
    return (
        str(details.get("papel", "")).lower() == "resposta"
        or any(
            response_key and response_key in _column_key(str(value))
            for response_key in response_keys
            for value in values
        )
    )


def _select_predictor_columns(
    frame: pd.DataFrame,
    response: str,
    predictor_columns: Sequence[str] | None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Select only numeric operational predictors and audit every rejection."""
    source_metadata = frame.attrs.get("feature_metadata", pd.DataFrame())
    metadata_by_feature: dict[str, Mapping[str, object]] = {}
    if isinstance(source_metadata, pd.DataFrame) and "feature" in source_metadata.columns:
        metadata_by_feature = source_metadata.set_index("feature").to_dict("index")
    requested = (
        list(predictor_columns)
        if predictor_columns is not None
        else frame.select_dtypes(include=[np.number]).columns.tolist()
    )
    selected: list[str] = []
    excluded: list[dict[str, str]] = []
    for column in dict.fromkeys(requested):
        if column not in frame.columns:
            excluded.append({"feature": str(column), "motivo": "preditor ausente"})
        elif column in {response, "_target"} or _is_reliability_response_feature(column, metadata_by_feature):
            excluded.append({"feature": str(column), "motivo": "resposta de confiabilidade ou derivada"})
        elif not pd.api.types.is_numeric_dtype(frame[column]):
            excluded.append({"feature": str(column), "motivo": "preditor nao numerico"})
        else:
            selected.append(str(column))
    return selected, excluded


def _operational_coverage_mask(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    min_feature_non_null: float,
) -> pd.Series:
    """Keep rows with the configured fraction of observed operational predictors."""
    if not feature_columns:
        return pd.Series(False, index=frame.index)
    non_null_fraction = frame.loc[:, list(feature_columns)].notna().mean(axis=1)
    return non_null_fraction.ge(min_feature_non_null)


def calculate_regression_metrics(
    y_true: pd.Series, y_pred: pd.Series, n_features: int
) -> dict[str, float]:
    """Calculate regression metrics without inventing values for undefined cases."""
    actual = pd.to_numeric(pd.Series(y_true), errors="coerce")
    predicted = pd.to_numeric(pd.Series(y_pred), errors="coerce")
    valid = actual.notna() & predicted.notna()
    actual = actual[valid].astype(float)
    predicted = predicted[valid].astype(float)
    if actual.empty:
        return {name: float("nan") for name in (
            "mae", "rmse", "mape", "r2", "r2_ajustado", "pearson",
            "spearman", "erro_medio", "erro_percentual_medio",
        )}
    error = predicted - actual
    nonzero = actual.ne(0)
    percentage_error = error[nonzero].div(actual[nonzero]) * 100
    actual_values = actual.to_numpy()
    predicted_values = predicted.to_numpy()
    ss_total = float(((actual - actual.mean()) ** 2).sum())
    ss_residual = float((error ** 2).sum())
    r2 = float(1 - ss_residual / ss_total) if ss_total > 0 else float("nan")
    n = len(actual)
    p = max(int(n_features), 0)
    adjusted = (
        float(1 - (1 - r2) * (n - 1) / (n - p - 1))
        if np.isfinite(r2) and n > p + 1 else float("nan")
    )
    pearson = float(pd.Series(actual_values).corr(pd.Series(predicted_values)))
    spearman = float(pd.Series(actual_values).corr(pd.Series(predicted_values), method="spearman"))
    return {
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "mape": float(np.abs(percentage_error).mean()) if not percentage_error.empty else float("nan"),
        "r2": r2,
        "r2_ajustado": adjusted,
        "pearson": pearson,
        "spearman": spearman,
        "erro_medio": float(error.mean()),
        "erro_percentual_medio": float(percentage_error.mean()) if not percentage_error.empty else float("nan"),
    }


def build_model_pipeline(model_name: str, random_state: int) -> Pipeline:
    """Build a leakage-safe preprocessing and estimator pipeline."""
    normalized = model_name.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"elastic_net", "elasticnet"}:
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", ElasticNet(random_state=random_state, max_iter=10000)),
        ])
    if normalized in {"random_forest", "randomforest"}:
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(random_state=random_state, n_jobs=1)),
        ])
    raise ValueError(f"Modelo nao suportado: {model_name}")


class _PeriodTimeSeriesSplit:
    """Split complete periods, never individual rows, into chronological folds."""

    def __init__(self, n_splits: int, periods: Sequence[object]):
        self.n_splits = n_splits
        self.periods = np.asarray(periods)

    def get_n_splits(self, X: object = None, y: object = None, groups: object = None) -> int:
        return self.n_splits

    def split(
        self, X: object, y: object = None, groups: object = None
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        unique = pd.Index(self.periods).drop_duplicates().sort_values()
        if len(unique) <= self.n_splits:
            raise ValueError("Periodos insuficientes para validacao temporal")
        validation_positions = np.array_split(np.arange(1, len(unique)), self.n_splits)
        for positions in validation_positions:
            if len(positions) == 0:
                continue
            train_periods = set(unique[: positions[0]])
            validation_periods = set(unique[positions])
            train = np.flatnonzero(pd.Series(self.periods).isin(train_periods).to_numpy())
            validation = np.flatnonzero(pd.Series(self.periods).isin(validation_periods).to_numpy())
            if len(train) and len(validation):
                yield train, validation


def _prediction_frame(
    response: str, model: str, periods: pd.Series, actual: pd.Series,
    predicted: pd.Series, division: str, groups: pd.Series,
) -> pd.DataFrame:
    error = predicted - actual
    denominator = actual.replace(0, np.nan)
    result = pd.DataFrame({
        "resposta": response, "modelo": model, "periodo": periods,
        "GRUPO": groups, "valor_real": actual, "valor_previsto": predicted,
        "erro": error, "erro_absoluto": error.abs(),
        "erro_percentual": error.div(denominator) * 100,
        "divisao": division, "fora_amostra": True,
    })
    return result.reset_index(drop=True)


def _fit_search(
    model_name: str, X: pd.DataFrame, y: pd.Series, periods: pd.Series,
    random_state: int, n_splits: int,
) -> tuple[Pipeline, dict[str, Any]]:
    pipeline = build_model_pipeline(model_name, random_state)
    if n_splits < 2:
        pipeline.fit(X, y)
        return pipeline, {}
    if model_name == "elastic_net":
        grid = {"model__alpha": [0.1, 1.0], "model__l1_ratio": [0.2, 0.8]}
    else:
        grid = {"model__n_estimators": [50], "model__max_depth": [None, 5]}
    splitter = _PeriodTimeSeriesSplit(n_splits, periods.tolist())
    search = GridSearchCV(pipeline, grid, cv=splitter, scoring="neg_mean_absolute_error", refit=True, n_jobs=1)
    search.fit(X, y)
    return search.best_estimator_, search.best_params_


def run_temporal_validation(
    data: pd.DataFrame,
    response: str,
    config: Config,
    predictor_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Train models with chronological splits and an explicit predictor contract."""
    empty_predictions = pd.DataFrame(columns=PREDICTION_COLUMNS + ["GRUPO"])
    empty_splits = pd.DataFrame(columns=[
        "divisao", "fold", "train_rows", "test_rows", "train_max_period",
        "test_min_period", "train_periods", "test_periods",
        "train_max_target_period", "test_min_target_period",
        "train_target_periods", "test_target_periods",
    ])
    period_column = "MES" if "MES" in data.columns else "periodo" if "periodo" in data.columns else None
    if period_column is None or response not in data.columns:
        return empty_predictions, empty_splits, {"status": "insuficiente", "motivo": "periodo ou resposta ausente"}
    frame = data.copy()
    frame[period_column] = frame[period_column].map(
        lambda value: value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
    )
    frame = frame.sort_values([period_column, "GRUPO"] if "GRUPO" in frame.columns else [period_column]).reset_index(drop=True)
    group_column = "GRUPO" if "GRUPO" in frame.columns else None
    if group_column:
        grouped = frame.groupby(group_column, sort=False)
        frame["_target"] = grouped[response].shift(-1)
        frame["_target_period"] = grouped[period_column].shift(-1)
    else:
        frame["_target"] = frame[response].shift(-1)
        frame["_target_period"] = frame[period_column].shift(-1)
    frame = frame.loc[
        frame["_target"].notna()
        & frame["_target_period"].eq(frame[period_column] + 1)
    ].copy()
    feature_columns, excluded_features = _select_predictor_columns(
        frame, response, predictor_columns
    )
    coverage_mask = _operational_coverage_mask(
        frame, feature_columns, config.min_feature_non_null
    )
    dropped = frame.loc[~coverage_mask].copy()
    coverage_audit = {
        "min_feature_non_null": config.min_feature_non_null,
        "dropped_rows_without_operational_coverage": int((~coverage_mask).sum()),
        "dropped_source_periods": tuple(dropped[period_column].dropna().unique()),
        "dropped_target_periods": tuple(dropped["_target_period"].dropna().unique()),
    }
    frame = frame.loc[coverage_mask].copy()
    periods = pd.Index(frame["_target_period"].dropna().unique()).sort_values()
    test_periods = periods[-config.test_months:] if len(periods) else periods
    train_periods = periods[:-config.test_months] if len(periods) > config.test_months else periods[:0]
    metadata_context = {
        "feature_columns": feature_columns,
        "predictor_columns": feature_columns,
        "excluded_features": excluded_features,
        "coverage_audit": coverage_audit,
        "dropped_periods": coverage_audit["dropped_target_periods"],
    }
    if (
        len(train_periods) < 3 or len(test_periods) == 0 or not feature_columns
        or int(frame[frame["_target_period"].isin(train_periods)].shape[0]) < config.min_train_rows
        or int(frame[frame["_target_period"].isin(test_periods)].shape[0]) < config.min_test_rows
    ):
        train_rows = int(frame[frame["_target_period"].isin(train_periods)].shape[0])
        test_rows = int(frame[frame["_target_period"].isin(test_periods)].shape[0])
        empty_metric_values = {name: float("nan") for name in (
            "mae", "rmse", "mape", "r2", "r2_ajustado", "pearson", "spearman",
            "erro_medio", "erro_percentual_medio", "variacao_janela",
        )}
        insufficient_metrics = [{
            "resposta": response, "modelo": model_name, "divisao": "teste_final",
            "fold": "final", "fora_amostra": True, "train_rows": train_rows,
            "test_rows": test_rows, "observacoes_teste": test_rows,
            "periodos_teste": tuple(test_periods), "status": "insuficiente",
            **empty_metric_values,
        } for model_name in ("elastic_net", "random_forest", "baseline_t1")]
        return empty_predictions, empty_splits, {
            "status": "insuficiente", "motivo": "linhas ou periodos insuficientes",
            "train_rows": train_rows, "test_rows": test_rows,
            "metricas": insufficient_metrics,
            **metadata_context,
        }
    train = frame[frame["_target_period"].isin(train_periods)].copy()
    final_test = frame[frame["_target_period"].isin(test_periods)].copy()
    n_splits = min(3, len(train_periods) - 1)
    if n_splits < 2:
        return empty_predictions, empty_splits, {
            "status": "insuficiente", "motivo": "janelas temporais insuficientes",
            **metadata_context,
        }
    split_records: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    hyperparameters: dict[str, dict[str, Any]] = {}
    final_estimators: dict[str, Pipeline] = {}
    metric_stability: dict[str, dict[str, dict[str, Any]]] = {}
    metric_records: list[dict[str, Any]] = []
    for model_name in ("elastic_net", "random_forest"):
        oof_predictions: list[pd.DataFrame] = []
        fold_metrics: list[dict[str, float]] = []
        oof_splitter = _PeriodTimeSeriesSplit(n_splits, train["_target_period"].tolist())
        for fold, (fit_indices, validation_indices) in enumerate(oof_splitter.split(train[feature_columns])):
            fit_frame = train.iloc[fit_indices]
            validation = train.iloc[validation_indices]
            estimator, params = _fit_search(
                model_name, fit_frame[feature_columns], fit_frame["_target"],
                fit_frame["_target_period"], config.random_state,
                min(2, len(pd.Index(fit_frame["_target_period"].unique())) - 1),
            )
            estimator.fit(fit_frame[feature_columns], fit_frame["_target"])
            predicted = pd.Series(estimator.predict(validation[feature_columns]), index=validation.index)
            oof_predictions.append(_prediction_frame(
                response, model_name, validation["_target_period"], validation["_target"],
                predicted, "oof", validation[group_column] if group_column else pd.Series("*", index=validation.index),
            ))
            fold_metric = calculate_regression_metrics(validation["_target"], predicted, len(feature_columns))
            fold_metrics.append(fold_metric)
            metric_records.append({
                "resposta": response, "modelo": model_name, "divisao": "oof",
                "fold": fold, "fora_amostra": True, "train_rows": len(fit_frame),
                "test_rows": len(validation), "observacoes_teste": len(validation),
                "periodos_teste": tuple(validation["_target_period"].unique()), **fold_metric,
            })
            split_records.append({
                "divisao": "oof", "fold": fold, "modelo": model_name,
                "train_rows": len(fit_frame), "test_rows": len(validation),
                "train_max_period": fit_frame["_target_period"].max(),
                "test_min_period": validation["_target_period"].min(),
                "train_periods": tuple(fit_frame["_target_period"].unique()),
                "test_periods": tuple(validation["_target_period"].unique()),
                "train_max_target_period": fit_frame["_target_period"].max(),
                "test_min_target_period": validation["_target_period"].min(),
                "train_target_periods": tuple(fit_frame["_target_period"].unique()),
                "test_target_periods": tuple(validation["_target_period"].unique()),
            })
        final_estimator, final_params = _fit_search(
            model_name, train[feature_columns], train["_target"], train["_target_period"],
            config.random_state, n_splits,
        )
        predicted_test = pd.Series(final_estimator.predict(final_test[feature_columns]), index=final_test.index)
        prediction_frames.extend(oof_predictions)
        prediction_frames.append(_prediction_frame(
            response, model_name, final_test["_target_period"], final_test["_target"],
            predicted_test, "teste", final_test[group_column] if group_column else pd.Series("*", index=final_test.index),
        ))
        hyperparameters[model_name] = final_params
        final_estimators[model_name] = final_estimator
        final_metric = calculate_regression_metrics(final_test["_target"], predicted_test, len(feature_columns))
        metric_records.append({
            "resposta": response, "modelo": model_name, "divisao": "teste_final",
            "fold": "final", "fora_amostra": True, "train_rows": len(train),
            "test_rows": len(final_test), "observacoes_teste": len(final_test),
            "periodos_teste": tuple(final_test["_target_period"].unique()), **final_metric,
        })
        variation = float(np.nanstd([row["mae"] for row in fold_metrics])) if fold_metrics else float("nan")
        for record in metric_records:
            if record["modelo"] == model_name:
                record["variacao_janela"] = variation
        metric_names = (
            "mae", "rmse", "mape", "r2", "r2_ajustado", "pearson", "spearman",
            "erro_medio", "erro_percentual_medio",
        )
        metric_stability[model_name] = {}
        for metric in metric_names:
            window_values = [row[metric] for row in fold_metrics]
            finite_values = [float(value) for value in window_values if np.isfinite(value)]
            metric_stability[model_name][metric] = {
                "media": float(np.mean(finite_values)) if finite_values else None,
                "desvio_padrao": float(np.std(finite_values)) if finite_values else None,
                "por_janela": [float(value) if np.isfinite(value) else None for value in window_values],
            }
    baseline = final_test.copy()
    baseline_pred = baseline[response]
    prediction_frames.append(_prediction_frame(
        response, "baseline_t1", baseline["_target_period"], baseline["_target"], baseline_pred,
        "baseline", baseline[group_column] if group_column else pd.Series("*", index=baseline.index),
    ))
    baseline_metric = calculate_regression_metrics(baseline["_target"], baseline_pred, 1)
    metric_records.append({
        "resposta": response, "modelo": "baseline_t1", "divisao": "teste_final",
        "fold": "final", "fora_amostra": True, "train_rows": len(train),
        "test_rows": len(final_test), "observacoes_teste": len(final_test),
        "periodos_teste": tuple(final_test["_target_period"].unique()),
        "variacao_janela": float("nan"), **baseline_metric,
    })
    split_records.append({
        "divisao": "teste", "fold": "final", "modelo": "todos",
        "train_rows": len(train), "test_rows": len(final_test),
        "train_max_period": train["_target_period"].max(), "test_min_period": final_test["_target_period"].min(),
        "train_periods": tuple(train["_target_period"].unique()), "test_periods": tuple(final_test["_target_period"].unique()),
        "train_max_target_period": train["_target_period"].max(),
        "test_min_target_period": final_test["_target_period"].min(),
        "train_target_periods": tuple(train["_target_period"].unique()),
        "test_target_periods": tuple(final_test["_target_period"].unique()),
    })
    forecast_train_frame = train.copy()
    forecast_test_frame = final_test.copy()
    forecast_train_frame.attrs["feature_columns"] = list(feature_columns)
    forecast_train_frame.attrs["forecast_train_frame"] = True
    forecast_test_frame.attrs["feature_columns"] = list(feature_columns)
    forecast_test_frame.attrs["forecast_test_frame"] = True
    forecast_test_frame.attrs["fora_amostra"] = True
    metadata = {
        "status": "ok", "response": response, "test_months": config.test_months,
        "train_rows": len(train), "test_rows": len(final_test),
        "final_estimators": final_estimators,
        "forecast_train_frame": forecast_train_frame,
        "forecast_test_frame": forecast_test_frame,
        "forecast_target_column": "_target",
        "hyperparameters": hyperparameters,
        "stabilidade_metricas": metric_stability,
        "metricas": metric_records,
        "train_target_periods": tuple(train["_target_period"].unique()),
        "test_target_periods": tuple(final_test["_target_period"].unique()),
        "splits": len(split_records),
        **metadata_context,
    }
    return pd.concat(prediction_frames, ignore_index=True), pd.DataFrame(split_records), metadata


DIAGNOSTIC_COLUMNS = ["diagnostico", "status", "valor", "gravidade", "mensagem", "grupo"]


def _eligible_explanation_features(
    frame: pd.DataFrame, response: str
) -> tuple[list[str], dict[str, dict[str, object]], list[dict[str, str]]]:
    """Select only numeric, metadata-approved features and record exclusions."""
    metadata = frame.attrs.get("feature_metadata", pd.DataFrame())
    has_metadata = isinstance(metadata, pd.DataFrame) and "feature" in metadata.columns
    metadata_by_feature = metadata.set_index("feature").to_dict("index") if has_metadata else {}
    candidates = list(metadata_by_feature) if has_metadata else list(frame.select_dtypes(include=[np.number]).columns)
    eligible: list[str] = []
    excluded: list[dict[str, str]] = []
    response_keys = {_column_key(response), "DFREAL", "MTBFREAL", "MTBSREAL", "MTTR", "NICVMINA"}
    for feature in candidates:
        item = metadata_by_feature.get(feature, {})
        reason = ""
        feature_key = _column_key(feature)
        if feature == response or any(token in feature_key for token in response_keys if token) or any(token in feature_key for token in ("TARGET", "RESPONSE", "RESPOSTA")):
            reason = "resposta ou resposta alternativa"
        elif feature_key in {"GRUPO", "MES", "ANOMES", "CALMONTH", "EQUIPAMENTO", "TPLNR", "AUFNR", "QMNUM", "AUFPL", "APLZL", "VORNR"} or any(token in feature_key for token in ("PRIMARYKEYJOIN", "AMSWEEK", "AMSDAYDATE")) or feature_key.startswith("ID") or feature_key.endswith("ID"):
            reason = "chave estrutural"
        elif any(token in feature_key for token in ("FUTURE", "POSTERIOR", "LEAK", "LEAKAGE", "VAZAMENTO", "DATACONCLUSAO", "DATAREALIZACAO")):
            reason = "risco/disponibilidade posterior"
        elif feature not in frame.columns or not pd.api.types.is_numeric_dtype(frame[feature]):
            reason = "nao numericamente elegivel"
        elif str(item.get("risco_vazamento", "")).strip().lower() in {"alto", "true", "sim", "confirmado", "leakage"}:
            reason = "risco de vazamento"
        elif str(item.get("papel", item.get("role", item.get("tipo", "")))).strip().lower() in {"resposta", "target", "response"}:
            reason = "resposta alternativa"
        elif any(str(item.get(key, "")).strip().lower() in {"posterior", "futuro", "depois", "after"}
                 for key in ("disponibilidade", "disponibilidade_temporal", "temporalidade")):
            reason = "disponibilidade posterior"
        if reason:
            excluded.append({"feature": str(feature), "motivo": reason})
        else:
            eligible.append(str(feature))
    return eligible, metadata_by_feature, excluded


def _oos_validation_status(
    train_frame: pd.DataFrame, validation_frame: pd.DataFrame | None
) -> tuple[bool, str]:
    """Prove an explicit OOS marker and disjoint row keys before permutation."""
    if validation_frame is None:
        return False, "validation_frame ausente"
    attrs_marker = validation_frame.attrs.get("fora_amostra") is True
    column_marker = "fora_amostra" in validation_frame.columns and validation_frame["fora_amostra"].eq(True).all()
    if not (attrs_marker or column_marker):
        return False, "validation_frame sem marcador fora_amostra=True"
    key_sets = []
    for columns in (("GRUPO", "MES"), ("GRUPO", "periodo"), ("MES",), ("periodo",)):
        if set(columns).issubset(train_frame.columns) and set(columns).issubset(validation_frame.columns):
            train_keys = set(map(tuple, train_frame.loc[:, list(columns)].itertuples(index=False, name=None)))
            validation_keys = set(map(tuple, validation_frame.loc[:, list(columns)].itertuples(index=False, name=None)))
            if train_keys & validation_keys:
                return False, f"sobreposicao de chaves OOS: {columns}"
            key_sets.append(validation_keys)
    if not key_sets and train_frame.index.intersection(validation_frame.index).size:
        return False, "sobreposicao de indices OOS"
    return True, "OOS comprovado"


def run_statistical_diagnostics(
    train_frame: pd.DataFrame, predictions: pd.DataFrame, response: str,
    algebra_relations: Sequence[Mapping[str, object]] | Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Run independent checks, preserving a status row for every check."""
    rows: list[dict[str, object]] = []

    def record(name: str, status: str, value: object = np.nan,
               severity: str = "INFO", message: str = "", group: object = np.nan) -> None:
        rows.append({"diagnostico": name, "status": status, "valor": value,
                     "gravidade": severity, "mensagem": message, "grupo": group})

    numeric = train_frame.select_dtypes(include=[np.number]).copy()
    features, _, _ = _eligible_explanation_features(train_frame, response)
    sample_size = len(train_frame)
    record("amostra", "ok" if sample_size >= 30 else "insuficiente", sample_size,
           "INFO" if sample_size >= 30 else "WARNING", "linhas observadas")

    def safe(name: str, function: Any) -> None:
        try:
            function()
        except Exception as exc:
            record(name, "erro", np.nan, "WARNING", f"diagnostico nao suportado: {exc}")

    def vif_check() -> None:
        if len(features) < 1 or sample_size < max(10, len(features) + 2):
            record("vif", "insuficiente", np.nan, "WARNING", "amostra insuficiente para VIF")
            return
        values = numeric[features].replace([np.inf, -np.inf], np.nan).dropna()
        if len(values) < max(10, len(features) + 2):
            raise ValueError("linhas completas insuficientes")
        matrix = sm.add_constant(values, has_constant="add")
        vifs = [variance_inflation_factor(matrix.to_numpy(), index) for index in range(1, matrix.shape[1])]
        maximum = float(np.nanmax(vifs)) if vifs else np.nan
        record("vif", "ok", maximum, "WARNING" if maximum > 10 else "INFO", "VIF maximo entre features")

    def correlation_check() -> None:
        if len(features) < 2:
            raise ValueError("menos de duas features numericas")
        matrix = numeric[features].corr().abs()
        upper = matrix.where(np.triu(np.ones(matrix.shape), k=1).astype(bool))
        maximum = float(upper.max().max()) if upper.notna().any().any() else np.nan
        record("correlacao", "ok", maximum, "WARNING" if maximum >= 0.9 else "INFO", "correlacoes avaliadas")

    def algebra_check() -> None:
        configured = algebra_relations if algebra_relations is not None else train_frame.attrs.get("algebra_relations")
        relations = configured if isinstance(configured, Sequence) and not isinstance(configured, (str, bytes)) else [configured] if configured else []
        if relations:
            for relation in relations:
                if isinstance(relation, Mapping):
                    record("algebra", "ok", np.nan, "WARNING", f"relacao configurada: {relation.get('formula', relation.get('name', relation))}")
                else:
                    record("algebra", "ok", np.nan, "WARNING", f"relacao configurada: {relation}")
        elif any(token in str(feature).lower() for feature in features for token in ("ratio", "razao", "per")):
            record("algebra", "heuristica", np.nan, "WARNING", "heuristica por nome; relacao nao confirmada")
        else:
            record("algebra", "insuficiente", np.nan, "INFO", "nenhuma formula ou relacao configurada")

    def fit_ols() -> Any:
        if response not in train_frame or not features:
            raise ValueError("resposta ou features ausente")
        complete = numeric[[*features, response]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(complete) < max(10, len(features) + 3):
            raise ValueError("linhas completas insuficientes")
        return sm.OLS(complete[response], sm.add_constant(complete[features], has_constant="add")).fit()

    def residual_check() -> None:
        model = fit_ols()
        residual = model.resid
        standardized = model.get_influence().resid_studentized_internal
        record("residuos", "ok", float(np.sqrt(np.mean(residual ** 2))), "INFO", "RMSE dos residuos OLS")
        record("outliers_residuos", "ok", int((np.abs(standardized) > 3).sum()), "WARNING" if (np.abs(standardized) > 3).any() else "INFO", "residuos padronizados acima de 3")

    def breusch_pagan_check() -> None:
        model = fit_ols()
        bp = het_breuschpagan(model.resid, model.model.exog)
        record("breusch_pagan", "ok", float(bp[1]), "WARNING" if bp[1] < 0.05 else "INFO", "p-valor do teste de heterocedasticidade")

    def condition_check() -> None:
        model = fit_ols()
        condition = float(np.linalg.cond(model.model.exog))
        record("condition_number", "ok", condition, "WARNING" if condition > 1000 else "INFO", "numero de condicao da matriz OLS")

    def influence_check() -> None:
        model = fit_ols()
        cooks = OLSInfluence(model).cooks_distance[0]
        record("influencia_ols", "ok", int((cooks > 4 / len(model.resid)).sum()), "WARNING" if (cooks > 4 / len(model.resid)).any() else "INFO", "observacoes com distancia de Cook elevada")

    def autocorrelation_check() -> None:
        required = {"modelo", "divisao", "fora_amostra", "valor_real", "valor_previsto", "GRUPO", "periodo"}
        if not required.issubset(predictions.columns):
            raise ValueError("predicoes requerem modelo, divisao, fora_amostra, GRUPO e periodo")
        oos = predictions[predictions["fora_amostra"].astype(bool)]
        test = oos[oos["divisao"].astype(str).eq("teste_final")]
        test = test[~test["modelo"].astype(str).str.startswith("baseline")]
        if test.empty:
            raise ValueError("nenhum modelo selecionado no teste_final")
        selected = train_frame.attrs.get("selected_model")
        model_name = str(selected) if selected else str(test.groupby("modelo").size().idxmax())
        test = test[test["modelo"].astype(str).eq(model_name)].copy()
        if test.empty:
            raise ValueError("modelo selecionado sem residuos no teste_final")
        for group, group_frame in test.groupby("GRUPO", sort=False):
            group_frame = group_frame.sort_values("periodo")
            residual = pd.to_numeric(group_frame["valor_previsto"], errors="coerce") - pd.to_numeric(group_frame["valor_real"], errors="coerce")
            residual = residual.dropna()
            if len(residual) < 2:
                record("durbin_watson", "insuficiente", np.nan, "WARNING", f"residuos OOS insuficientes no grupo {group}", group)
                record("autocorrelacao", "insuficiente", np.nan, "WARNING", f"residuos OOS insuficientes no grupo {group}", group)
                continue
            dw = float(durbin_watson(residual))
            ac = float(residual.autocorr())
            record("durbin_watson", "ok", dw, "WARNING" if dw < 1 or dw > 3 else "INFO", f"residuos OOS do modelo {model_name}, divisao teste_final, grupo {group}", group)
            record("autocorrelacao", "ok", ac, "WARNING" if abs(ac) > 0.5 else "INFO", f"residuos OOS do modelo {model_name}, divisao teste_final, grupo {group}", group)

    for name, function in (("vif", vif_check), ("correlacao", correlation_check), ("algebra", algebra_check),
                           ("residuos", residual_check), ("breusch_pagan", breusch_pagan_check),
                           ("condition_number", condition_check), ("influencia_ols", influence_check),
                           ("durbin_watson", autocorrelation_check)):
        safe(name, function)
    for name in ("outliers_residuos", "autocorrelacao"):
        if not (pd.DataFrame(rows)["diagnostico"] == name).any():
            record(name, "insuficiente", np.nan, "WARNING", "diagnostico dependente de OLS/residuos nao disponivel")
    return pd.DataFrame(rows, columns=DIAGNOSTIC_COLUMNS)


EXPLANATION_COLUMNS = ["feature", "resposta", "fonte", "campo_original", "transformacao",
                       "defasagem", "importancia", "estabilidade", "confianca", "status_importancia",
                       "status_semantico", "risco_vazamento", "texto"]


def extract_model_explanations(
    train_frame: pd.DataFrame, predictions: pd.DataFrame, response: str,
    model_name: str = "elastic_net", random_state: int = 42,
    validation_frame: pd.DataFrame | None = None,
    estimator: Pipeline | None = None,
    response_column: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return model coefficients and validation permutation rankings."""
    features, meta_by_feature, excluded = _eligible_explanation_features(train_frame, response)
    forecast_features = train_frame.attrs.get("feature_columns")
    if forecast_features:
        features = [str(feature) for feature in forecast_features if feature in train_frame.columns]
        forecast_feature_set = set(features)
        excluded = [item for item in excluded if item["feature"] not in forecast_feature_set]
    coefficients: list[dict[str, object]] = []
    target_column = response_column or response
    if not features or target_column not in train_frame:
        return pd.DataFrame(columns=EXPLANATION_COLUMNS), pd.DataFrame(columns=EXPLANATION_COLUMNS)
    fitted = estimator or build_model_pipeline(model_name, random_state)
    if estimator is None:
        fitted.fit(train_frame[features], train_frame[target_column])
    model = fitted.named_steps.get("model")
    if hasattr(model, "coef_"):
        values = np.asarray(model.coef_).ravel()
        coefficients = [{"feature": feature, "resposta": response, "fonte": meta_by_feature.get(feature, {}).get("fonte", "desconhecida"),
                         "campo_original": meta_by_feature.get(feature, {}).get("campo_original", feature),
                         "transformacao": meta_by_feature.get(feature, {}).get("transformacao", "desconhecida"),
                         "defasagem": meta_by_feature.get(feature, {}).get("defasagem", np.nan),
                         "importancia": float(value), "estabilidade": "nao_avaliada",
                         "confianca": "exploratoria", "status_importancia": "coeficiente",
                         "status_semantico": meta_by_feature.get(feature, {}).get("status_semantico", "nao_confirmado"),
                         "risco_vazamento": meta_by_feature.get(feature, {}).get("risco_vazamento", "nao_avaliado"),
                         "texto": "importancia preditiva; significado operacional confirmado" if str(meta_by_feature.get(feature, {}).get("status_semantico", "")).lower() == "confirmado" else "importancia preditiva; significado operacional nao confirmado"}
                        for feature, value in zip(features, values)]
    validation = validation_frame
    ranking_values = np.full(len(features), np.nan)
    ranking_status = "indisponivel"
    if estimator is None:
        oos_ok, oos_reason = False, "estimador final de previsao ausente"
    elif target_column != "_target":
        oos_ok, oos_reason = False, "alvo futuro _target ausente"
    elif validation is None or validation.attrs.get("forecast_test_frame") is not True:
        oos_ok, oos_reason = False, "forecast_test_frame final ausente"
    else:
        oos_ok, oos_reason = _oos_validation_status(train_frame, validation)
    if oos_ok and validation is not None and len(validation) >= 2 and target_column in validation and set(features).issubset(validation.columns):
        result = permutation_importance(fitted, validation[features], validation[target_column], n_repeats=5, random_state=random_state, scoring="neg_mean_absolute_error")
        ranking_values = result.importances_mean
        ranking_status = "oos_permutacao"
    ranking = pd.DataFrame([{**(coefficients[index] if index < len(coefficients) else {"feature": feature, "resposta": response}),
                             "fonte": meta_by_feature.get(feature, {}).get("fonte", "desconhecida"),
                             "campo_original": meta_by_feature.get(feature, {}).get("campo_original", feature),
                             "transformacao": meta_by_feature.get(feature, {}).get("transformacao", "desconhecida"),
                             "defasagem": meta_by_feature.get(feature, {}).get("defasagem", np.nan),
                             "importancia": float(value) if np.isfinite(value) else np.nan, "estabilidade": "permutacao_5x" if ranking_status == "oos_permutacao" else "nao_avaliada",
                             "confianca": "exploratoria", "status_importancia": ranking_status,
                             "status_semantico": meta_by_feature.get(feature, {}).get("status_semantico", "nao_confirmado"),
                             "risco_vazamento": meta_by_feature.get(feature, {}).get("risco_vazamento", "nao_avaliado"),
                             "texto": ("importancia preditiva; significado operacional confirmado" if str(meta_by_feature.get(feature, {}).get("status_semantico", "")).lower() == "confirmado" else "importancia preditiva; significado operacional nao confirmado") if ranking_status == "oos_permutacao" else f"importancia preditiva indisponivel: {oos_reason}; significado operacional nao confirmado"}
                             for index, (feature, value) in enumerate(zip(features, ranking_values))], columns=EXPLANATION_COLUMNS)
    coefficients_frame = pd.DataFrame(coefficients, columns=EXPLANATION_COLUMNS)
    ranking = ranking.sort_values("importancia", ascending=False).reset_index(drop=True)
    for output in (coefficients_frame, ranking):
        output.attrs["feature_exclusions"] = excluded
        output.attrs["metadata_status"] = "disponivel" if meta_by_feature else "ausente"
    return coefficients_frame, ranking


def classify_validity(
    metrics: pd.DataFrame, diagnostics: pd.DataFrame, metadata: pd.DataFrame, config: Config
) -> dict[str, str]:
    """Classify only on out-of-sample test evidence and explicit metadata."""
    result = {"classificacao": "INVALIDO", "motivo": "avaliacao fora da amostra nao confiavel"}
    if metrics.empty or "fora_amostra" not in metrics.columns:
        result["motivo"] = "fora_amostra ausente; avaliacao nao confiavel"
        return result
    if "divisao" not in metrics.columns or "modelo" not in metrics.columns:
        result["motivo"] = "divisao/modelo ausente; avaliacao nao confiavel"
        return result
    test = metrics[metrics["divisao"].astype(str).eq("teste_final") & metrics["fora_amostra"].astype(bool)]
    baseline = test[test.get("modelo", pd.Series(dtype=object)).astype(str).str.startswith("baseline")]
    models = test[~test.get("modelo", pd.Series(dtype=object)).astype(str).str.startswith("baseline")]
    if models.empty or baseline.empty:
        return result
    observed_test_rows: int | None = None
    for count_column in ("test_rows", "observacoes_teste"):
        if count_column in models.columns:
            counts = pd.to_numeric(models[count_column], errors="coerce").dropna()
            if not counts.empty:
                observed_test_rows = int(counts.max())
                break
    if observed_test_rows is None and "valor_real" in models.columns:
        observed_test_rows = len(models)
    if observed_test_rows is not None and observed_test_rows < config.min_test_rows:
        result["motivo"] = f"amostra OOS/teste insuficiente: {observed_test_rows} < min_test_rows {config.min_test_rows}"
        return result
    model = models.sort_values("mae").iloc[0]
    base_mae = pd.to_numeric(baseline["mae"], errors="coerce").min()
    mae = float(model["mae"]) if pd.notna(model["mae"]) else np.nan
    if not np.isfinite(mae) or not np.isfinite(base_mae) or mae >= base_mae * (1 - config.min_baseline_improvement):
        result["motivo"] = "modelo nao supera baseline no teste"
        return result
    violations: list[str] = []
    for field, threshold, comparator in (("r2", config.min_test_r2, lambda value, limit: value < limit),
                                         ("mape", config.max_test_mape, lambda value, limit: value > limit)):
        if field in model.index and pd.notna(model[field]) and comparator(float(model[field]), threshold):
            violations.append(f"{field}={model[field]} viola threshold {threshold}")
    if "metric_cv" in model.index:
        cv = float(model["metric_cv"]) if pd.notna(model["metric_cv"]) else np.inf
    elif "variacao_janela" in model.index and pd.notna(model["variacao_janela"]) and mae:
        cv = abs(float(model["variacao_janela"])) / abs(mae)
    else:
        cv = np.nan
    if np.isfinite(cv) and cv > config.max_metric_cv:
        violations.append(f"metric_cv={cv} viola threshold {config.max_metric_cv}")
    vif_rows = diagnostics[diagnostics.get("diagnostico", pd.Series(dtype=object)).eq("vif")] if not diagnostics.empty and "diagnostico" in diagnostics else pd.DataFrame()
    if not vif_rows.empty and pd.to_numeric(vif_rows["valor"], errors="coerce").max() > config.max_vif:
        violations.append(f"vif viola threshold {config.max_vif}")
    if violations:
        result["motivo"] = "thresholds violados: " + "; ".join(violations)
        return result
    if "leakage" in metadata.columns and metadata["leakage"].astype(bool).any() or "risco_vazamento" in metadata.columns and metadata["risco_vazamento"].astype(str).str.lower().isin({"alto", "confirmado"}).any():
        result["motivo"] = "risco de vazamento"
        return result
    if not diagnostics.empty and diagnostics.get("status", pd.Series(dtype=object)).astype(str).eq("insuficiente").any():
        result["motivo"] = "amostra insuficiente para teste confiavel"
        return result
    severe = diagnostics.get("gravidade", pd.Series(dtype=object)).astype(str).isin({"ERROR", "CRITICAL"})
    if severe.any():
        result["motivo"] = "diagnostico grave"
        return result
    unconfirmed = "status_semantico" in metadata.columns and metadata["status_semantico"].astype(str).str.lower().ne("confirmado").any()
    warning = diagnostics.get("gravidade", pd.Series(dtype=object)).astype(str).eq("WARNING").any()
    if unconfirmed:
        return {"classificacao": "DESCOBERTA_EXPLORATORIA", "motivo": "previsao mensuravel; semantica nao confirmada"}
    if warning:
        return {"classificacao": "PARCIALMENTE_VALIDO", "motivo": "instabilidade, amostra pequena ou diagnostico de atencao"}
    return {"classificacao": "VALIDO", "motivo": "superacao consistente no teste e mapeamentos confirmados"}


def _configure_logging(output_dir: Path) -> logging.Logger:
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


def _write_quality_reports(audit: pd.DataFrame, output_dir: Path) -> None:
    """Persist the canonical audit under both names used by the pipeline."""
    for filename in ("auditoria_qualidade.csv", "relatorio_qualidade_dados.csv"):
        audit.to_csv(output_dir / filename, index=False, encoding="utf-8-sig")


RESULT_TABLE_FILES = {
    "audit": "relatorio_qualidade_dados.csv",
    "base_analitica": "base_analitica.csv",
    "metricas": "metricas_modelos.csv",
    "previsoes": "previsoes_fora_amostra.csv",
    "coeficientes": "coeficientes_elastic_net.csv",
    "importancia": "importancia_variaveis.csv",
    "ranking": "ranking_dados_recomendados.csv",
    "features_excluidas": "features_excluidas.csv",
    "cobertura_temporal": "cobertura_temporal_validacao.csv",
    "mapeamento_features": "mapeamento_features.csv",
    "diagnosticos": "diagnosticos_estatisticos.csv",
    "classificacao": "classificacao_validade.csv",
}


def _as_frame(value: object, columns: Sequence[str] = ()) -> pd.DataFrame:
    """Convert optional result values to a stable, serializable frame."""
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return pd.DataFrame(list(value), columns=list(columns) if columns else None)
    return pd.DataFrame(columns=list(columns))


def _periods_as_text(periods: object) -> str:
    """Serialize validation periods so coverage decisions are auditable in CSV."""
    if periods is None:
        return ""
    if isinstance(periods, (str, bytes)):
        return str(periods)
    try:
        return ",".join(str(period) for period in periods)
    except TypeError:
        return str(periods)


def _temporal_validation_audit(
    response: str, metadata: Mapping[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Make per-response coverage and predictor exclusions serializable."""
    coverage = metadata.get("coverage_audit", {})
    coverage_row = pd.DataFrame([{
        "resposta": response,
        "min_feature_non_null": coverage.get("min_feature_non_null"),
        "dropped_rows_without_operational_coverage": coverage.get(
            "dropped_rows_without_operational_coverage", 0
        ),
        "dropped_source_periods": _periods_as_text(
            coverage.get("dropped_source_periods", ())
        ),
        "dropped_target_periods": _periods_as_text(
            metadata.get("dropped_periods", coverage.get("dropped_target_periods", ()))
        ),
    }])
    exclusions = _as_frame(metadata.get("excluded_features"))
    if exclusions.empty:
        return coverage_row, exclusions
    exclusions = exclusions.copy()
    exclusions["resposta"] = response
    exclusions["origem_exclusao"] = "validacao_temporal"
    if "campo_original" not in exclusions.columns:
        exclusions["campo_original"] = exclusions.get("feature", pd.Series(index=exclusions.index, dtype=object))
    return coverage_row, exclusions


def save_results(results: Mapping[str, Any], output_dir: Path) -> None:
    """Persist canonical result tables after a completed model run.

    Audit-only executions intentionally persist only their quality reports and
    audit table, so an empty ML table cannot be mistaken for model evidence.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = _as_frame(results.get("audit"))
    audit.to_csv(output_dir / "auditoria_qualidade.csv", index=False, encoding="utf-8-sig")
    if results.get("status") == "audit_only":
        return
    for key, filename in RESULT_TABLE_FILES.items():
        frame = _as_frame(results.get(key))
        frame.to_csv(output_dir / filename, index=False, encoding="utf-8-sig")


def _plot_slug(value: object) -> str:
    return "".join(character.lower() if str(character).isalnum() else "_" for character in str(value)).strip("_")


def _save_plot(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()
    return path


def generate_plots(results: Mapping[str, Any], output_dir: Path) -> list[Path]:
    """Generate response-level OOS plots and provenance-aware explanation plots."""
    plot_dir = output_dir / "graficos"
    predictions = _as_frame(results.get("previsoes"))
    if predictions.empty or "resposta" not in predictions.columns:
        return []
    predictions = predictions[predictions.get("fora_amostra", pd.Series(True, index=predictions.index)).astype(bool)]
    paths: list[Path] = []
    ranking = _as_frame(results.get("ranking"))
    coefficients = _as_frame(results.get("coeficientes"))
    metrics = _as_frame(results.get("metricas"))
    for response, response_predictions in predictions.groupby("resposta", sort=True):
        slug = _plot_slug(response)
        response_predictions = response_predictions.copy()
        response_predictions["periodo"] = response_predictions.get("periodo", pd.RangeIndex(len(response_predictions)))
        for model, model_predictions in response_predictions.groupby("modelo", sort=True):
            model_slug = _plot_slug(model)
            ordered = model_predictions.sort_values("periodo")
            figure, axis = plt.subplots()
            axis.plot(ordered["periodo"].astype(str), ordered["valor_real"], marker="o", label="real")
            axis.plot(ordered["periodo"].astype(str), ordered["valor_previsto"], marker="o", label="previsto")
            axis.set(title=f"Serie real e prevista: {response} / {model}", xlabel="periodo", ylabel=response)
            axis.legend()
            paths.append(_save_plot(plot_dir / f"serie_real_prevista_{slug}_{model_slug}.png"))

            figure, axis = plt.subplots()
            axis.scatter(ordered["valor_real"], ordered["valor_previsto"])
            values = pd.concat([ordered["valor_real"], ordered["valor_previsto"]]).dropna()
            if not values.empty:
                axis.plot([values.min(), values.max()], [values.min(), values.max()], linestyle="--", color="black")
            axis.set(title=f"Dispersao y=x: {response} / {model}", xlabel="real", ylabel="previsto")
            paths.append(_save_plot(plot_dir / f"dispersao_yx_{slug}_{model_slug}.png"))

            figure, axis = plt.subplots()
            axis.axhline(0, color="black", linewidth=0.8)
            axis.plot(ordered["periodo"].astype(str), ordered["erro"], marker="o")
            axis.set(title=f"Residuos temporais: {response} / {model}", xlabel="periodo", ylabel="erro")
            paths.append(_save_plot(plot_dir / f"residuos_temporais_{slug}_{model_slug}.png"))

            figure, axis = plt.subplots()
            axis.hist(pd.to_numeric(ordered["erro"], errors="coerce").dropna(), bins=min(10, max(3, len(ordered))))
            axis.set(title=f"Distribuicao de erros: {response} / {model}", xlabel="erro", ylabel="frequencia")
            paths.append(_save_plot(plot_dir / f"distribuicao_erros_{slug}_{model_slug}.png"))

        for frame, value_key, label, prefix in (
            (ranking, "importancia", "importancia", "importancia"),
            (coefficients, "importancia", "coeficiente", "coeficientes"),
        ):
            selected = frame[frame.get("resposta", pd.Series(dtype=object)).eq(response)] if not frame.empty and "resposta" in frame else pd.DataFrame()
            if selected.empty or value_key not in selected.columns:
                continue
            selected = selected.sort_values(value_key).tail(15)
            figure, axis = plt.subplots(figsize=(8, 5))
            axis.barh(selected["feature"].astype(str), pd.to_numeric(selected[value_key], errors="coerce"))
            axis.set(title=f"{label.capitalize()}: {response}", xlabel=label)
            paths.append(_save_plot(plot_dir / f"{prefix}_{slug}.png"))

        comparison = metrics[metrics.get("resposta", pd.Series(dtype=object)).eq(response)] if not metrics.empty and "resposta" in metrics else pd.DataFrame()
        if not comparison.empty and {"modelo", "mae"}.issubset(comparison.columns):
            comparison = comparison[comparison.get("divisao", "teste_final").astype(str).eq("teste_final")]
            figure, axis = plt.subplots()
            axis.bar(comparison["modelo"].astype(str), pd.to_numeric(comparison["mae"], errors="coerce"))
            axis.set(title=f"Comparacao modelos e baseline: {response}", ylabel="MAE")
            paths.append(_save_plot(plot_dir / f"comparacao_modelos_baseline_{slug}.png"))
    return paths


def write_final_report(results: Mapping[str, Any], output_dir: Path) -> Path:
    """Write a factual text report, omitting unavailable numeric evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "relatorio_final.txt"
    lines = ["RELATORIO FINAL DE VALIDACAO", "", f"status: {results.get('status', 'desconhecido')}"]
    if results.get("motivo"):
        lines.append(f"motivo: {results['motivo']}")
    if results.get("status") == "audit_only":
        lines.extend([
            "", "Execucao interrompida antes do treinamento.",
            "Modelo vencedor: indisponivel.",
            "Nenhum resultado numerico de modelo foi produzido.",
            "Limitacao: corrija a auditoria; sem --group-map-file, GRUPO e derivado do TPLNR validado.",
        ])
    else:
        metrics = _as_frame(results.get("metricas"))
        classifications = _as_frame(results.get("classificacao"))
        predictions = _as_frame(results.get("previsoes"))
        importance = _as_frame(results.get("importancia"))
        lines.extend(["", "Resultados por resposta:"])
        responses = sorted(set(metrics.get("resposta", pd.Series(dtype=object)).dropna().astype(str)))
        for response in responses:
            lines.append(f"- resposta: {response}")
            response_metrics = metrics[(metrics["resposta"].astype(str) == response) & metrics.get("divisao", "").astype(str).eq("teste_final")]
            if not response_metrics.empty:
                model_rows = response_metrics[~response_metrics["modelo"].astype(str).str.startswith("baseline")]
                if not model_rows.empty:
                    winner = model_rows.sort_values("mae", na_position="last").iloc[0]
                    if pd.notna(winner.get("mae")):
                        lines.append(f"  modelo vencedor: {winner['modelo']}; MAE teste: {winner['mae']}")
                baseline = response_metrics[response_metrics["modelo"].astype(str).str.startswith("baseline")]
                if not baseline.empty and pd.notna(baseline.iloc[0].get("mae")):
                    lines.append(f"  baseline MAE teste: {baseline.iloc[0]['mae']}")
            if not predictions.empty and "resposta" in predictions:
                observed = predictions[predictions["resposta"].astype(str).eq(response)]
                lines.append(f"  previsoes OOS observadas: {len(observed)}")
            classification = classifications[classifications.get("resposta", pd.Series(dtype=object)).astype(str).eq(response)] if not classifications.empty and "resposta" in classifications else pd.DataFrame()
            if not classification.empty:
                lines.append(f"  classificacao: {classification.iloc[0].get('classificacao', 'indisponivel')}")
        lines.extend([
            "", "Importância preditiva:",
            "A importância preditiva indica quanto uma variável contribuiu para a previsão; não estabelece relação de causa e efeito com a resposta.",
            "Somente features com status_semantico=confirmado têm significado operacional confirmado.",
        ])
        if importance.empty:
            lines.append("Nenhuma importância preditiva foi disponibilizada.")
        else:
            for _, item in importance.iterrows():
                feature = item.get("feature", "desconhecida")
                status = str(item.get("status_semantico", "nao_confirmado")).lower()
                if status != "confirmado":
                    raw_field = item.get("campo_original", feature)
                    transformation = item.get("transformacao", "nao informada")
                    lines.append(
                        f"- variável {feature} contribuiu para a previsão; campo bruto: {raw_field}; "
                        f"transformação: {transformation}; significado operacional não confirmado."
                    )
        lines.append("Limitacoes: consulte features_excluidas.csv, diagnosticos_estatisticos.csv e o status_semantico das features.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _indicator_analysis_frame(indicators: pd.DataFrame) -> pd.DataFrame:
    """Normalize indicator grain and expose its response columns as MES rows."""
    frame = indicators.copy()
    month = _month_column(frame)
    if month is None:
        raise DataValidationError("Indicadores requerem uma coluna mensal")
    frame["MES"] = _parse_month_column(frame, month)
    return frame.loc[frame["MES"].notna()].copy()


def main(argv: Sequence[str] | None = None) -> int:
    """Run audit, group mapping, temporal modeling, persistence and reporting."""
    config = parse_args(argv)
    logger = _configure_logging(config.output_dir)
    results: dict[str, Any] = {"status": "failed", "audit": pd.DataFrame(columns=AUDIT_COLUMNS)}
    try:
        indicators = load_indicator_files(config.input_dir)
        operational = load_operational_files(config.input_dir)
        normalized_indicators = {
            source: normalize_indicator_frame(frame, source)
            for source, frame in indicators.items()
        }
        sources = {**normalized_indicators, **operational}
        audit = audit_data_quality(sources)
        audit_path = config.output_dir / "auditoria_qualidade.csv"
        _write_quality_reports(audit, config.output_dir)
        results["audit"] = audit
        errors = int((audit["severidade"] == "ERROR").sum())
        logger.info(
            "Fontes carregadas: %d indicadores e %d operacionais; auditoria: %d registros, %d erros",
            len(indicators), len(operational), len(audit), errors,
        )
        if errors:
            logger.error("Auditoria estrutural encontrou %d erros; verifique %s", errors, audit_path)
            results.update(status="audit_only", motivo=f"auditoria estrutural encontrou {errors} erro(s)")
            save_results(results, config.output_dir)
            write_final_report(results, config.output_dir)
            return 1
        try:
            combined_indicators = pd.concat(normalized_indicators.values(), ignore_index=True)
            if config.group_map_file is not None:
                mapped_indicators, mapped_operational = build_group_mapping(
                    combined_indicators, operational, config.group_map_file
                )
            else:
                mapped_indicators, mapped_operational = build_hierarchy_group_mapping(
                    combined_indicators, operational
                )
        except DataValidationError as exc:
            hierarchy_mapping = config.group_map_file is None
            correction = getattr(exc, "correction", "")
            if hierarchy_mapping and not correction:
                correction = "forneca TPLNR preenchido, com GRUPO e EQUIPAMENTO nos dois segmentos finais"
            mapping_diagnostic = pd.DataFrame(
                [{
                    "fonte": "hierarquia_tplnr" if hierarchy_mapping else "mapeamento",
                    "categoria": "semantica",
                    "campo": "TPLNR" if hierarchy_mapping else "GRUPO",
                    "valor": correction,
                    "severidade": "ERROR",
                    "mensagem": str(exc),
                }],
                columns=AUDIT_COLUMNS,
            )
            audit = pd.concat([audit, mapping_diagnostic], ignore_index=True)
            _write_quality_reports(audit, config.output_dir)
            results.update(audit=audit, status="audit_only", motivo=str(exc))
            save_results(results, config.output_dir)
            write_final_report(results, config.output_dir)
            logger.error("Mapeamento de grupo interrompe o pipeline: %s", exc)
            return 1
        analysis_indicators = _indicator_analysis_frame(mapped_indicators)
        features, feature_metadata, excluded = build_operational_features(
            mapped_operational, {"reference_frame": analysis_indicators}
        )
        feature_columns = [column for column in features.columns if column not in {"GRUPO", "MES"}]
        lagged, lag_metadata = create_lag_features(
            features, feature_columns, config.max_lag,
            response_columns=[column for column in analysis_indicators.columns if column not in {"GRUPO", "MES", "EQUIPAMENTO"}],
        )
        analytic = analysis_indicators.merge(lagged, on=["GRUPO", "MES"], how="left", validate="one_to_one")
        analytic.attrs["feature_metadata"] = lag_metadata
        metric_frames: list[pd.DataFrame] = []
        prediction_frames: list[pd.DataFrame] = []
        diagnostic_frames: list[pd.DataFrame] = []
        coefficient_frames: list[pd.DataFrame] = []
        ranking_frames: list[pd.DataFrame] = []
        coverage_frames: list[pd.DataFrame] = []
        temporal_exclusion_frames: list[pd.DataFrame] = []
        classification_rows: list[dict[str, object]] = []
        response_columns = [
            column for column in analysis_indicators.columns
            if _column_key(column) in {"DFREAL", "MTBFREAL", "MTBSREAL", "MTTR", "NICVMINA"}
        ]
        for response in response_columns:
            try:
                predictions, _, metadata = run_temporal_validation(
                    analytic,
                    response,
                    config,
                    predictor_columns=lag_metadata["feature"].tolist(),
                )
                coverage_frame, temporal_exclusions = _temporal_validation_audit(response, metadata)
                coverage_frames.append(coverage_frame)
                if not temporal_exclusions.empty:
                    temporal_exclusion_frames.append(temporal_exclusions)
                response_metrics = pd.DataFrame(metadata.get("metricas", []))
                if not response_metrics.empty:
                    metric_frames.append(response_metrics)
                if not predictions.empty:
                    prediction_frames.append(predictions)
                diagnostic = run_statistical_diagnostics(analytic, predictions, response)
                diagnostic["resposta"] = response
                diagnostic_frames.append(diagnostic)
                test_periods = set(metadata.get("test_target_periods", ()))
                fallback_train_frame = analytic[~analytic["MES"].isin(test_periods)].copy() if test_periods else analytic.iloc[0:0].copy()
                fallback_validation_frame = analytic[analytic["MES"].isin(test_periods)].copy()
                train_frame = metadata.get("forecast_train_frame", fallback_train_frame)
                validation_frame = metadata.get("forecast_test_frame", fallback_validation_frame)
                final_estimators = metadata.get("final_estimators", {})
                coefficients, ranking = extract_model_explanations(
                    train_frame,
                    predictions,
                    response,
                    validation_frame=validation_frame,
                    estimator=final_estimators.get("elastic_net") if isinstance(final_estimators, Mapping) else None,
                    response_column=metadata.get("forecast_target_column"),
                    random_state=config.random_state,
                )
                coefficient_frames.append(coefficients)
                ranking_frames.append(ranking)
                classification = classify_validity(response_metrics, diagnostic, lag_metadata, config)
                classification_rows.append({"resposta": response, **classification})
            except Exception as exc:
                logger.exception("Falha na resposta %s", response)
                classification_rows.append({"resposta": response, "classificacao": "INVALIDO", "motivo": f"erro por resposta: {exc}"})
        results.update({
            "status": "completed",
            "audit": audit,
            "base_analitica": analytic,
            "metricas": pd.concat(metric_frames, ignore_index=True) if metric_frames else pd.DataFrame(),
            "previsoes": pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame(),
            "coeficientes": pd.concat(coefficient_frames, ignore_index=True) if coefficient_frames else pd.DataFrame(),
            "importancia": pd.concat(ranking_frames, ignore_index=True) if ranking_frames else pd.DataFrame(),
            "ranking": pd.concat(ranking_frames, ignore_index=True) if ranking_frames else pd.DataFrame(),
            "features_excluidas": pd.concat(
                [excluded, *temporal_exclusion_frames], ignore_index=True, sort=False
            ) if temporal_exclusion_frames else excluded,
            "cobertura_temporal": pd.concat(coverage_frames, ignore_index=True) if coverage_frames else pd.DataFrame(),
            "mapeamento_features": lag_metadata,
            "diagnosticos": pd.concat(diagnostic_frames, ignore_index=True) if diagnostic_frames else pd.DataFrame(),
            "classificacao": pd.DataFrame(classification_rows),
        })
        save_results(results, config.output_dir)
        generate_plots(results, config.output_dir)
        write_final_report(results, config.output_dir)
        return 0 if response_columns and classification_rows else 1
    except DataValidationError as exc:
        diagnostic = pd.DataFrame(
            [{
                "fonte": getattr(exc, "source", "desconhecida"),
                "categoria": "semantica" if getattr(exc, "source", "") == "mapeamento" else "fonte",
                "campo": str(getattr(exc, "path", "")),
                "valor": getattr(exc, "correction", ""),
                "severidade": "ERROR",
                "mensagem": str(exc),
            }],
            columns=AUDIT_COLUMNS,
        )
        _write_quality_reports(diagnostic, config.output_dir)
        results.update(status="audit_only", audit=diagnostic, motivo=str(exc))
        save_results(results, config.output_dir)
        write_final_report(results, config.output_dir)
        logger.error("Validacao de dados interrompida: %s", exc)
        return 1
    except Exception as exc:
        logger.exception("Pipeline interrompido por erro inesperado")
        results.update(status="failed", motivo=f"erro inesperado: {exc}")
        save_results(results, config.output_dir)
        write_final_report(results, config.output_dir)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
