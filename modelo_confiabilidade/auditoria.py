"""Auditoria estrutural e quality gate das fontes."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from .configuracao import (
    INDICATOR_FILES,
    OPERATIONAL_FILES,
    _ESSENTIAL_INDICATOR_COLUMNS,
    _INDICATOR_NUMERIC_COLUMNS,
)
from .dados import _column_key, _comparison_text, normalize_columns, parse_month_series

AUDIT_COLUMNS = ["fonte", "categoria", "campo", "valor", "severidade", "mensagem"]


def audit_data_quality(sources: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Report structural quality issues without requiring semantic mappings."""
    findings: list[dict[str, object]] = []
    periods: dict[str, set[pd.Period]] = {}

    def add(
        source: str,
        category: str,
        field: str,
        value: object,
        severity: str,
        message: str,
    ) -> None:
        findings.append({
            "fonte": source,
            "categoria": category,
            "campo": field,
            "valor": value,
            "severidade": severity,
            "mensagem": message,
        })

    required_sources = set(INDICATOR_FILES) | set(OPERATIONAL_FILES)
    for missing in sorted(required_sources - set(sources)):
        add(missing, "fonte", "", "ausente", "ERROR", "Fonte obrigatoria ausente")

    for source, frame in sources.items():
        if not isinstance(frame, pd.DataFrame):
            add(source, "fonte", "", "ausente/ilegiveis", "ERROR", "Fonte ausente ou ilegivel")
            continue
        data = normalize_columns(frame)
        add(
            source,
            "dimensao",
            "",
            f"{len(data)}x{len(data.columns)}",
            "INFO",
            "Dimensao observada",
        )
        columns_by_key = {_column_key(column): column for column in data.columns}
        recorded_coercions = set()
        for event in frame.attrs.get("data_quality_events", []):
            recorded_coercions.add(event["campo"])
            add(
                source,
                "coercao",
                event["campo"],
                event["contagem"],
                "ERROR",
                f"Valores originais invalidos: {event['amostra']}",
            )
        for column in data.columns:
            add(source, "dtype", column, str(data[column].dtype), "INFO", "Tipo estrutural observado")
            nulls = int(data[column].isna().sum())
            if nulls:
                add(source, "nulos", column, nulls, "WARNING", "Campo contem valores nulos")
            if data[column].nunique(dropna=True) <= 1 and len(data) > 1:
                add(
                    source,
                    "constante",
                    column,
                    data[column].dropna().iloc[0] if data[column].notna().any() else "",
                    "INFO",
                    "Campo constante",
                )
            key = _column_key(column)
            numeric = pd.to_numeric(
                data[column].astype("string").str.replace(",", ".", regex=False), errors="coerce"
            )
            non_empty = data[column].notna() & data[column].astype("string").str.strip().ne("")
            clearly_numeric = non_empty.any() and numeric[non_empty].notna().mean() >= 0.95
            if key in _INDICATOR_NUMERIC_COLUMNS or clearly_numeric:
                invalid_values = data.loc[non_empty & numeric.isna(), column].astype(str).tolist()
                if column not in recorded_coercions:
                    add(
                        source,
                        "coercao",
                        column,
                        len(invalid_values),
                        "WARNING" if invalid_values else "INFO",
                        f"Coercao numerica; amostra: {invalid_values[:3]}",
                    )
                if (numeric < 0).any():
                    add(
                        source,
                        "negativos",
                        column,
                        int((numeric < 0).sum()),
                        "WARNING",
                        "Valores negativos encontrados",
                    )
                if key.startswith(("DF", "UF", "RO")) and (numeric > 100).any():
                    add(
                        source,
                        "impossiveis",
                        column,
                        int((numeric > 100).sum()),
                        "ERROR",
                        "Percentual acima de 100",
                    )

        if source in INDICATOR_FILES:
            for essential in sorted(_ESSENTIAL_INDICATOR_COLUMNS - set(columns_by_key)):
                add(source, "resposta", essential, "ausente", "ERROR", "Campo essencial ausente")

        month_key = next(
            (
                key
                for key in ("ANOMES", "CALMONTH", "AMSMON", "DATA", "DATACRIACAO")
                if key in columns_by_key
            ),
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
        key_columns = [
            columns_by_key[key]
            for key in ("ANOMES", "CALMONTH", "EQUIPAMENTO", "TPLNR")
            if key in columns_by_key
        ]
        if len(key_columns) >= 2:
            duplicate_count = int(data.duplicated(key_columns, keep=False).sum())
            if duplicate_count:
                add(
                    source,
                    "duplicidade",
                    ",".join(key_columns),
                    duplicate_count,
                    "WARNING",
                    "Chaves estruturais duplicadas",
                )
        for column in data.columns:
            cardinality = data[column].nunique(dropna=True)
            if len(data) and cardinality / len(data) > 0.95 and len(data) >= 10:
                add(source, "cardinalidade", column, cardinality, "INFO", "Cardinalidade elevada")

    if len(periods) > 1:
        common = set.intersection(*periods.values())
        if not common:
            add(
                ";".join(periods),
                "intersecao_temporal",
                "",
                0,
                "ERROR",
                "Fontes nao possuem periodo temporal comum",
            )
        else:
            add(
                ";".join(periods),
                "intersecao_temporal",
                "",
                len(common),
                "INFO",
                "Periodos comuns observados",
            )
    return pd.DataFrame(findings, columns=AUDIT_COLUMNS)


def _write_quality_reports(audit: pd.DataFrame, output_dir: Path) -> None:
    """Persist the canonical audit under both names used by the pipeline."""
    for filename in ("auditoria_qualidade.csv", "relatorio_qualidade_dados.csv"):
        audit.to_csv(output_dir / filename, index=False, encoding="utf-8-sig")


write_quality_reports = _write_quality_reports

__all__ = [
    "AUDIT_COLUMNS",
    "_write_quality_reports",
    "audit_data_quality",
    "write_quality_reports",
]
