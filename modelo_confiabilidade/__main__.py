"""Ponto de entrada para ``python -m modelo_confiabilidade``."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

import pandas as pd

from .auditoria import AUDIT_COLUMNS, _write_quality_reports, audit_data_quality
from .configuracao import Config, DataValidationError, configure_logging, parse_args
from .dados import (
    _column_key,
    _indicator_analysis_frame,
    build_group_mapping,
    build_hierarchy_group_mapping,
    build_operational_features,
    create_lag_features,
    load_indicator_files,
    load_operational_files,
    normalize_indicator_frame,
)
from .diagnosticos import (
    classify_validity,
    extract_model_explanations,
    run_statistical_diagnostics,
)
from .deploy import export_model_artifacts, fit_production_estimators
from .modelagem import _temporal_validation_audit, run_temporal_validation
from .relatorios import (
    compute_indicator_correlations,
    compute_real_vs_meta,
    generate_plots,
    save_results,
    write_final_report,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Executa auditoria, mapeamento, modelagem temporal, persistência e relatórios."""
    config = parse_args(argv)
    logger = configure_logging(config.output_dir)
    results: dict[str, Any] = {"status": "failed", "audit": pd.DataFrame(columns=AUDIT_COLUMNS)}
    try:
        # Primeiro carregamos e normalizamos as fontes para aplicar o mesmo contrato de dados.
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
            len(indicators),
            len(operational),
            len(audit),
            errors,
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
        # A partir daqui, transformamos as fontes mapeadas na base analítica temporal.
        analysis_indicators = _indicator_analysis_frame(mapped_indicators)
        features, feature_metadata, excluded = build_operational_features(
            mapped_operational, {"reference_frame": analysis_indicators}
        )
        feature_columns = [column for column in features.columns if column not in {"GRUPO", "MES"}]
        lagged, lag_metadata = create_lag_features(
            features,
            feature_columns,
            config.max_lag,
            response_columns=[
                column
                for column in analysis_indicators.columns
                if column not in {"GRUPO", "MES", "EQUIPAMENTO"}
            ],
        )
        analytic = analysis_indicators.merge(lagged, on=["GRUPO", "MES"], how="left", validate="many_to_one")
        analytic.attrs["feature_metadata"] = lag_metadata
        # Alinhamento de janela: linhas cujo MES esteja a menos de max_lag meses do inicio
        # do dado operacional nao possuem historico completo e ficariam com milhares de
        # colunas de lag 100% NaN. Elas sao removidas antes da modelagem e dos diagnosticos.
        if not features.empty:
            aligned_start = features["MES"].min() + config.max_lag
            rows_before = len(analytic)
            analytic = analytic.loc[analytic["MES"] >= aligned_start].copy()
            logger.info(
                "Alinhamento de janela: MES >= %s (inicio operacional + max_lag); "
                "%d linhas sem historico completo de lags removidas",
                str(aligned_start),
                rows_before - len(analytic),
            )
        # Features sem nenhuma observacao valida nunca se tornam preditores: nao carregam
        # sinal e tornariam imputacao e correlacoes indefinidas.
        lag_feature_columns = lag_metadata["feature"].tolist()
        if "observacoes_validas" in lag_metadata.columns:
            usable = lag_metadata["observacoes_validas"].fillna(0) > 0
            lag_feature_columns = lag_metadata.loc[usable, "feature"].tolist()
            logger.info(
                "Selecao de preditores: %d de %d features de lag possuem ao menos uma observacao valida",
                len(lag_feature_columns),
                len(lag_metadata),
            )
        # Cada lista acumula os artefatos produzidos para um tipo de resultado.
        metric_frames: list[pd.DataFrame] = []
        prediction_frames: list[pd.DataFrame] = []
        diagnostic_frames: list[pd.DataFrame] = []
        coefficient_frames: list[pd.DataFrame] = []
        ranking_frames: list[pd.DataFrame] = []
        coverage_frames: list[pd.DataFrame] = []
        temporal_exclusion_frames: list[pd.DataFrame] = []
        classification_rows: list[dict[str, object]] = []
        model_export_requests: list[dict[str, object]] = []
        response_columns = [
            column
            for column in analysis_indicators.columns
            if _column_key(column) in {"DFREAL", "MTBFREAL", "MTBSREAL", "MTTR", "NICVMINA"}
        ]
        logger.info(
            "Iniciando modelagem de %d respostas: %s",
            len(response_columns),
            ", ".join(response_columns),
        )
        for response_index, response in enumerate(response_columns, start=1):
            response_started = time.monotonic()
            logger.info(
                "Resposta %s (%d/%d): iniciando validacao temporal",
                response,
                response_index,
                len(response_columns),
            )
            try:
                predictions, _, metadata = run_temporal_validation(
                    analytic,
                    response,
                    config,
                    predictor_columns=lag_feature_columns,
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
                fallback_train_frame = (
                    analytic[~analytic["MES"].isin(test_periods)].copy()
                    if test_periods
                    else analytic.iloc[0:0].copy()
                )
                fallback_validation_frame = analytic[analytic["MES"].isin(test_periods)].copy()
                train_frame = metadata.get("forecast_train_frame", fallback_train_frame)
                validation_frame = metadata.get("forecast_test_frame", fallback_validation_frame)
                final_estimators = metadata.get("final_estimators", {})
                coefficients, ranking = extract_model_explanations(
                    train_frame,
                    predictions,
                    response,
                    validation_frame=validation_frame,
                    estimator=final_estimators.get("elastic_net")
                    if isinstance(final_estimators, Mapping)
                    else None,
                    response_column=metadata.get("forecast_target_column"),
                    random_state=config.random_state,
                )
                coefficient_frames.append(coefficients)
                ranking_frames.append(ranking)
                classification = classify_validity(response_metrics, diagnostic, lag_metadata, config)
                classification_rows.append({"resposta": response, **classification})
                final_estimators = metadata.get("final_estimators", {})
                export_estimators = final_estimators
                export_fit_scope = "treino_final (teste OOS excluido)"
                export_training_periods = tuple(metadata.get("train_target_periods", ()))
                production_train = pd.concat(
                    [train_frame, validation_frame], ignore_index=True
                )
                if isinstance(final_estimators, Mapping) and final_estimators:
                    try:
                        export_estimators = fit_production_estimators(
                            final_estimators,
                            production_train,
                            metadata.get("feature_columns", []),
                            target_column=str(metadata.get("forecast_target_column", "_target")),
                        )
                        export_fit_scope = "historico_completo_pos_validacao"
                        export_training_periods += tuple(metadata.get("test_target_periods", ()))
                    except Exception as exc:
                        # A falha do reajuste não apaga o estimador validado; o escopo
                        # exportado identifica claramente que o OOS não foi incluído.
                        logger.warning(
                            "Refit de producao indisponivel para %s; exportando estimador OOS: %s",
                            response,
                            exc,
                        )
                recommended_model = ""
                if not response_metrics.empty and {"modelo", "mae", "divisao"}.issubset(response_metrics.columns):
                    candidates = response_metrics[
                        response_metrics["divisao"].astype(str).eq("teste_final")
                        & ~response_metrics["modelo"].astype(str).str.startswith("baseline")
                        & pd.to_numeric(response_metrics["mae"], errors="coerce").notna()
                    ].sort_values("mae")
                    if not candidates.empty:
                        recommended_model = str(candidates.iloc[0]["modelo"])
                requested_models = set(getattr(config, "export_models", ()))
                if "recommended" in requested_models:
                    requested_models = {recommended_model} if recommended_model else set()
                export_estimators = {
                    str(model_name): estimator
                    for model_name, estimator in export_estimators.items()
                    if str(model_name) in requested_models
                } if isinstance(export_estimators, Mapping) else {}
                if export_estimators:
                    model_export_requests.append({
                        "response": response,
                        "estimators": export_estimators,
                        "feature_columns": metadata.get("feature_columns", []),
                        "training_periods": export_training_periods,
                        "classification": classification.get("classificacao"),
                        "recommended_model": recommended_model,
                        "config": config,
                        "fit_scope": export_fit_scope,
                    })
                logger.info(
                    "Resposta %s: concluida em %.1f min",
                    response,
                    (time.monotonic() - response_started) / 60,
                )
            except Exception as exc:
                logger.exception("Falha na resposta %s", response)
                classification_rows.append({
                    "resposta": response,
                    "classificacao": "INVALIDO",
                    "motivo": f"erro por resposta: {exc}",
                })
        real_vs_meta_frame = compute_real_vs_meta(analysis_indicators)
        correlations_frame = compute_indicator_correlations(
            analytic,
            feature_columns=lag_feature_columns,
            response_columns=response_columns,
        )
        exported_models = export_model_artifacts(model_export_requests, config.output_dir)
        results.update({
            "status": "completed",
            "audit": audit,
            "base_analitica": analytic,
            "real_x_meta": real_vs_meta_frame,
            "correlacoes": correlations_frame,
            "metricas": pd.concat(metric_frames, ignore_index=True) if metric_frames else pd.DataFrame(),
            "previsoes": pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame(),
            "coeficientes": pd.concat(coefficient_frames, ignore_index=True) if coefficient_frames else pd.DataFrame(),
            "importancia": pd.concat(ranking_frames, ignore_index=True) if ranking_frames else pd.DataFrame(),
            "ranking": pd.concat(ranking_frames, ignore_index=True) if ranking_frames else pd.DataFrame(),
            "features_excluidas": pd.concat(
                [excluded, *temporal_exclusion_frames], ignore_index=True, sort=False
            )
            if temporal_exclusion_frames
            else excluded,
            "cobertura_temporal": pd.concat(coverage_frames, ignore_index=True)
            if coverage_frames
            else pd.DataFrame(),
            "mapeamento_features": lag_metadata,
            "diagnosticos": pd.concat(diagnostic_frames, ignore_index=True)
            if diagnostic_frames
            else pd.DataFrame(),
            "classificacao": pd.DataFrame(classification_rows),
            "modelos_exportados": exported_models,
        })
        save_results(results, config.output_dir)
        logger.info("Resultados salvos em %s; gerando graficos", config.output_dir)
        generate_plots(results, config.output_dir)
        write_final_report(results, config.output_dir)
        status = "concluido" if response_columns and classification_rows else "falhou"
        logger.info(
            "Pipeline %s: todos os artefatos gravados em %s (relatorio_final.txt pronto)",
            status,
            config.output_dir,
        )
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
