"""Normalização, mapeamento, agregação e lags das fontes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
import unicodedata
import warnings

import numpy as np
import pandas as pd

from .configuracao import (
    INDICATOR_FILES,
    OPERATIONAL_FILES,
    _INDICATOR_NUMERIC_COLUMNS,
    DataValidationError,
)

FEATURE_METADATA_COLUMNS = [
    "feature",
    "fonte",
    "campo_original",
    "transformacao",
    "mes_referencia",
    "defasagem",
    "observacoes_validas",
    "risco_vazamento",
    "status_semantico",
]


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
            error.source = source
            error.path = path
            error.correction = f"forneca o arquivo {filename} em {input_dir}"
            raise error
        try:
            if reader == "excel":
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        category=UserWarning,
                        module="openpyxl",
                    )
                    loaded[source] = pd.read_excel(path, sheet_name="Export", **kwargs)
            else:
                loaded[source] = pd.read_csv(
                    path,
                    sep=";",
                    encoding="utf-8-sig",
                    low_memory=False,
                    **kwargs,
                )
        except Exception as exc:
            detail = "aba Export" if reader == "excel" else "separador ';' e codificacao UTF-8-SIG"
            error = DataValidationError(
                f"Nao foi possivel ler {source} em {path}: {exc}. "
                f"Correcao esperada: valide o arquivo e sua {detail}."
            )
            error.source = source
            error.path = path
            error.correction = f"valide o arquivo e sua {detail}"
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
        equipment = (
            result[equipment_column]
            .astype("string")
            .str.strip()
            .str.rstrip(".")
            .str.replace(r"-CARGA$", "", regex=True)
        )
        result[equipment_column] = equipment
        result = result.loc[equipment.notna() & equipment.ne("")].copy()
    if month_column:
        result[month_column] = parse_month_series(result[month_column], month_column)
        result = result.loc[result[month_column].notna()].copy()

    coercion_events: list[dict[str, object]] = []
    for column in result.columns:
        key = _column_key(column)
        if key in {"ANOMES", "EQUIPAMENTO"}:
            continue
        raw_str = result[column].astype("string").str.replace(",", ".", regex=False)
        numeric_values = pd.to_numeric(raw_str, errors="coerce")
        non_empty = result[column].notna() & result[column].astype("string").str.strip().ne("")
        clearly_numeric = non_empty.any() and numeric_values[non_empty].notna().mean() >= 0.95
        if key in _INDICATOR_NUMERIC_COLUMNS or clearly_numeric:
            # 1. Non-numeric invalid strings
            invalid_str = non_empty & numeric_values.isna()

            # 2. Infinite values (inf, -inf) -> process error, expurgated
            inf_values = np.isinf(numeric_values)
            numeric_values = numeric_values.mask(inf_values, np.nan)

            # 3. Percentages (DF, UF, RO - both REAL and META) -> scale [0, 100]%
            is_percentage = key.startswith(("DF", "UF", "RO")) or any(
                token in key for token in ("DISPONIBILIDADE", "UTILIZACAO", "RENDIMENTO")
            )
            pct_out_of_bounds = pd.Series(False, index=result.index)
            if is_percentage:
                pct_out_of_bounds = numeric_values.notna() & ((numeric_values < 0) | (numeric_values > 100))
                numeric_values = numeric_values.mask(pct_out_of_bounds, np.nan)

            # 4. Non-negative indicator fields (MTBF, MTBS, MTTR, NIC, HT, HM, HMC, HO, HAC, MPS, MPNS) -> >= 0
            neg_invalid = pd.Series(False, index=result.index)
            if not is_percentage and any(
                token in key for token in ("MTBF", "MTBS", "MTTR", "NIC", "HT", "HM", "HMC", "HO", "HAC", "MPS", "MPNS")
            ):
                neg_invalid = numeric_values.notna() & (numeric_values < 0)
                numeric_values = numeric_values.mask(neg_invalid, np.nan)

            anomalies = invalid_str | inf_values | pct_out_of_bounds | neg_invalid
            if anomalies.any():
                invalid_samples = result.loc[anomalies, column].astype(str).tolist()
                coercion_events.append({
                    "fonte": source,
                    "campo": column,
                    "contagem": int(anomalies.sum()),
                    "amostra": [str(value) for value in invalid_samples[:3]],
                })
            result[column] = numeric_values
    result = result.reset_index(drop=True)
    result.attrs["data_quality_events"] = coercion_events
    return result


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
    """Derive the group and equipment from TPLNR segments, tolerating unassigned records."""
    if tplnr_column not in frame.columns:
        raise DataValidationError(f"Coluna TPLNR ausente: {tplnr_column}")

    values = frame[tplnr_column].astype("string").str.strip()
    non_empty = values.notna() & values.ne("")
    parts = values.str.split("-")
    valid_parts = parts.map(
        lambda value: isinstance(value, list)
        and len(value) >= 2
        and any(str(part).strip() for part in value)
    )
    valid_mask = non_empty & valid_parts
    if not valid_mask.any():
        sample = values.dropna().head(3).tolist() if len(values.dropna()) > 0 else ["<NA>"]
        raise DataValidationError(
            f"TPLNR invalido na coluna {tplnr_column}: nenhum registro valido; amostra: {sample}"
        )

    def _extract_group(p: object) -> str | None:
        if not isinstance(p, list) or len(p) < 2:
            return None
        if len(p) >= 5:
            return str(p[3]).strip()
        return str(p[-2]).strip()

    def _extract_equipment(p: object) -> str | None:
        if not isinstance(p, list) or len(p) < 2:
            return None
        if len(p) >= 5:
            return str(p[4]).strip()
        return str(p[-1]).strip()

    result = frame.copy()
    result["GRUPO"] = parts.map(_extract_group).astype("string")
    result["EQUIPAMENTO"] = parts.map(_extract_equipment).astype("string")
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

    lookup_source = (
        pd.concat(
            [
                frame[["EQUIPAMENTO", "GRUPO"]].dropna()
                for frame in derived_operational.values()
            ],
            ignore_index=True,
        )
        if derived_operational
        else pd.DataFrame(columns=["EQUIPAMENTO", "GRUPO"])
    )
    lookup_source["EQUIPAMENTO"] = lookup_source["EQUIPAMENTO"].astype("string").str.strip()
    lookup_source["GRUPO"] = lookup_source["GRUPO"].astype("string").str.strip()
    lookup_source = lookup_source[
        lookup_source["EQUIPAMENTO"].notna()
        & lookup_source["GRUPO"].notna()
        & lookup_source["EQUIPAMENTO"].ne("")
        & lookup_source["GRUPO"].ne("")
    ]

    if "EQUIPAMENTO" not in indicators.columns:
        raise DataValidationError("Indicadores requerem a coluna EQUIPAMENTO para o mapeamento")

    indicator_equipments = set(indicators["EQUIPAMENTO"].astype("string").str.strip().dropna().unique())
    norm_ind_eqs = {eq.replace("-", "").replace(".", "").upper() for eq in indicator_equipments}

    lookup_source["_EQ_NORM"] = (
        lookup_source["EQUIPAMENTO"]
        .astype("string")
        .str.replace("-", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.upper()
    )
    ind_lookup = lookup_source[lookup_source["_EQ_NORM"].isin(norm_ind_eqs)]

    counts = ind_lookup.groupby(["EQUIPAMENTO", "GRUPO"]).size().reset_index(name="count")
    counts = counts.sort_values(["EQUIPAMENTO", "count"], ascending=[True, False])

    top1 = counts.groupby("EQUIPAMENTO").nth(0)
    top2 = counts.groupby("EQUIPAMENTO").nth(1)
    tot = counts.groupby("EQUIPAMENTO")["count"].sum().reset_index(name="total")
    merged = top1.merge(top2, on="EQUIPAMENTO", suffixes=("_1", "_2"), how="inner").merge(tot, on="EQUIPAMENTO")
    ambiguous = merged[merged["count_2"] / merged["total"] >= 0.15]

    if not ambiguous.empty:
        error = DataValidationError(
            "Equipamento associado a multiplos grupos: " + ", ".join(ambiguous["EQUIPAMENTO"].astype(str))
        )
        error.correction = "resolver equipamento em um unico grupo"
        raise error

    all_counts = lookup_source.groupby(["EQUIPAMENTO", "GRUPO"]).size().reset_index(name="count")
    all_counts = all_counts.sort_values(["EQUIPAMENTO", "count"], ascending=[True, False])
    all_top1 = all_counts.groupby("EQUIPAMENTO").nth(0)
    lookup = all_top1.drop_duplicates("EQUIPAMENTO").set_index("EQUIPAMENTO")["GRUPO"]

    mapped_indicators = indicators.copy()
    mapped_indicators["EQUIPAMENTO"] = mapped_indicators["EQUIPAMENTO"].astype("string").str.strip()
    if "GRUPO" in mapped_indicators.columns:
        mapped_indicators = mapped_indicators.drop(columns=["GRUPO"])
    mapped_indicators["GRUPO"] = mapped_indicators["EQUIPAMENTO"].map(lookup)
    missing_group = (
        mapped_indicators["GRUPO"].isna()
        | mapped_indicators["GRUPO"].astype("string").str.strip().eq("")
    )
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
    frames = {
        "indicadores": _normalize_group_values(indicators, "indicadores"),
        **{name: _normalize_group_values(frame, name) for name, frame in operational.items()},
    }
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
            inconsistent = (
                existing.notna()
                & expected.notna()
                & (existing.astype("string") != expected.astype("string"))
            )
            if inconsistent.any():
                raise _mapping_error(f"GRUPO explicito inconsistente com a chave na fonte {name}")
            result["GRUPO"] = existing.where(existing.notna(), expected)
        elif "GRUPO" not in result.columns:
            if expected is None:
                raise _mapping_error(
                    f"Fonte {name} nao possui EQUIPAMENTO/TPLNR para aplicar o mapeamento"
                )
            result["GRUPO"] = expected
        if name == "indicadores" and result["GRUPO"].isna().any():
            sample = (
                result.loc[result["GRUPO"].isna(), _mapping_key(result) or "GRUPO"]
                .astype(str)
                .head(3)
                .tolist()
            )
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
        return (
            frame[month]
            if isinstance(frame[month].dtype, pd.PeriodDtype)
            else parse_month_series(frame[month], "MES")
        )
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
            group_obj = values.groupby([result["GRUPO"], result["MES"]])
            aggregations[f"{column}_sum"] = group_obj.sum()
            aggregations[f"{column}_mean"] = group_obj.mean()
            aggregations[f"{column}_median"] = group_obj.median()
            aggregations[f"{column}_min"] = group_obj.min()
            aggregations[f"{column}_max"] = group_obj.max()
            aggregations[f"{column}_count"] = group_obj.count()
            aggregations[f"{column}_nunique"] = group_obj.nunique()
        else:
            n_unique = result[column].nunique(dropna=True)
            if len(result) >= 10 and n_unique / max(len(result), 1) > 0.95:
                continue
            groups = result.groupby([result["GRUPO"], result["MES"]])[column]
            aggregations[f"{column}_count"] = groups.count()
            aggregations[f"{column}_nunique"] = groups.nunique()
            if n_unique <= 20:
                proportions = (
                    result.assign(_value=result[column].astype("string"))
                    .groupby([result["GRUPO"], result["MES"], "_value"])
                    .size()
                )
                prop_df = proportions.unstack(level="_value", fill_value=0)
                group_sizes = groups.size()
                prop_df = prop_df.reindex(group_sizes.index, fill_value=0).div(group_sizes, axis=0).fillna(0)
                for value in prop_df.columns:
                    aggregations[f"{column}_prop_{value}"] = prop_df[value]
    output = (
        pd.DataFrame(aggregations).reset_index()
        if aggregations
        else result[["GRUPO", "MES"]].drop_duplicates()
    )
    output = output.sort_values(["GRUPO", "MES"]).reset_index(drop=True)
    observed = set(result["MES"].dropna())
    output.attrs["coverage_report"] = pd.DataFrame([{
        "fonte": "desconhecida",
        "linhas_entrada": input_rows,
        "linhas_validas": len(result),
        "linhas_perdidas": input_rows - len(result),
        "meses_observados": len(observed),
        "meses_sem_cobertura": 0,
        "cardinalidade_join": len(output),
        "linhas_perdidas_join": 0,
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
        future_columns = (
            set(configured_future)
            if not isinstance(configured_future, Mapping)
            else {field for fields in configured_future.values() for field in fields}
        )
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
            reference_keys = set(
                zip(
                    reference.loc[reference["MES"].notna(), "GRUPO"],
                    reference.loc[reference["MES"].notna(), "MES"],
                )
            )
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
            structural_name = column in structural_columns or any(
                token in key
                for token in (
                    "PRIMARYKEYJOIN",
                    "AMSWEEK",
                    "AMSDAYDATE",
                    "EVENTDATE",
                    "DATACRIACAO",
                    "DATAEVENTO",
                    "DATAPREVISTA",
                    "DATAEXECUCAO",
                    "YEAR",
                    "MONTH",
                    "WEEK",
                    "DAY",
                )
            )
            if structural_name:
                source_excluded.add(column)
                excluded.append({"fonte": source, "campo_original": column, "motivo": "chave estrutural"})
        for column in frame.columns:
            key = _column_key(column)
            if column in source_excluded:
                continue
            future = column in future_columns or key in {_column_key(item) for item in future_columns}
            posterior = any(
                token in key
                for token in ("FUTURE", "POSTERIOR", "DATACONCLUSAO", "DATAREALIZACAO")
            )
            identifier = key in id_names or key.endswith("ID") or key.startswith("ID")
            numeric_high_cardinality = (
                len(frame) >= 10
                and frame[column].nunique(dropna=True) / max(len(frame), 1) > 0.95
            )
            text_high_cardinality = (
                pd.api.types.is_string_dtype(frame[column]) or frame[column].dtype == object
            ) and numeric_high_cardinality
            if future or posterior:
                source_excluded.add(column)
                excluded.append({"fonte": source, "campo_original": column, "motivo": "disponibilidade posterior"})
            elif identifier or text_high_cardinality:
                source_excluded.add(column)
                excluded.append({
                    "fonte": source,
                    "campo_original": column,
                    "motivo": "identificador/chave ou alta cardinalidade",
                })
        source_excluded -= {"GRUPO", "EQUIPAMENTO", "TPLNR", *month_parts}
        aggregate = aggregate_monthly_data(frame, source_excluded)
        report = aggregate.attrs.get("coverage_report", pd.DataFrame())
        if not report.empty:
            report = report.copy()
            report["fonte"] = source
            report["meses_observados_set"] = [aggregate.attrs.get("observed_months", set())]
            observed_keys = aggregate.attrs.get("observed_keys", set())
            report["cardinalidade_join"] = len(observed_keys)
            report["chaves_sem_correspondencia"] = (
                len(observed_keys - reference_keys) if reference_keys else 0
            )
            report["chaves_referencia_sem_fonte"] = (
                len(reference_keys - observed_keys) if reference_keys else 0
            )
            report["linhas_perdidas_join"] = report["chaves_sem_correspondencia"]
            report["operational_keys_without_indicator"] = report["chaves_sem_correspondencia"]
            report["indicator_keys_without_operational"] = report["chaves_referencia_sem_fonte"]
            report["percentual_cobertura"] = (
                len(observed_keys & reference_keys) / len(reference_keys) * 100
                if reference_keys
                else 0.0
            )
            coverage.append(report)
        aggregate = aggregate.rename(
            columns={
                column: f"{source}__{column}"
                for column in aggregate.columns
                if column not in {"GRUPO", "MES"}
            }
        )
        aggregate.attrs.clear()
        frames.append(aggregate)
        for feature in aggregate.columns:
            if feature in {"GRUPO", "MES"}:
                continue
            original = feature[len(source) + 2 :].rsplit("_", 1)[0]
            metadata.append({
                "feature": feature,
                "fonte": source,
                "campo_original": original,
                "transformacao": feature.rsplit("_", 1)[-1],
                "mes_referencia": "t",
                "defasagem": 0,
                "observacoes_validas": int(aggregate[feature].notna().sum()),
                "risco_vazamento": "baixo",
                "status_semantico": "nao_confirmado",
            })
    if not frames:
        empty = pd.DataFrame(columns=["GRUPO", "MES"])
        metadata_frame = pd.DataFrame(columns=FEATURE_METADATA_COLUMNS)
        metadata_frame.attrs["coverage_report"] = pd.DataFrame(
            columns=[
                "fonte",
                "linhas_entrada",
                "linhas_validas",
                "linhas_perdidas",
                "meses_observados",
                "meses_sem_cobertura",
                "cardinalidade_join",
                "linhas_perdidas_join",
                "taxa_cobertura",
                "chaves_sem_correspondencia",
                "chaves_referencia_sem_fonte",
                "operational_keys_without_indicator",
                "indicator_keys_without_operational",
                "percentual_cobertura",
            ]
        )
        return empty, metadata_frame, fixed_excluded
    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on=["GRUPO", "MES"], how="outer", validate="one_to_one")
    for spec in specs:
        if (
            not isinstance(spec, Mapping)
            or not spec.get("name")
            or not spec.get("source")
            or not spec.get("fields")
            or not spec.get("transform")
        ):
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
        result = result.merge(
            value.reset_index(), on=["GRUPO", "MES"], how="left", validate="one_to_one"
        )
        metadata.append({
            "feature": str(spec["name"]),
            "fonte": source,
            "campo_original": ",".join(fields),
            "transformacao": str(transform),
            "mes_referencia": "t",
            "defasagem": 0,
            "observacoes_validas": int(value.notna().sum()),
            "risco_vazamento": "baixo",
            "status_semantico": spec.get("semantic_status", "nao_confirmado"),
        })
    metadata_frame = pd.DataFrame(metadata, columns=FEATURE_METADATA_COLUMNS)
    coverage_frame = pd.concat(coverage, ignore_index=True) if coverage else pd.DataFrame()
    if not coverage_frame.empty:
        all_months = set().union(*coverage_frame["meses_observados_set"].tolist())
        coverage_frame["meses_sem_cobertura"] = coverage_frame["meses_observados_set"].map(
            lambda months: len(all_months - months)
        )
        coverage_frame = coverage_frame.drop(columns=["meses_observados_set"])
        coverage_frame["meses_sem_cobertura"] = coverage_frame["meses_sem_cobertura"].astype(int)
    metadata_frame.attrs["coverage_report"] = coverage_frame
    excluded_frame = pd.DataFrame(excluded, columns=["fonte", "campo_original", "motivo"])
    result = result.sort_values(["GRUPO", "MES"]).reset_index(drop=True)
    result.attrs["feature_metadata"] = metadata_frame
    result.attrs["coverage_report"] = coverage_frame
    return result, metadata_frame, excluded_frame


def create_lag_features(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    max_lag: int,
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
    canonical_responses = set(response_columns or ()) | {
        "DF (REAL)",
        "DF (META)",
        "MTBF (REAL)",
        "MTBF (META)",
        "MTBS (REAL)",
        "MTBS (META)",
        "MTTR",
        "MTTR (META)",
        "NIC (VMINA)",
        "NIC (META)",
        "UF (REAL)",
        "UF (META)",
        "RO (REAL)",
        "RO (META)",
    }
    response_keys = {_column_key(column) for column in canonical_responses}
    source_metadata = frame.attrs.get("feature_metadata")
    metadata_by_feature = {}
    if isinstance(source_metadata, pd.DataFrame) and "feature" in source_metadata.columns:
        metadata_by_feature = source_metadata.set_index("feature").to_dict("index")
    for feature in feature_columns:
        feature_key = _column_key(feature)
        original_key = _column_key(metadata_by_feature.get(feature, {}).get("campo_original", ""))
        if any(
            token in feature_key or token in original_key
            for token in response_keys
            if len(token) >= 4 or token in {"MTTR", "NIC"}
        ):
            raise DataValidationError(
                f"Feature {feature} e resposta ou derivada de resposta; nao pode virar lag"
            )
    result = frame.sort_values(["GRUPO", "MES"]).reset_index(drop=True).copy()
    records: list[dict[str, object]] = []
    metadata_events: list[dict[str, str]] = []
    lag_columns = {}
    for feature in feature_columns:
        if feature not in result.columns:
            raise DataValidationError(f"Feature ausente para lag: {feature}")
        if feature not in metadata_by_feature:
            metadata_events.append({
                "tipo": "metadata_ausente",
                "feature": feature,
                "mensagem": "Fonte, status semantico e risco nao foram fornecidos",
            })
        grouped = result.groupby("GRUPO", sort=False)[feature]
        for lag in range(max_lag + 1):
            name = f"{feature}_lag_{lag}"
            lag_series = grouped.shift(lag) if lag else result[feature]
            lag_columns[name] = lag_series
            original = metadata_by_feature.get(feature, {})
            records.append({
                "feature": name,
                "fonte": original.get("fonte", "desconhecida"),
                "campo_original": original.get("campo_original", feature),
                "transformacao": "shift",
                "mes_referencia": "t",
                "defasagem": lag,
                "observacoes_validas": int(lag_series.notna().sum()),
                "risco_vazamento": original.get("risco_vazamento", "nao_avaliado"),
                "status_semantico": original.get("status_semantico", "nao_confirmado"),
            })
    if lag_columns:
        result = pd.concat([result, pd.DataFrame(lag_columns, index=result.index)], axis=1)
    if "resposta" in result.columns:
        result["resposta_t1"] = result.groupby("GRUPO", sort=False)["resposta"].shift(-1)
    metadata = pd.DataFrame(records, columns=FEATURE_METADATA_COLUMNS)
    metadata.attrs["events"] = pd.DataFrame(
        metadata_events, columns=["tipo", "feature", "mensagem"]
    )
    metadata.attrs["coverage_report"] = (
        source_metadata.attrs.get("coverage_report", pd.DataFrame())
        if isinstance(source_metadata, pd.DataFrame)
        else pd.DataFrame()
    )
    return result, metadata


def _indicator_analysis_frame(indicators: pd.DataFrame) -> pd.DataFrame:
    """Normalize indicator grain and expose its response columns as MES rows."""
    frame = indicators.copy()
    month = _month_column(frame)
    if month is None:
        raise DataValidationError("Indicadores requerem uma coluna mensal")
    frame["MES"] = _parse_month_column(frame, month)
    return frame.loc[frame["MES"].notna()].copy()


__all__ = [
    "FEATURE_METADATA_COLUMNS",
    "_column_key",
    "_comparison_text",
    "_indicator_analysis_frame",
    "_mapping_error",
    "_mapping_key",
    "_month_column",
    "_normalize_group_values",
    "_parse_month_column",
    "_read_required",
    "aggregate_monthly_data",
    "build_group_mapping",
    "build_hierarchy_group_mapping",
    "build_operational_features",
    "create_lag_features",
    "derive_tplnr_hierarchy",
    "load_indicator_files",
    "load_operational_files",
    "normalize_columns",
    "normalize_indicator_frame",
    "parse_month_series",
]
