"""Contract tests for the Task 1 interfaces."""

from pathlib import Path
import logging
import subprocess
import sys
from typing import Mapping

import numpy as np
import pandas as pd
import pytest

from modelo_confiabilidade.__main__ import main
from modelo_confiabilidade.auditoria import audit_data_quality
from modelo_confiabilidade.configuracao import (
    Config,
    DataValidationError,
    INDICATOR_FILES,
    OPERATIONAL_FILES,
    _configure_logging,
    load_indicator_files,
    load_operational_files,
    parse_args,
)
from modelo_confiabilidade.dados import (
    _month_column,
    aggregate_monthly_data,
    build_group_mapping,
    build_hierarchy_group_mapping,
    build_operational_features,
    create_lag_features,
    derive_tplnr_hierarchy,
    normalize_columns,
    normalize_indicator_frame,
    parse_month_series,
)
from modelo_confiabilidade.diagnosticos import (
    classify_validity,
    extract_model_explanations,
    run_statistical_diagnostics,
)
from modelo_confiabilidade.modelagem import (
    build_model_pipeline,
    calculate_regression_metrics,
    run_temporal_validation,
)
from modelo_confiabilidade.relatorios import (
    generate_plots,
    save_results,
    write_final_report,
)


@pytest.fixture
def small_source_dir(tmp_path: Path) -> Path:
    """Create all nine source files with one small, distinguishable row."""
    indicator = pd.DataFrame(
        {
            "ANO MÊS": ["202501"],
            "EQUIPAMENTO": ["EQ-1"],
            "GRUPO": ["grupo-1"],
            "DF (REAL)": [1],
            "MTBF (REAL)": [2],
            "MTBS (REAL)": [3],
            "MTTR": [4],
            "NIC (VMINA)": [5],
        }
    )
    for filename in INDICATOR_FILES.values():
        with pd.ExcelWriter(tmp_path / filename) as writer:
            indicator.to_excel(writer, sheet_name="Export", index=False)
            pd.DataFrame({"wrong": ["not selected"]}).to_excel(
                writer, sheet_name="Other", index=False
            )

    operational = pd.DataFrame(
        {"DESCRIÇÃO": ["ação"], "valor": [1], "YEAR": [2025], "CALMONTH": [202501], "GRUPO": ["grupo-1"]}
    )
    for filename in OPERATIONAL_FILES.values():
        operational.to_csv(tmp_path / filename, sep=";", encoding="utf-8-sig", index=False)
    return tmp_path


def test_parse_args_defaults_and_values(tmp_path: Path) -> None:
    """CLI values are converted to their typed configuration fields."""
    config = parse_args(
        [
            "--input-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--test-months",
            "3",
            "--max-lag",
            "6",
            "--random-state",
            "7",
        ]
    )

    assert config.test_months == 3
    assert config.max_lag == 6
    assert config.random_state == 7
    assert config.input_dir == tmp_path
    assert config.output_dir == tmp_path / "out"


def test_parse_args_rejects_non_positive_integer() -> None:
    """Positive-only numeric CLI options reject zero and negative values."""
    with pytest.raises(SystemExit):
        parse_args(["--test-months", "0"])


def test_package_cli_help_lists_required_options() -> None:
    """The package entrypoint exposes the documented command-line contract."""
    result = subprocess.run(
        [sys.executable, "-m", "modelo_confiabilidade", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    for option in ("--input-dir", "--output-dir", "--test-months", "--max-lag", "--group-map-file"):
        assert option in result.stdout


def test_data_and_audit_functions_have_new_owners() -> None:
    """Data loading and structural auditing are exposed by their modules."""
    from modelo_confiabilidade.auditoria import audit_data_quality as owned_audit
    from modelo_confiabilidade.dados import (
        create_lag_features as owned_lags,
        load_indicator_files as owned_loader,
    )

    assert callable(owned_loader)
    assert callable(owned_lags)
    assert callable(owned_audit)


def test_modeling_and_diagnostics_have_new_owners() -> None:
    """Modeling and diagnostics are exposed by their focused modules."""
    from modelo_confiabilidade.diagnosticos import classify_validity as owned_classification
    from modelo_confiabilidade.modelagem import run_temporal_validation as owned_validation

    assert callable(owned_validation)
    assert callable(owned_classification)


def test_reports_are_owned_by_reports_module(tmp_path: Path) -> None:
    """Report persistence is exposed by the reports module."""
    from modelo_confiabilidade.relatorios import save_results as owned_save_results

    owned_save_results({"metricas_modelos": pd.DataFrame({"x": [1]})}, tmp_path)

    assert (tmp_path / "metricas_modelos.csv").exists()


def test_missing_required_source_is_reported(tmp_path: Path) -> None:
    """Missing indicator files produce an actionable validation error."""
    with pytest.raises(DataValidationError, match="INDICADORES MENSAIS"):
        load_indicator_files(tmp_path)


def test_missing_operational_source_is_reported(tmp_path: Path) -> None:
    """Missing operational files identify the expected source and path."""
    with pytest.raises(DataValidationError, match="AMS_Contador"):
        load_operational_files(tmp_path)


def test_file_constants_cover_the_four_xlsx_and_five_csv_sources() -> None:
    """The loader contract names every source explicitly."""
    assert len(INDICATOR_FILES) == 4
    assert len(OPERATIONAL_FILES) == 5
    assert all(name.endswith(".xlsx") for name in INDICATOR_FILES.values())
    assert all(name.endswith(".csv") for name in OPERATIONAL_FILES.values())


def test_indicator_loader_reads_export_sheet(small_source_dir: Path) -> None:
    """Indicator loading selects the required Export worksheet."""
    loaded = load_indicator_files(small_source_dir)

    assert set(loaded) == set(INDICATOR_FILES)
    assert loaded["caminhao"].loc[0, "EQUIPAMENTO"] == "EQ-1"
    assert "wrong" not in loaded["caminhao"].columns


def test_operational_loader_reads_semicolon_and_utf8_bom(small_source_dir: Path) -> None:
    """Operational loading decodes the documented delimiter and BOM."""
    loaded = load_operational_files(small_source_dir)

    assert set(loaded) == set(OPERATIONAL_FILES)
    assert loaded["AMS_Contador"].loc[0, "DESCRIÇÃO"] == "ação"
    assert list(loaded["AMS_Contador"].columns) == ["DESCRIÇÃO", "valor", "YEAR", "CALMONTH", "GRUPO"]


def test_unreadable_source_has_path_and_correction(tmp_path: Path) -> None:
    """Unreadable files report both the concrete path and expected correction."""
    path = tmp_path / INDICATOR_FILES["caminhao"]
    path.write_bytes(b"not an xlsx")

    with pytest.raises(DataValidationError) as error:
        load_indicator_files(tmp_path)

    message = str(error.value)
    assert str(path) in message
    assert "Correcao esperada" in message
    assert "Export" in message


def test_main_writes_log_file_and_replaces_handlers_safely(tmp_path: Path) -> None:
    """Repeated CLI failures keep the file log usable and bounded to two handlers."""
    output_dir = tmp_path / "out"
    arguments = ["--input-dir", str(tmp_path / "missing"), "--output-dir", str(output_dir)]

    assert main(arguments) == 1
    assert main(arguments) == 1

    log_path = output_dir / "validar_modelo.log"
    assert log_path.is_file()
    assert "Validacao de dados interrompida" in log_path.read_text(encoding="utf-8")


def test_logging_closes_previous_file_handler(tmp_path: Path) -> None:
    """Replacing logger handlers closes the previous file descriptor."""
    logger = _configure_logging(tmp_path / "out")
    previous_file_handler = next(
        handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)
    )

    _configure_logging(tmp_path / "out")

    assert previous_file_handler.stream is None


def test_normalize_columns_removes_outer_spaces_and_bom() -> None:
    frame = pd.DataFrame({"\ufeff ANO MÊS ": ["202501"], " EQUIPAMENTO ": ["A"]})

    result = normalize_columns(frame)

    assert list(result.columns) == ["ANO MÊS", "EQUIPAMENTO"]


def test_parse_month_series_returns_period_month() -> None:
    result = parse_month_series(pd.Series(["202501", "2025-02"]), "ANO MES")

    assert result.astype(str).tolist() == ["2025-01", "2025-02"]


def test_parse_month_series_marks_invalid_values_as_nat() -> None:
    result = parse_month_series(pd.Series(["202513", "not-a-month"]), "ANO MES")

    assert result.isna().all()


def test_normalize_indicator_frame_removes_structural_rows_and_coerces_values() -> None:
    frame = pd.DataFrame(
        {
            " ANO MÊS ": ["202501", "", "202502", "202503"],
            " EQUIPAMENTO ": ["A", "TOTAL", "Filtro aplicado", None],
            " DF (REAL) ": ["1,5", "2", "3", "erro"],
        }
    )
    result = normalize_indicator_frame(frame, "caminhao")

    assert result["EQUIPAMENTO"].tolist() == ["A"]
    assert result["ANO MÊS"].astype(str).tolist() == ["2025-01"]
    assert result["DF (REAL)"].tolist() == [1.5]


def test_normalize_indicator_frame_keeps_operational_text_columns() -> None:
    frame = pd.DataFrame({"EQUIPAMENTO": ["A"], "DESCRIÇÃO": ["123 texto"]})

    result = normalize_indicator_frame(frame, "caminhao")

    assert result["DESCRIÇÃO"].tolist() == ["123 texto"]
    assert result["DESCRIÇÃO"].dtype == object


def test_normalize_indicator_frame_preserves_invalid_coercion_event() -> None:
    frame = pd.DataFrame(
        {"ANO MÊS": ["202501"], "EQUIPAMENTO": ["A"], "DF (REAL)": ["erro"]}
    )

    result = normalize_indicator_frame(frame, "caminhao")

    assert pd.isna(result.loc[0, "DF (REAL)"])
    assert result.attrs["data_quality_events"] == [
        {
            "fonte": "caminhao",
            "campo": "DF (REAL)",
            "contagem": 1,
            "amostra": ["erro"],
        }
    ]


def test_audit_data_quality_reports_structural_findings_without_semantic_schema() -> None:
    sources: Mapping[str, pd.DataFrame] = {
        "sample": pd.DataFrame(
            {
                "ANO MES": ["202501", "202501", "202513"],
                "EQUIPAMENTO": ["A", "A", None],
                "valor": [1, -2, None],
            }
        )
    }

    result = audit_data_quality(sources)

    assert list(result.columns) == ["fonte", "categoria", "campo", "valor", "severidade", "mensagem"]
    assert {"duplicidade", "periodo", "nulos", "negativos"}.issubset(set(result["categoria"]))
    assert set(result["severidade"]).issubset({"INFO", "WARNING", "ERROR"})


def test_audit_data_quality_reports_missing_source_as_error() -> None:
    result = audit_data_quality({"missing": None})

    assert ((result["fonte"] == "missing") & (result["severidade"] == "ERROR")).any()


def test_audit_unknown_source_still_reports_required_sources_as_errors() -> None:
    result = audit_data_quality({"unknown": pd.DataFrame({"valor": [1]})})

    assert set(INDICATOR_FILES).issubset(set(result.loc[result["severidade"] == "ERROR", "fonte"]))


def test_audit_reports_dtypes_coercions_missing_responses_and_missing_period() -> None:
    result = audit_data_quality(
        {
            "caminhao": pd.DataFrame(
                {"ANO MÊS": ["202501", "invalid"], "EQUIPAMENTO": ["A", "B"], "DF (REAL)": ["1", "bad"]}
            ),
            "unknown": pd.DataFrame({"valor": ["x"]}),
        }
    )

    categories = set(result["categoria"])
    assert {"dtype", "coercao", "resposta", "periodo"}.issubset(categories)
    assert ((result["categoria"] == "coercao") & result["mensagem"].str.contains("bad")).any()
    assert ((result["fonte"] == "unknown") & (result["categoria"] == "periodo") & (result["severidade"] == "ERROR")).any()


def test_audit_does_not_treat_aufnr_as_percentage() -> None:
    result = audit_data_quality(
        {"AMS_Contador": pd.DataFrame({"CALMONTH": [202501], "AUFNR": [123456]})}
    )

    assert not ((result["campo"] == "AUFNR") & (result["categoria"] == "impossiveis")).any()


def test_main_runs_quality_gate_and_writes_audit(small_source_dir: Path) -> None:
    output_dir = small_source_dir / "out"

    assert main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)]) != 0
    audit_path = output_dir / "auditoria_qualidade.csv"
    assert audit_path.is_file()
    assert {"fonte", "categoria", "severidade"}.issubset(
        pd.read_csv(audit_path).columns
    )


def test_main_persists_invalid_coercion_event(small_source_dir: Path) -> None:
    path = small_source_dir / INDICATOR_FILES["caminhao"]
    frame = pd.read_excel(path, sheet_name="Export")
    frame["DF (REAL)"] = frame["DF (REAL)"].astype(object)
    frame.loc[0, "DF (REAL)"] = "erro"
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, sheet_name="Export", index=False)

    output_dir = small_source_dir / "out-invalid"

    assert main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)]) == 1
    audit = pd.read_csv(output_dir / "auditoria_qualidade.csv")
    coercions = audit[(audit["fonte"] == "caminhao") & (audit["categoria"] == "coercao")]
    assert coercions["campo"].eq("DF (REAL)").any()
    assert coercions["mensagem"].str.contains("erro").any()


def test_main_persists_missing_source_diagnostic(tmp_path: Path) -> None:
    output_dir = tmp_path / "out-missing"

    assert main(["--input-dir", str(tmp_path), "--output-dir", str(output_dir)]) == 1
    for filename in ("auditoria_qualidade.csv", "relatorio_qualidade_dados.csv"):
        report = pd.read_csv(output_dir / filename)
        error = report[report["severidade"] == "ERROR"]
        assert error["fonte"].eq("caminhao").any()
        assert error["campo"].str.contains(str(tmp_path)).any()
        assert error["mensagem"].str.contains("Correcao esperada").any()


def test_audit_only_report_contains_no_model_metrics(tmp_path: Path, small_source_dir: Path) -> None:
    """Audit-only runs explain interruption without creating ML result tables."""
    output_dir = tmp_path / "out-audit-only"

    code = main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)])

    assert code != 0
    report = (output_dir / "relatorio_final.txt").read_text(encoding="utf-8").lower()
    assert "interrompida antes do treinamento" in report
    assert "nenhum resultado numerico de modelo" in report
    assert not (output_dir / "metricas_modelos.csv").exists()


def test_final_report_distinguishes_predictive_importance_from_semantics(tmp_path: Path) -> None:
    """The report must not present unconfirmed raw fields as business meaning."""
    results = {
        "status": "completed",
        "base_analitica": pd.DataFrame(),
        "metricas": pd.DataFrame(),
        "importancia": pd.DataFrame({
            "feature": ["AMS_Contador__IMAINDI383_sum_lag_1"],
            "campo_original": ["IMAINDI383"],
            "transformacao": ["sum com defasagem de 1 mes"],
            "status_semantico": ["nao_confirmado"],
        }),
        "mapeamento_features": pd.DataFrame(),
    }

    write_final_report(results, tmp_path)

    report = (tmp_path / "relatorio_final.txt").read_text(encoding="utf-8")
    assert "importância preditiva" in report
    assert "significado operacional confirmado" in report
    assert "IMAINDI383" in report
    assert "sum com defasagem de 1 mes" in report
    assert "causou" not in report.lower()


def test_main_does_not_require_group_map_when_tplnr_is_valid(small_source_dir: Path) -> None:
    """The CLI derives groups from valid operational TPLNR values when no map is supplied."""
    for index, filename in enumerate(OPERATIONAL_FILES.values(), start=1):
        path = small_source_dir / filename
        frame = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        frame = frame.drop(columns=["GRUPO"], errors="ignore")
        frame["TPLNR"] = f"P-M-G{index}-EQ{index}"
        frame.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    for index, filename in enumerate(INDICATOR_FILES.values(), start=1):
        indicator_path = small_source_dir / filename
        indicator = pd.read_excel(indicator_path, sheet_name="Export")
        indicator["EQUIPAMENTO"] = f"EQ{index}"
        with pd.ExcelWriter(indicator_path) as writer:
            indicator.to_excel(writer, sheet_name="Export", index=False)
    output_dir = small_source_dir / "out-derived-group"

    assert main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)]) != 1


def test_missing_group_mapping_stops_before_join(tmp_path: Path) -> None:
    indicators = pd.DataFrame({"EQUIPAMENTO": ["A"], "MES": [pd.Period("2025-01", "M")]})

    with pytest.raises(DataValidationError, match="mapeamento.*GRUPO"):
        build_group_mapping(indicators, {"AMS_Contador": pd.DataFrame()}, None)


def test_derive_tplnr_hierarchy_uses_last_two_segments() -> None:
    frame = pd.DataFrame({"TPLNR": ["PLANTA-MINA-CAM70-CA70959"]})

    result = derive_tplnr_hierarchy(frame)

    assert result.loc[0, "GRUPO"] == "CAM70"
    assert result.loc[0, "EQUIPAMENTO"] == "CA70959"


def test_derive_tplnr_hierarchy_rejects_missing_or_short_tplnr() -> None:
    frame = pd.DataFrame({"TPLNR": [None, "ONLYONE"]})

    with pytest.raises(DataValidationError, match="TPLNR"):
        derive_tplnr_hierarchy(frame)


def test_hierarchy_mapping_assigns_indicator_groups_by_equipment() -> None:
    indicators = pd.DataFrame({"EQUIPAMENTO": ["CA70959"]})
    operational = {"AMS_Contador": pd.DataFrame({"TPLNR": ["P-M-CAM70-CA70959"]})}

    mapped_indicators, mapped_operational = build_hierarchy_group_mapping(indicators, operational)

    assert mapped_indicators.loc[0, "GRUPO"] == "CAM70"
    assert mapped_operational["AMS_Contador"].loc[0, "GRUPO"] == "CAM70"


def test_hierarchy_mapping_rejects_equipment_assigned_to_multiple_groups() -> None:
    indicators = pd.DataFrame({"EQUIPAMENTO": ["CA70959"]})
    operational = {
        "AMS_Contador": pd.DataFrame({"TPLNR": ["P-M-CAM70-CA70959"]}),
        "AMC_ITABIRA": pd.DataFrame({"TPLNR": ["P-M-CAM71-CA70959"]}),
    }

    with pytest.raises(DataValidationError, match="multiplos grupos"):
        build_hierarchy_group_mapping(indicators, operational)


def test_hierarchy_mapping_rejects_indicator_equipment_without_group() -> None:
    indicators = pd.DataFrame({"EQUIPAMENTO": ["CA70960"]})
    operational = {"AMS_Contador": pd.DataFrame({"TPLNR": ["P-M-CAM70-CA70959"]})}

    with pytest.raises(DataValidationError, match="Cobertura incompleta"):
        build_hierarchy_group_mapping(indicators, operational)


def test_main_audits_invalid_tplnr_hierarchy_without_group_map(small_source_dir: Path) -> None:
    output_dir = small_source_dir / "out-invalid-hierarchy"

    assert main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)]) == 1

    audit = pd.read_csv(output_dir / "auditoria_qualidade.csv")
    diagnostic = audit[audit["fonte"] == "hierarquia_tplnr"].iloc[0]
    assert diagnostic["campo"] == "TPLNR"
    assert diagnostic["severidade"] == "ERROR"
    assert "TPLNR" in diagnostic["valor"]


def test_main_audits_hierarchy_conflict_with_specific_correction(small_source_dir: Path) -> None:
    for source, filename in OPERATIONAL_FILES.items():
        path = small_source_dir / filename
        frame = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        frame["TPLNR"] = "P-M-G2-EQ1" if source == "AMC_ITABIRA" else "P-M-G1-EQ1"
        frame.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    output_dir = small_source_dir / "out-hierarchy-conflict"

    assert main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)]) == 1

    audit = pd.read_csv(output_dir / "auditoria_qualidade.csv")
    diagnostic = audit[audit["fonte"] == "hierarquia_tplnr"].iloc[0]
    assert "resolver equipamento em um unico grupo" in diagnostic["valor"].lower()


def test_main_audits_missing_hierarchy_coverage_with_specific_correction(small_source_dir: Path) -> None:
    for filename in OPERATIONAL_FILES.values():
        path = small_source_dir / filename
        frame = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        frame["TPLNR"] = "P-M-G1-EQ1"
        frame.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    output_dir = small_source_dir / "out-missing-hierarchy-coverage"

    assert main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)]) == 1

    audit = pd.read_csv(output_dir / "auditoria_qualidade.csv")
    diagnostic = audit[audit["fonte"] == "hierarquia_tplnr"].iloc[0]
    assert "incluir cobertura hierarquica para o equipamento" in diagnostic["valor"].lower()


def test_lag_is_created_inside_each_group_without_future_values() -> None:
    frame = pd.DataFrame(
        {
            "GRUPO": ["A", "A", "B", "B"],
            "MES": pd.period_range("2025-01", periods=2, freq="M").tolist() * 2,
            "x": [1.0, 2.0, 10.0, 20.0],
        }
    )
    frame.attrs["feature_metadata"] = pd.DataFrame([{
        "feature": "x", "fonte": "AMS_Contador", "campo_original": "IMAINDI383",
        "transformacao": "sum", "mes_referencia": "t", "defasagem": 0,
        "observacoes_validas": 4, "risco_vazamento": "medio", "status_semantico": "confirmado",
    }])

    result, metadata = create_lag_features(frame, ["x"], 1)

    assert result.loc[(result.GRUPO == "A") & (result.MES == pd.Period("2025-02", "M")), "x_lag_1"].item() == 1.0
    assert result.loc[(result.GRUPO == "B") & (result.MES == pd.Period("2025-02", "M")), "x_lag_1"].item() == 10.0
    assert metadata["fonte"].eq("AMS_Contador").all()
    assert metadata["status_semantico"].eq("confirmado").all()
    assert metadata["risco_vazamento"].eq("medio").all()


def test_explicit_map_preserves_source_identifier_and_semantic_status(tmp_path: Path) -> None:
    map_file = tmp_path / "grupos.csv"
    pd.DataFrame({"TPLNR": ["A-01-99"], "GRUPO": ["frota-a"]}).to_csv(map_file, index=False)
    indicators = pd.DataFrame({"EQUIPAMENTO": ["A-01-99"], "MES": [pd.Period("2025-01", "M")]})
    operational = {"AMS_Contador": pd.DataFrame({"TPLNR": ["A-01-99"], "MES": [pd.Period("2025-01", "M")]})}

    mapped_indicators, mapped_operational = build_group_mapping(indicators, operational, map_file)

    assert mapped_indicators.loc[0, "EQUIPAMENTO"] == "A-01-99"
    assert mapped_indicators.loc[0, "GRUPO"] == "frota-a"
    assert mapped_operational["AMS_Contador"].loc[0, "TPLNR"] == "A-01-99"
    assert mapped_operational["AMS_Contador"].loc[0, "GRUPO"] == "frota-a"


def test_operational_features_do_not_assign_unconfirmed_aliases() -> None:
    operational = {
        "AMS_Contador": pd.DataFrame(
            {"GRUPO": ["A", "A"], "MES": [pd.Period("2025-01", "M")] * 2, "IMAINDI383": [1, 2]}
        )
    }

    features, metadata, excluded = build_operational_features(operational)

    assert "AMS_Contador__IMAINDI383_sum" in features.columns
    assert not {"AMS_00H", "AMS_PREVISTAS", "AMS_EXECUTADAS"}.intersection(features.columns)
    assert metadata["status_semantico"].eq("nao_confirmado").all()
    assert excluded["motivo"].eq("chave estrutural").all()


def test_aggregate_monthly_data_uses_group_and_month() -> None:
    frame = pd.DataFrame(
        {"GRUPO": ["A", "A"], "MES": [pd.Period("2025-01", "M")] * 2, "valor": [2.0, 3.0], "tipo": ["x", "x"]}
    )

    result = aggregate_monthly_data(frame)

    assert result.loc[0, "valor_sum"] == 5.0
    assert result.loc[0, "valor_count"] == 2


def test_aggregate_ams_calendar_builds_month_from_year_and_month() -> None:
    frame = pd.DataFrame({"GRUPO": ["A"], "AMSYEAR": [2025], "AMSMON": [2], "valor": [4]})

    result = aggregate_monthly_data(frame)

    assert _month_column(frame) == "AMSYEAR+AMSMON"
    assert result.loc[0, "MES"] == pd.Period("2025-02", "M")
    assert result.loc[0, "valor_sum"] == 4


def test_aggregate_ams_calendar_uses_six_digit_amsmon_directly() -> None:
    frame = pd.DataFrame({"GRUPO": ["A"], "AMSYEAR": [2026], "AMSMON": [202608], "valor": [4]})

    result = aggregate_monthly_data(frame)

    assert result.loc[0, "MES"] == pd.Period("2026-08", "M")


def test_configured_transform_creates_only_explicit_derived_feature() -> None:
    operational = {
        "AMS_Contador": pd.DataFrame(
            {"GRUPO": ["A", "A"], "MES": [pd.Period("2025-01", "M")] * 2, "IMAINDI383": [1, 2]}
        )
    }
    config = [{"name": "AMS_PREVISTAS", "source": "AMS_Contador", "fields": ["IMAINDI383"],
               "transform": "sum", "aggregation": "sum", "semantic_status": "confirmado"}]

    features, metadata, _ = build_operational_features(operational, config)

    assert "AMS_PREVISTAS" in features.columns
    assert metadata.loc[metadata["feature"] == "AMS_PREVISTAS", "status_semantico"].item() == "confirmado"


def test_exclusions_have_fixed_schema_and_keep_eligible_numeric_fields() -> None:
    operational = {"AMC_ITABIRA": pd.DataFrame(
        {"GRUPO": ["A", "A"], "MES": [pd.Period("2025-01", "M")] * 2,
         "AUFNR": [100, 101], "valor": [1.0, 2.0], "texto": ["x", "y"]}
    )}

    features, _, excluded = build_operational_features(operational)

    assert "AMC_ITABIRA__valor_sum" in features.columns
    assert "AMC_ITABIRA__AUFNR_sum" not in features.columns
    assert list(excluded.columns) == ["fonte", "campo_original", "motivo"]
    assert excluded["campo_original"].eq("AUFNR").any()


def test_structural_keys_are_excluded_with_explicit_reasons() -> None:
    operational = {"AMS_Contador": pd.DataFrame(
        {"GRUPO": ["A"], "EQUIPAMENTO": ["EQ-1"], "MES": [pd.Period("2025-01", "M")], "valor": [1]}
    )}

    features, _, excluded = build_operational_features(operational)

    assert "AMS_Contador__valor_sum" in features.columns
    assert {"GRUPO", "EQUIPAMENTO", "MES"}.issubset(set(excluded["campo_original"]))
    assert excluded.loc[excluded["campo_original"] == "GRUPO", "motivo"].item() == "chave estrutural"


def test_sap_temporal_and_join_structures_never_become_features() -> None:
    operational = {"S": pd.DataFrame(
        {"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")], "AMSWEEK": [1],
         "AMSDAY_DATE": [20250101], "PRIMARY_KEY_JOIN": [123], "valor": [2]}
    )}

    features, _, excluded = build_operational_features(operational)

    assert not any(name.startswith(("S__AMSWEEK_", "S__AMSDAY_DATE_", "S__PRIMARY_KEY_JOIN_")) for name in features)
    assert {"AMSWEEK", "AMSDAY_DATE", "PRIMARY_KEY_JOIN"}.issubset(set(excluded["campo_original"]))


def test_coverage_reports_keys_missing_from_indicator_reference() -> None:
    operational = {"AMS_Contador": pd.DataFrame(
        {"GRUPO": ["A", "B"], "MES": [pd.Period("2025-01", "M"), pd.Period("2025-02", "M")], "valor": [1, 2]}
    )}
    indicators = pd.DataFrame({"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")]})

    _, metadata, _ = build_operational_features(operational, {"reference_frame": indicators})
    report = metadata.attrs["coverage_report"]

    assert report.loc[report["fonte"] == "AMS_Contador", "linhas_perdidas_join"].item() == 1
    assert report.loc[report["fonte"] == "AMS_Contador", "chaves_sem_correspondencia"].item() == 1


def test_coverage_reports_unmatched_keys_on_both_sides_and_percent() -> None:
    operational = {"S": pd.DataFrame(
        {"GRUPO": ["A", "B"], "MES": [pd.Period("2025-01", "M"), pd.Period("2025-03", "M")], "valor": [1, 2]}
    )}
    indicators = pd.DataFrame({"GRUPO": ["A", "C"], "MES": [pd.Period("2025-01", "M"), pd.Period("2025-02", "M")]})

    _, metadata, _ = build_operational_features(operational, {"reference_frame": indicators})
    report = metadata.attrs["coverage_report"].loc[lambda value: value["fonte"] == "S"].iloc[0]

    assert report["operational_keys_without_indicator"] == 1
    assert report["indicator_keys_without_operational"] == 1
    assert report["percentual_cobertura"] == 50.0


def test_future_columns_are_excluded_by_configuration() -> None:
    operational = {"AMS_Contador": pd.DataFrame(
        {"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")], "future_value": [9], "valor": [1]}
    )}

    features, _, excluded = build_operational_features(operational, {"future_columns": ["future_value"]})

    assert "AMS_Contador__future_value_sum" not in features.columns
    assert excluded.loc[excluded["campo_original"] == "future_value", "motivo"].item() == "disponibilidade posterior"


def test_lags_reject_response_columns() -> None:
    frame = pd.DataFrame({"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")], "DF (REAL)": [1.0]})

    with pytest.raises(DataValidationError, match="resposta"):
        create_lag_features(frame, ["DF (REAL)"], 1)


def test_lags_reject_feature_name_containing_response_token() -> None:
    frame = pd.DataFrame({"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")], "foo_DF_REAL_sum": [1.0]})
    frame.attrs["feature_metadata"] = pd.DataFrame([{
        "feature": "foo_DF_REAL_sum", "fonte": "S", "campo_original": "bar",
        "transformacao": "sum", "mes_referencia": "t", "defasagem": 0,
        "observacoes_validas": 1, "risco_vazamento": "baixo", "status_semantico": "nao_confirmado",
    }])

    with pytest.raises(DataValidationError, match="resposta"):
        create_lag_features(frame, ["foo_DF_REAL_sum"], 1)


def test_feature_metadata_reports_coverage_and_join_statistics() -> None:
    operational = {
        "AMS_Contador": pd.DataFrame({"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")], "valor": [1]}),
        "AMC_ITABIRA": pd.DataFrame({"GRUPO": ["A"], "MES": [pd.Period("2025-02", "M")], "valor": [2]}),
    }

    _, metadata, _ = build_operational_features(operational)
    report = metadata.attrs["coverage_report"]

    assert {"fonte", "linhas_entrada", "linhas_validas", "meses_sem_cobertura", "cardinalidade_join"}.issubset(report.columns)
    assert report["meses_sem_cobertura"].ge(0).all()


def test_mapping_rejects_inconsistent_existing_group(tmp_path: Path) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame({"EQUIPAMENTO": ["A"], "GRUPO": ["correct"]}).to_csv(path, index=False)
    indicators = pd.DataFrame({"EQUIPAMENTO": ["A"], "GRUPO": ["wrong"]})

    with pytest.raises(DataValidationError, match="inconsistente"):
        build_group_mapping(indicators, {}, path)


def test_mapping_rejects_null_rows_in_map_file(tmp_path: Path) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame({"EQUIPAMENTO": ["A", None], "GRUPO": ["correct", "x"]}).to_csv(path, index=False)

    with pytest.raises(DataValidationError, match="nulos.*1"):
        build_group_mapping(pd.DataFrame({"EQUIPAMENTO": ["A"]}), {}, path)


def test_mapping_rejects_blank_group_in_source(tmp_path: Path) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame({"EQUIPAMENTO": ["A"], "GRUPO": ["grupo-a"]}).to_csv(path, index=False)
    indicators = pd.DataFrame({"EQUIPAMENTO": ["A"], "GRUPO": ["  "]})

    with pytest.raises(DataValidationError, match="GRUPO.*vazio"):
        build_group_mapping(indicators, {}, path)


def test_mapping_rejects_blank_group_in_map_file(tmp_path: Path) -> None:
    path = tmp_path / "map.csv"
    pd.DataFrame({"EQUIPAMENTO": ["A", "B"], "GRUPO": ["grupo-a", ""]}).to_csv(path, index=False)

    with pytest.raises(DataValidationError, match="nulos.*1"):
        build_group_mapping(pd.DataFrame({"EQUIPAMENTO": ["A"]}), {}, path)


def test_lag_metadata_missing_is_an_explicit_event() -> None:
    frame = pd.DataFrame({"GRUPO": ["A"], "MES": [pd.Period("2025-01", "M")], "x": [1.0]})

    _, metadata = create_lag_features(frame, ["x"], 1)

    assert metadata["status_semantico"].eq("nao_confirmado").all()
    assert metadata["risco_vazamento"].eq("nao_avaliado").all()
    assert metadata.attrs["events"].loc[0, "tipo"] == "metadata_ausente"


def make_config() -> Config:
    return Config(
        test_months=2,
        random_state=7,
        min_train_rows=4,
        min_test_rows=2,
    )


def make_small_dataset() -> pd.DataFrame:
    rows = []
    for month_number, month in enumerate(pd.period_range("2025-01", periods=8, freq="M")):
        for group_number, group in enumerate(("A", "B")):
            feature = float(month_number + group_number)
            rows.append({
                "GRUPO": group,
                "MES": month,
                "feature": feature,
                "DF (REAL)": feature + 10.0,
            })
    return pd.DataFrame(rows)


def _forecast_frame_with_all_responses() -> pd.DataFrame:
    periods = pd.period_range("2025-01", periods=14, freq="M")
    return pd.DataFrame({
        "GRUPO": ["A"] * len(periods),
        "MES": periods,
        "DF (REAL)": range(len(periods)),
        "MTBF (REAL)": range(10, 10 + len(periods)),
        "MTBS (REAL)": range(20, 20 + len(periods)),
        "MTTR": range(30, 30 + len(periods)),
        "NIC (VMINA)": range(40, 40 + len(periods)),
        "driver_lag_0": [float(value) for value in range(len(periods))],
    })


def _forecast_frame_with_missing_operational_months() -> pd.DataFrame:
    frame = _forecast_frame_with_all_responses()
    frame.loc[frame["MES"] < pd.Period("2025-05", freq="M"), "driver_lag_0"] = np.nan
    return frame


def _forecast_frame_with_known_driver_effect() -> pd.DataFrame:
    driver = np.array([4.0, 18.0, 7.0, 21.0, 3.0, 15.0, 9.0, 24.0, 6.0, 27.0, 11.0, 30.0, 13.0])
    response = np.r_[50.0, driver[:-1] * 10.0]
    frame = pd.DataFrame({
        "GRUPO": ["A"] * len(driver),
        "MES": pd.period_range("2025-01", periods=len(driver), freq="M"),
        "DF (REAL)": response,
        "driver_lag_0": driver,
        "current_response_decoy_lag_0": response,
    })
    frame.attrs["feature_metadata"] = pd.DataFrame([
        {
            "feature": "driver_lag_0",
            "fonte": "S",
            "campo_original": "driver",
            "transformacao": "lag_0",
            "defasagem": 0,
            "status_semantico": "confirmado",
            "risco_vazamento": "baixo",
        },
        {
            "feature": "current_response_decoy_lag_0",
            "fonte": "S",
            "campo_original": "decoy_operacional",
            "transformacao": "lag_0",
            "defasagem": 0,
            "status_semantico": "confirmado",
            "risco_vazamento": "baixo",
        },
    ])
    return frame


def test_oos_importance_uses_next_month_target_and_final_test_rows() -> None:
    """OOS explanations rank the driver of the forecast target, not the contemporaneous response."""
    data = _forecast_frame_with_known_driver_effect()
    predictions, _, metadata = run_temporal_validation(
        data, "DF (REAL)", Config(test_months=2, min_train_rows=6, min_test_rows=2)
    )
    train_frame = metadata["forecast_train_frame"]
    test_frame = metadata["forecast_test_frame"]

    coefficients, ranking = extract_model_explanations(
        train_frame,
        predictions,
        "DF (REAL)",
        validation_frame=test_frame,
        estimator=metadata["final_estimators"]["elastic_net"],
        response_column="_target",
    )

    assert not coefficients.empty
    assert ranking["status_importancia"].eq("oos_permutacao").all()
    assert ranking.iloc[0]["feature"] == "driver_lag_0"


def test_temporal_validation_excludes_other_reliability_responses() -> None:
    """Other reliability responses never become predictors for a selected response."""
    frame = _forecast_frame_with_all_responses()

    _, _, metadata = run_temporal_validation(
        frame, "DF (REAL)", Config(test_months=2, min_train_rows=4, min_test_rows=2)
    )

    assert "MTBF (REAL)" not in metadata["feature_columns"]
    assert "MTBS (REAL)" not in metadata["feature_columns"]


def test_temporal_validation_uses_explicit_operational_predictor_contract() -> None:
    """The caller can constrain training to the supplied operational predictors."""
    frame = _forecast_frame_with_all_responses()

    _, _, metadata = run_temporal_validation(
        frame,
        "DF (REAL)",
        Config(test_months=2, min_train_rows=4, min_test_rows=2),
        predictor_columns=["driver_lag_0"],
    )

    assert metadata["feature_columns"] == ["driver_lag_0"]
    assert metadata["predictor_columns"] == ["driver_lag_0"]


def test_temporal_exclusions_appear_with_origin_tag_in_features_excluidas(tmp_path: Path) -> None:
    """Predictor exclusions from temporal validation are persisted with a distinct origin tag."""
    from modelo_confiabilidade._pipeline import _temporal_validation_audit

    frame = _forecast_frame_with_all_responses()
    frame["text_preditor"] = "non-numeric"
    _, _, metadata = run_temporal_validation(
        frame, "DF (REAL)", Config(test_months=2, min_train_rows=4, min_test_rows=2),
        predictor_columns=["driver_lag_0", "text_preditor"],
    )

    assert any(excl.get("motivo") == "preditor nao numerico" for excl in metadata.get("excluded_features", []))

    _, temporal_exclusions = _temporal_validation_audit("DF (REAL)", metadata)
    assert not temporal_exclusions.empty
    assert (temporal_exclusions["origem_exclusao"] == "validacao_temporal").all()
    assert (temporal_exclusions["resposta"] == "DF (REAL)").all()

    operational_exclusions = pd.DataFrame([{"campo_original": "id", "motivo": "chave"}])
    combined = pd.concat([operational_exclusions, temporal_exclusions], ignore_index=True, sort=False)
    save_results({"features_excluidas": combined}, tmp_path)
    csv = pd.read_csv(tmp_path / "features_excluidas.csv")
    assert (csv["origem_exclusao"] == "validacao_temporal").sum() >= 1
    assert (csv["origem_exclusao"].isna()).sum() >= 1


def test_temporal_validation_does_not_use_rows_without_operational_features() -> None:
    """Months before operational coverage cannot become imputed training observations."""
    frame = _forecast_frame_with_missing_operational_months()

    _, _, metadata = run_temporal_validation(
        frame, "DF (REAL)", Config(test_months=2, min_train_rows=4, min_test_rows=2)
    )

    assert metadata["train_target_periods"][0] >= pd.Period("2025-05", freq="M")


def test_metrics_ignore_zero_denominator_in_mape() -> None:
    metrics = calculate_regression_metrics(pd.Series([0.0, 2.0]), pd.Series([1.0, 3.0]), 1)

    assert metrics["mape"] == 50.0


def test_model_pipelines_contain_required_estimators_and_random_state() -> None:
    elastic_net = build_model_pipeline("elastic_net", random_state=7)
    random_forest = build_model_pipeline("random_forest", random_state=7)

    assert list(elastic_net.named_steps) == ["imputer", "scaler", "model"]
    assert list(random_forest.named_steps) == ["imputer", "model"]
    assert elastic_net.named_steps["model"].random_state == 7
    assert random_forest.named_steps["model"].random_state == 7


def test_temporal_splits_never_train_on_later_period() -> None:
    predictions, splits, metadata = run_temporal_validation(
        make_small_dataset(), "DF (REAL)", make_config()
    )

    assert not predictions.empty
    assert (splits["train_max_period"] < splits["test_min_period"]).all()
    assert set(predictions["divisao"]) >= {"oof", "teste", "baseline"}
    assert predictions["fora_amostra"].all()
    assert metadata["test_months"] == 2


def test_same_period_groups_stay_in_same_split() -> None:
    _, splits, _ = run_temporal_validation(make_small_dataset(), "DF (REAL)", make_config())

    assert all(
        set(train_periods).isdisjoint(test_periods)
        for train_periods, test_periods in zip(splits["train_periods"], splits["test_periods"])
    )
    oof = splits[splits["divisao"] == "oof"]
    assert oof.groupby("fold")["test_periods"].apply(lambda values: len({tuple(item) for item in values})).eq(1).all()


def test_baseline_uses_previous_period_response() -> None:
    predictions, _, _ = run_temporal_validation(
        make_small_dataset(), "DF (REAL)", make_config()
    )
    baseline = predictions[predictions["divisao"] == "baseline"].sort_values("periodo")

    assert not baseline.empty
    for group in ("A", "B"):
        values = baseline[baseline["GRUPO"] == group].sort_values("periodo")
        assert (values["valor_previsto"].to_numpy() == values["valor_real"].to_numpy() - 1.0).all()


def test_insufficient_data_returns_diagnostic_without_fabricated_metrics() -> None:
    predictions, splits, metadata = run_temporal_validation(
        make_small_dataset().iloc[:2], "DF (REAL)", make_config()
    )

    assert predictions.empty
    assert splits.empty
    assert metadata["status"] == "insuficiente"


def test_target_period_split_excludes_test_responses_from_training() -> None:
    _, splits, metadata = run_temporal_validation(
        make_small_dataset(), "DF (REAL)", make_config()
    )

    assert (splits["train_max_target_period"] < splits["test_min_target_period"]).all()
    assert set(metadata["train_target_periods"]).isdisjoint(metadata["test_target_periods"])


def test_baseline_has_target_period_and_previous_observation() -> None:
    predictions, _, _ = run_temporal_validation(
        make_small_dataset(), "DF (REAL)", make_config()
    )
    baseline = predictions[predictions["divisao"] == "baseline"].sort_values(["GRUPO", "periodo"])

    assert set(baseline["periodo"]) == {
        pd.Period("2025-07", freq="M"), pd.Period("2025-08", freq="M")
    }
    for group in ("A", "B"):
        values = baseline[baseline["GRUPO"] == group]
        assert (values["valor_previsto"].to_numpy() == values["valor_real"].to_numpy() - 1.0).all()


def test_complete_metrics_are_recorded_for_each_window_and_final_test() -> None:
    _, _, metadata = run_temporal_validation(make_small_dataset(), "DF (REAL)", make_config())
    required = {
        "mae", "rmse", "mape", "r2", "r2_ajustado", "pearson", "spearman",
        "erro_medio", "erro_percentual_medio", "variacao_janela",
    }
    metrics = pd.DataFrame(metadata["metricas"])

    assert required.issubset(metrics.columns)
    assert "teste_final" in set(metrics["divisao"])


def test_metric_stability_contains_all_metrics_and_window_variation() -> None:
    _, _, metadata = run_temporal_validation(make_small_dataset(), "DF (REAL)", make_config())
    required = {
        "mae", "rmse", "mape", "r2", "r2_ajustado", "pearson", "spearman",
        "erro_medio", "erro_percentual_medio",
    }

    for summary in metadata["stabilidade_metricas"].values():
        assert required.issubset(summary)
        for metric in required:
            assert {"media", "desvio_padrao", "por_janela"}.issubset(summary[metric])


def _diagnostic_frame() -> pd.DataFrame:
    x = pd.Series(range(1, 31), dtype=float)
    return pd.DataFrame({"x": x, "x_duplicate": x, "response": x * 2 + 0.1 * x ** 2})


def _prediction_frame() -> pd.DataFrame:
    frame = _diagnostic_frame()
    return pd.DataFrame({
        "resposta": "response", "modelo": "elastic_net", "divisao": "teste_final",
        "fora_amostra": True, "valor_real": frame["response"],
        "valor_previsto": frame["response"] + 0.5,
    })


def test_statistical_diagnostics_report_vif_heteroscedasticity_autocorrelation() -> None:
    result = run_statistical_diagnostics(_diagnostic_frame(), _prediction_frame(), "response")

    assert {"vif", "correlacao", "breusch_pagan", "durbin_watson", "amostra", "condition_number"}.issubset(set(result["diagnostico"]))
    assert (result["diagnostico"] == "vif").any()
    assert (result["diagnostico"] == "durbin_watson").any()
    assert result["status"].notna().all()


def test_diagnostics_capture_unsupported_sample_without_stopping() -> None:
    result = run_statistical_diagnostics(pd.DataFrame({"x": [1.0], "response": [2.0]}), pd.DataFrame(), "response")

    assert not result.empty
    assert result["status"].isin({"ok", "insuficiente", "erro"}).all()
    assert (result["status"] != "ok").any()


def test_explanations_return_coefficients_permutation_and_ranking() -> None:
    train = _diagnostic_frame().drop(columns="x_duplicate")
    train.attrs["feature_metadata"] = pd.DataFrame([{
        "feature": "x", "fonte": "S", "campo_original": "valor_x",
        "transformacao": "sum", "defasagem": 1, "status_semantico": "nao_confirmado",
    }])
    predictions = _prediction_frame()
    predictions["modelo"] = "random_forest"
    coefficients, ranking = extract_model_explanations(
        train, predictions, "response", model_name="random_forest", random_state=7
    )

    assert coefficients.empty or {"feature", "resposta", "importancia"}.issubset(coefficients.columns)
    assert {"feature", "resposta", "importancia", "fonte", "campo_original", "transformacao", "defasagem", "confianca"}.issubset(ranking.columns)
    assert ranking["texto"].str.contains("importancia preditiva").all()


def test_classification_uses_out_of_sample_baseline_and_semantics() -> None:
    bad = pd.DataFrame([
        {"modelo": "elastic_net", "divisao": "teste_final", "mae": 2.0, "r2": 0.9, "fora_amostra": True},
        {"modelo": "baseline_t1", "divisao": "teste_final", "mae": 1.0, "r2": 0.0, "fora_amostra": True},
    ])
    good = bad.copy()
    good.loc[0, "mae"] = 0.2
    clean = pd.DataFrame([{"diagnostico": "amostra", "status": "ok", "gravidade": "INFO"}])
    confirmed = pd.DataFrame([{"status_semantico": "confirmado", "risco_vazamento": "baixo"}])
    unconfirmed = confirmed.copy()
    unconfirmed.loc[0, "status_semantico"] = "nao_confirmado"

    assert classify_validity(bad, clean, confirmed, make_config())["classificacao"] == "INVALIDO"
    assert classify_validity(good, clean, unconfirmed, make_config())["classificacao"] == "DESCOBERTA_EXPLORATORIA"


def _confirmed_metrics(**overrides: object) -> pd.DataFrame:
    model = {
        "modelo": "elastic_net", "divisao": "teste_final", "mae": 0.2,
        "r2": 0.8, "mape": 5.0, "variacao_janela": 0.01,
        "fora_amostra": True,
    }
    model.update(overrides)
    return pd.DataFrame([model, {
        "modelo": "baseline_t1", "divisao": "teste_final", "mae": 1.0,
        "r2": 0.0, "mape": 20.0, "variacao_janela": 0.0,
        "fora_amostra": True,
    }])


def test_classification_rejects_bad_r2_mape_cv_and_vif_thresholds() -> None:
    config = Config(min_test_r2=0.7, max_test_mape=10.0, max_metric_cv=0.2, max_vif=5.0, min_test_rows=2)
    diagnostics = pd.DataFrame([
        {"diagnostico": "amostra", "status": "ok", "valor": 10, "gravidade": "INFO"},
        {"diagnostico": "vif", "status": "ok", "valor": 6.0, "gravidade": "WARNING"},
    ])
    result = classify_validity(_confirmed_metrics(r2=0.1, mape=50.0, variacao_janela=1.0), diagnostics,
                               pd.DataFrame([{"status_semantico": "confirmado", "risco_vazamento": "baixo"}]), config)

    assert result["classificacao"] == "INVALIDO"
    assert "threshold" in result["motivo"]
    assert "r2" in result["motivo"]


def test_classification_rejects_missing_oos_flag_and_insufficient_test() -> None:
    config = make_config()
    clean = pd.DataFrame([{"diagnostico": "amostra", "status": "insuficiente", "valor": 1, "gravidade": "WARNING"}])
    metadata = pd.DataFrame([{"status_semantico": "confirmado", "risco_vazamento": "baixo"}])

    missing_flag = _confirmed_metrics().drop(columns="fora_amostra")
    result = classify_validity(missing_flag, clean, metadata, config)
    assert result["classificacao"] == "INVALIDO"
    assert "fora_amostra" in result["motivo"]

    too_small = _confirmed_metrics()
    too_small["fora_amostra"] = True
    result = classify_validity(too_small, clean, metadata, Config(min_test_rows=10))
    assert result["classificacao"] == "INVALIDO"
    assert "amostra" in result["motivo"]


def test_permutation_importance_requires_oos_frame_and_reports_unavailable() -> None:
    train = _diagnostic_frame().drop(columns="x_duplicate")
    train.attrs["feature_metadata"] = pd.DataFrame([{
        "feature": "x", "fonte": "S", "campo_original": "valor_x",
        "transformacao": "sum", "defasagem": 1, "status_semantico": "confirmado",
        "risco_vazamento": "baixo",
    }])
    _, ranking = extract_model_explanations(train, _prediction_frame(), "response")

    assert ranking["status_importancia"].eq("indisponivel").all()
    assert ranking["importancia"].isna().all()


def test_explanations_exclude_leaked_and_response_features() -> None:
    train = _diagnostic_frame().assign(leaked=range(30), alternative_response=range(30))
    train.attrs["feature_metadata"] = pd.DataFrame([
        {"feature": "x", "fonte": "S", "campo_original": "valor_x", "transformacao": "sum", "defasagem": 1,
         "status_semantico": "confirmado", "risco_vazamento": "baixo"},
        {"feature": "leaked", "fonte": "S", "campo_original": "target_future", "transformacao": "raw", "defasagem": 0,
         "status_semantico": "confirmado", "risco_vazamento": "alto"},
        {"feature": "alternative_response", "fonte": "S", "campo_original": "outra_resposta", "transformacao": "raw", "defasagem": 0,
         "status_semantico": "confirmado", "risco_vazamento": "baixo", "papel": "resposta"},
    ])
    coefficients, ranking = extract_model_explanations(
        train, _prediction_frame(), "response", validation_frame=train.copy()
    )

    assert set(coefficients["feature"]) == {"x"}
    assert set(ranking["feature"]) == {"x"}
    assert "status_semantico" in ranking and "risco_vazamento" in ranking


def test_autocorrelation_requires_single_selected_oos_model_and_order_columns() -> None:
    train = _diagnostic_frame().assign(GRUPO=["A"] * 15 + ["B"] * 15, MES=pd.period_range("2025-01", periods=30, freq="M"))
    predictions = pd.DataFrame({
        "modelo": ["elastic_net"] * 4 + ["baseline_t1"] * 4,
        "divisao": ["teste_final"] * 4 + ["oof"] * 4,
        "fora_amostra": [True] * 8,
        "GRUPO": ["A", "A", "B", "B"] * 2,
        "periodo": list(pd.period_range("2025-01", periods=4, freq="M")) * 2,
        "valor_real": [1, 2, 3, 4] * 2,
        "valor_previsto": [1, 1, 4, 4] * 2,
    })
    result = run_statistical_diagnostics(train, predictions, "response")

    assert result.loc[result["diagnostico"] == "durbin_watson", "status"].eq("ok").all()
    assert (result.loc[result["diagnostico"] == "autocorrelacao", "mensagem"].str.contains("teste_final").any()
            or result.loc[result["diagnostico"] == "autocorrelacao", "status"].eq("ok").all())


def test_diagnostics_keep_independent_rows_when_ols_is_unsupported() -> None:
    result = run_statistical_diagnostics(
        pd.DataFrame({"x": [1.0, 1.0], "response": [2.0, 2.0]}),
        pd.DataFrame({"modelo": ["elastic_net"] * 3, "divisao": ["teste_final"] * 3,
                      "fora_amostra": [True] * 3, "GRUPO": ["A"] * 3,
                      "periodo": pd.period_range("2025-01", periods=3, freq="M"),
                      "valor_real": [1, 2, 3], "valor_previsto": [1, 2, 3]}),
        "response",
    )

    assert {"vif", "correlacao", "breusch_pagan", "condition_number", "influencia_ols", "durbin_watson"}.issubset(set(result["diagnostico"]))


def test_configured_algebra_relation_is_distinguished_from_name_heuristic() -> None:
    frame = _diagnostic_frame()
    result = run_statistical_diagnostics(frame, _prediction_frame(), "response",
                                         algebra_relations=[{"name": "x_ratio", "formula": "x / response"}])

    algebra = result[result["diagnostico"] == "algebra"]
    assert not algebra.empty
    assert algebra["mensagem"].str.contains("configurada").any()


def test_permutation_importance_blocks_train_copy_without_oos_marker() -> None:
    train = _diagnostic_frame().drop(columns="x_duplicate")
    _, ranking = extract_model_explanations(
        train, _prediction_frame(), "response", validation_frame=train.copy()
    )

    assert ranking["status_importancia"].eq("indisponivel").all()
    assert ranking["importancia"].isna().all()


def test_permutation_importance_blocks_overlapping_oos_keys() -> None:
    train = _diagnostic_frame().drop(columns="x_duplicate").assign(_target=lambda frame: frame["response"])
    train["GRUPO"] = "A"
    train["MES"] = pd.period_range("2025-01", periods=len(train), freq="M")
    train.attrs["feature_columns"] = ["x"]
    validation = train.copy()
    validation.attrs["fora_amostra"] = True
    validation.attrs["forecast_test_frame"] = True
    estimator = build_model_pipeline("elastic_net", random_state=7)
    estimator.fit(train[["x"]], train["_target"])
    _, ranking = extract_model_explanations(
        train,
        _prediction_frame(),
        "response",
        validation_frame=validation,
        estimator=estimator,
        response_column="_target",
    )

    assert ranking["status_importancia"].eq("indisponivel").all()
    assert ranking["texto"].str.contains("sobreposicao|OOS", case=False, regex=True).all()


def test_permutation_importance_blocks_main_fallback_without_forecast_handoff() -> None:
    train = _diagnostic_frame().drop(columns="x_duplicate")
    validation = train.copy()
    validation.index = validation.index + 100
    validation.attrs["fora_amostra"] = True
    _, ranking = extract_model_explanations(
        train, _prediction_frame(), "response", validation_frame=validation
    )

    assert ranking["status_importancia"].eq("indisponivel").all()
    assert ranking["importancia"].isna().all()


def test_permutation_importance_requires_forecast_estimator_target_and_frame() -> None:
    data = _forecast_frame_with_known_driver_effect()
    predictions, _, metadata = run_temporal_validation(
        data, "DF (REAL)", Config(test_months=2, min_train_rows=6, min_test_rows=2)
    )
    train_frame = metadata["forecast_train_frame"]
    test_frame = metadata["forecast_test_frame"]

    _, ranking_without_estimator = extract_model_explanations(
        train_frame,
        predictions,
        "DF (REAL)",
        validation_frame=test_frame,
        response_column="_target",
    )
    _, ranking_without_future_target = extract_model_explanations(
        train_frame,
        predictions,
        "DF (REAL)",
        validation_frame=test_frame,
        estimator=metadata["final_estimators"]["elastic_net"],
    )
    ad_hoc_test = test_frame.copy()
    ad_hoc_test.attrs.pop("forecast_test_frame", None)
    _, ranking_without_forecast_frame = extract_model_explanations(
        train_frame,
        predictions,
        "DF (REAL)",
        validation_frame=ad_hoc_test,
        estimator=metadata["final_estimators"]["elastic_net"],
        response_column="_target",
    )

    assert ranking_without_estimator["status_importancia"].eq("indisponivel").all()
    assert ranking_without_future_target["status_importancia"].eq("indisponivel").all()
    assert ranking_without_forecast_frame["status_importancia"].eq("indisponivel").all()


def test_permutation_importance_accepts_forecast_handoff() -> None:
    data = _forecast_frame_with_known_driver_effect()
    predictions, _, metadata = run_temporal_validation(
        data, "DF (REAL)", Config(test_months=2, min_train_rows=6, min_test_rows=2)
    )
    _, ranking = extract_model_explanations(
        metadata["forecast_train_frame"],
        predictions,
        "DF (REAL)",
        validation_frame=metadata["forecast_test_frame"],
        estimator=metadata["final_estimators"]["elastic_net"],
        response_column="_target",
    )

    assert ranking["status_importancia"].eq("oos_permutacao").all()


def test_autocorrelation_is_calculated_independently_per_group() -> None:
    train = _diagnostic_frame().assign(GRUPO=["A"] * 30, MES=pd.period_range("2025-01", periods=30, freq="M"))
    predictions = pd.DataFrame({
        "modelo": ["elastic_net"] * 6,
        "divisao": ["teste_final"] * 6,
        "fora_amostra": [True] * 6,
        "GRUPO": ["A", "A", "A", "B", "B", "B"],
        "periodo": list(pd.period_range("2026-01", periods=3, freq="M")) * 2,
        "valor_real": [0, 1, 2, 100, 101, 102],
        "valor_previsto": [1, 2, 3, 0, 1, 2],
    })
    result = run_statistical_diagnostics(train, predictions, "response")

    autocorrelation = result[result["diagnostico"] == "autocorrelacao"]
    assert len(autocorrelation) == 2
    assert set(autocorrelation["grupo"]) == {"A", "B"}
    assert autocorrelation["mensagem"].str.contains("grupo").all()


def test_classification_rejects_two_real_oos_rows_against_minimum_ten() -> None:
    metrics = pd.DataFrame([
        {"modelo": "elastic_net", "divisao": "teste_final", "fora_amostra": True, "valor_real": 1.0, "mae": 0.1, "r2": 0.8, "mape": 1.0},
        {"modelo": "elastic_net", "divisao": "teste_final", "fora_amostra": True, "valor_real": 2.0, "mae": 0.2, "r2": 0.8, "mape": 1.0},
        {"modelo": "baseline_t1", "divisao": "teste_final", "fora_amostra": True, "valor_real": 1.0, "mae": 1.0, "r2": 0.0, "mape": 10.0},
        {"modelo": "baseline_t1", "divisao": "teste_final", "fora_amostra": True, "valor_real": 2.0, "mae": 1.0, "r2": 0.0, "mape": 10.0},
    ])
    diagnostics = pd.DataFrame([{"diagnostico": "amostra", "status": "ok", "valor": 100, "gravidade": "INFO"}])
    result = classify_validity(metrics, diagnostics, pd.DataFrame([{"status_semantico": "confirmado", "risco_vazamento": "baixo"}]), Config(min_test_rows=10))

    assert result["classificacao"] == "INVALIDO"
    assert "amostra" in result["motivo"]


def test_feature_filter_without_metadata_excludes_structural_future_and_risk_names() -> None:
    train = _diagnostic_frame().assign(
        GRUPO=1, MES=1, target_future=1, leakage_score=1, DF_REAL_lag_1=1,
        AUFNR=1, legitimate_feature=range(30),
    )
    _, ranking = extract_model_explanations(train, _prediction_frame(), "response")

    assert set(ranking["feature"]) == {"x", "x_duplicate", "legitimate_feature"}
    assert ranking.attrs["feature_exclusions"]
    assert ranking.attrs["metadata_status"] == "ausente"


def test_temporal_validation_metrics_integrate_with_classifier_on_small_test() -> None:
    config = Config(test_months=2, min_train_rows=4, min_test_rows=10, random_state=7)
    predictions, _, metadata = run_temporal_validation(make_small_dataset(), "DF (REAL)", config)
    metrics = pd.DataFrame(metadata["metricas"])
    diagnostics = pd.DataFrame([{"diagnostico": "amostra", "status": "ok", "valor": 100, "gravidade": "INFO"}])
    feature_metadata = pd.DataFrame([{"status_semantico": "confirmado", "risco_vazamento": "baixo"}])

    assert predictions.empty
    assert not metrics.empty
    assert {"fora_amostra", "test_rows", "observacoes_teste"}.issubset(metrics.columns)
    result = classify_validity(metrics, diagnostics, feature_metadata, config)

    assert result["classificacao"] == "INVALIDO"
    assert "amostra" in result["motivo"]


def test_temporal_validation_metric_records_include_oos_cardinality() -> None:
    _, _, metadata = run_temporal_validation(make_small_dataset(), "DF (REAL)", make_config())
    metrics = pd.DataFrame(metadata["metricas"])

    assert metrics["fora_amostra"].eq(True).all()
    assert metrics["test_rows"].eq(metrics["observacoes_teste"]).all()
    assert metrics.loc[metrics["divisao"] == "teste_final", "observacoes_teste"].eq(metadata["test_rows"]).all()


def test_save_results_persists_required_tables(tmp_path: Path) -> None:
    results = {
        "audit": pd.DataFrame([{"severidade": "INFO", "mensagem": "ok"}]),
        "base_analitica": pd.DataFrame([{"GRUPO": "A", "MES": "2025-01"}]),
        "metricas": pd.DataFrame([{"resposta": "DF (REAL)", "fora_amostra": True}]),
        "previsoes": pd.DataFrame([{"resposta": "DF (REAL)", "valor_real": 1.0}]),
        "coeficientes": pd.DataFrame([{"feature": "x"}]),
        "importancia": pd.DataFrame([{"feature": "x"}]),
        "ranking": pd.DataFrame([{"feature": "x"}]),
        "features_excluidas": pd.DataFrame([{"campo_original": "id", "motivo": "chave"}]),
        "cobertura_temporal": pd.DataFrame([{
            "resposta": "DF (REAL)",
            "min_feature_non_null": 0.5,
            "dropped_rows_without_operational_coverage": 2,
            "dropped_source_periods": "2025-01,2025-02",
            "dropped_target_periods": "2025-02,2025-03",
        }]),
        "mapeamento_features": pd.DataFrame([{"feature": "x", "status_semantico": "nao_confirmado"}]),
        "diagnosticos": pd.DataFrame([{"diagnostico": "amostra", "status": "ok"}]),
        "classificacao": pd.DataFrame([{"resposta": "DF (REAL)", "classificacao": "INVALIDO"}]),
    }

    save_results(results, tmp_path)

    expected = {
        "relatorio_qualidade_dados.csv", "base_analitica.csv", "metricas_modelos.csv",
        "previsoes_fora_amostra.csv", "coeficientes_elastic_net.csv", "importancia_variaveis.csv",
        "ranking_dados_recomendados.csv", "features_excluidas.csv", "mapeamento_features.csv",
        "cobertura_temporal_validacao.csv", "diagnosticos_estatisticos.csv", "classificacao_validade.csv",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    coverage = pd.read_csv(tmp_path / "cobertura_temporal_validacao.csv")
    assert coverage.loc[0, "resposta"] == "DF (REAL)"
    assert coverage.loc[0, "dropped_rows_without_operational_coverage"] == 2


def test_generate_plots_writes_png_for_oos_predictions(tmp_path: Path) -> None:
    predictions = pd.DataFrame({
        "resposta": ["DF (REAL)"] * 3,
        "modelo": ["elastic_net"] * 3,
        "periodo": pd.period_range("2025-01", periods=3, freq="M"),
        "valor_real": [1.0, 2.0, 3.0],
        "valor_previsto": [1.2, 1.8, 3.1],
        "erro": [0.2, -0.2, 0.1],
        "fora_amostra": [True] * 3,
        "divisao": ["teste"] * 3,
    })

    paths = generate_plots({"previsoes": predictions}, tmp_path)

    assert paths
    assert all(path.suffix == ".png" and path.is_file() for path in paths)


def test_write_final_report_audit_only_does_not_invent_metrics(tmp_path: Path) -> None:
    path = write_final_report(
        {"status": "audit_only", "motivo": "mapeamento de GRUPO ausente", "classificacoes": []},
        tmp_path,
    )

    text = path.read_text(encoding="utf-8").lower()
    assert "mapeamento" in text
    assert "modelo vencedor" in text
    assert "mae" not in text


def test_audit_only_run_writes_quality_report_and_returns_error(small_source_dir: Path) -> None:
    path = small_source_dir / OPERATIONAL_FILES["AMS_Contador"]
    frame = pd.read_csv(path, sep=";", encoding="utf-8-sig").drop(columns=["GRUPO"])
    frame.to_csv(path, sep=";", encoding="utf-8-sig", index=False)
    output_dir = small_source_dir / "out-audit-only"

    code = main(["--input-dir", str(small_source_dir), "--output-dir", str(output_dir)])

    assert code != 0
    assert (output_dir / "relatorio_qualidade_dados.csv").exists()
    report = (output_dir / "relatorio_final.txt").read_text(encoding="utf-8").lower()
    assert "tplnr" in report
    assert "derivado" in report
