"""Diagnósticos estatísticos, explicações e classificação."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.pipeline import Pipeline
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import OLSInfluence, variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson

from .configuracao import Config
from .dados import _column_key
from .modelagem import build_model_pipeline

DIAGNOSTIC_COLUMNS = ["diagnostico", "status", "valor", "gravidade", "mensagem", "grupo"]

EXPLANATION_COLUMNS = [
    "feature",
    "resposta",
    "fonte",
    "campo_original",
    "transformacao",
    "defasagem",
    "importancia",
    "estabilidade",
    "confianca",
    "status_importancia",
    "status_semantico",
    "risco_vazamento",
    "texto",
]


def _eligible_explanation_features(
    frame: pd.DataFrame, response: str
) -> tuple[list[str], dict[str, dict[str, object]], list[dict[str, str]]]:
    """Select only numeric, metadata-approved features and record exclusions."""
    metadata = frame.attrs.get("feature_metadata", pd.DataFrame())
    has_metadata = isinstance(metadata, pd.DataFrame) and "feature" in metadata.columns
    metadata_by_feature = metadata.set_index("feature").to_dict("index") if has_metadata else {}
    candidates = (
        list(metadata_by_feature)
        if has_metadata
        else list(frame.select_dtypes(include=[np.number]).columns)
    )
    eligible: list[str] = []
    excluded: list[dict[str, str]] = []
    response_keys = {
        _column_key(response),
        "DFREAL",
        "MTBFREAL",
        "MTBSREAL",
        "MTTR",
        "NICVMINA",
    }
    for feature in candidates:
        item = metadata_by_feature.get(feature, {})
        reason = ""
        feature_key = _column_key(feature)
        if "META" in feature_key:
            reason = "meta de planejamento (reservada para real x meta)"
        elif feature_key.startswith("UF") or "UTILIZACAO" in feature_key:
            reason = "indicador UF desconsiderado da modelagem preditiva"
        elif (
            feature == response
            or any(token in feature_key for token in response_keys if token)
            or any(token in feature_key for token in ("TARGET", "RESPONSE", "RESPOSTA"))
        ):
            reason = "resposta ou resposta alternativa"
        elif (
            feature_key
            in {
                "GRUPO",
                "MES",
                "ANOMES",
                "CALMONTH",
                "EQUIPAMENTO",
                "TPLNR",
                "AUFNR",
                "QMNUM",
                "AUFPL",
                "APLZL",
                "VORNR",
            }
            or any(
                token in feature_key
                for token in ("PRIMARYKEYJOIN", "AMSWEEK", "AMSDAYDATE")
            )
            or feature_key.startswith("ID")
            or feature_key.endswith("ID")
        ):
            reason = "chave estrutural"
        elif any(
            token in feature_key
            for token in (
                "FUTURE",
                "POSTERIOR",
                "LEAK",
                "LEAKAGE",
                "VAZAMENTO",
                "DATACONCLUSAO",
                "DATAREALIZACAO",
            )
        ):
            reason = "risco/disponibilidade posterior"
        elif feature not in frame.columns or not pd.api.types.is_numeric_dtype(frame[feature]):
            reason = "nao numericamente elegivel"
        elif (
            str(item.get("risco_vazamento", "")).strip().lower()
            in {"alto", "true", "sim", "confirmado", "leakage"}
        ):
            reason = "risco de vazamento"
        elif str(item.get("papel", item.get("role", item.get("tipo", "")))).strip().lower() in {
            "resposta",
            "target",
            "response",
        }:
            reason = "resposta alternativa"
        elif any(
            str(item.get(key, "")).strip().lower() in {"posterior", "futuro", "depois", "after"}
            for key in ("disponibilidade", "disponibilidade_temporal", "temporalidade")
        ):
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
    column_marker = (
        "fora_amostra" in validation_frame.columns
        and validation_frame["fora_amostra"].eq(True).all()
    )
    if not (attrs_marker or column_marker):
        return False, "validation_frame sem marcador fora_amostra=True"
    key_sets = []
    for columns in (("GRUPO", "MES"), ("GRUPO", "periodo"), ("MES",), ("periodo",)):
        if set(columns).issubset(train_frame.columns) and set(columns).issubset(
            validation_frame.columns
        ):
            train_keys = set(
                map(
                    tuple,
                    train_frame.loc[:, list(columns)].itertuples(index=False, name=None),
                )
            )
            validation_keys = set(
                map(
                    tuple,
                    validation_frame.loc[:, list(columns)].itertuples(index=False, name=None),
                )
            )
            if train_keys & validation_keys:
                return False, f"sobreposicao de chaves OOS: {columns}"
            key_sets.append(validation_keys)
    if not key_sets and train_frame.index.intersection(validation_frame.index).size:
        return False, "sobreposicao de indices OOS"
    return True, "OOS comprovado"


def run_statistical_diagnostics(
    train_frame: pd.DataFrame,
    predictions: pd.DataFrame,
    response: str,
    algebra_relations: Sequence[Mapping[str, object]] | Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Run independent checks, preserving a status row for every check."""
    rows: list[dict[str, object]] = []

    def record(
        name: str,
        status: str,
        value: object = np.nan,
        severity: str = "INFO",
        message: str = "",
        group: object = np.nan,
    ) -> None:
        rows.append({
            "diagnostico": name,
            "status": status,
            "valor": value,
            "gravidade": severity,
            "mensagem": message,
            "grupo": group,
        })

    numeric = train_frame.select_dtypes(include=[np.number]).copy()
    features, _, _ = _eligible_explanation_features(train_frame, response)
    sample_size = len(train_frame)
    record(
        "amostra",
        "ok" if sample_size >= 30 else "insuficiente",
        sample_size,
        "INFO" if sample_size >= 30 else "WARNING",
        "linhas observadas",
    )

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
        vifs = [
            variance_inflation_factor(matrix.to_numpy(), index)
            for index in range(1, matrix.shape[1])
        ]
        maximum = float(np.nanmax(vifs)) if vifs else np.nan
        record(
            "vif",
            "ok",
            maximum,
            "WARNING" if maximum > 10 else "INFO",
            "VIF maximo entre features",
        )

    def correlation_check() -> None:
        if len(features) < 2:
            raise ValueError("menos de duas features numericas")
        # Colunas constantes ou vazias nao possuem correlacao definida; sao excluidas
        # para evitar divisao por zero (stddev=0) e ConstantInputWarning no spearman.
        varying = [
            feature
            for feature in features
            if feature in numeric.columns and numeric[feature].nunique(dropna=True) > 1
        ]
        if len(varying) < 2:
            raise ValueError("menos de duas features com variancia")
        matrix = numeric[varying].corr().abs()
        upper = matrix.where(np.triu(np.ones(matrix.shape), k=1).astype(bool))
        maximum = float(upper.max().max()) if upper.notna().any().any() else np.nan
        record(
            "correlacao",
            "ok",
            maximum,
            "WARNING" if maximum >= 0.9 else "INFO",
            "correlacoes avaliadas",
        )

    def algebra_check() -> None:
        configured = (
            algebra_relations
            if algebra_relations is not None
            else train_frame.attrs.get("algebra_relations")
        )
        relations = (
            configured
            if isinstance(configured, Sequence) and not isinstance(configured, (str, bytes))
            else [configured]
            if configured
            else []
        )
        if relations:
            for relation in relations:
                if isinstance(relation, Mapping):
                    record(
                        "algebra",
                        "ok",
                        np.nan,
                        "WARNING",
                        f"relacao configurada: {relation.get('formula', relation.get('name', relation))}",
                    )
                else:
                    record("algebra", "ok", np.nan, "WARNING", f"relacao configurada: {relation}")
        elif any(
            token in str(feature).lower()
            for feature in features
            for token in ("ratio", "razao", "per")
        ):
            record("algebra", "heuristica", np.nan, "WARNING", "heuristica por nome; relacao nao confirmada")
        else:
            record("algebra", "insuficiente", np.nan, "INFO", "nenhuma formula ou relacao configurada")

    def fit_ols() -> Any:
        if response not in train_frame or not features:
            raise ValueError("resposta ou features ausente")
        complete = numeric[[*features, response]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(complete) < max(10, len(features) + 3):
            raise ValueError("linhas completas insuficientes")
        return sm.OLS(
            complete[response], sm.add_constant(complete[features], has_constant="add")
        ).fit()

    def residual_check() -> None:
        model = fit_ols()
        residual = model.resid
        standardized = model.get_influence().resid_studentized_internal
        record(
            "residuos",
            "ok",
            float(np.sqrt(np.mean(residual**2))),
            "INFO",
            "RMSE dos residuos OLS",
        )
        record(
            "outliers_residuos",
            "ok",
            int((np.abs(standardized) > 3).sum()),
            "WARNING" if (np.abs(standardized) > 3).any() else "INFO",
            "residuos padronizados acima de 3",
        )

    def breusch_pagan_check() -> None:
        model = fit_ols()
        bp = het_breuschpagan(model.resid, model.model.exog)
        record(
            "breusch_pagan",
            "ok",
            float(bp[1]),
            "WARNING" if bp[1] < 0.05 else "INFO",
            "p-valor do teste de heterocedasticidade",
        )

    def condition_check() -> None:
        model = fit_ols()
        condition = float(np.linalg.cond(model.model.exog))
        record(
            "condition_number",
            "ok",
            condition,
            "WARNING" if condition > 1000 else "INFO",
            "numero de condicao da matriz OLS",
        )

    def influence_check() -> None:
        model = fit_ols()
        cooks = OLSInfluence(model).cooks_distance[0]
        record(
            "influencia_ols",
            "ok",
            int((cooks > 4 / len(model.resid)).sum()),
            "WARNING" if (cooks > 4 / len(model.resid)).any() else "INFO",
            "observacoes com distancia de Cook elevada",
        )

    def autocorrelation_check() -> None:
        required = {
            "modelo",
            "divisao",
            "fora_amostra",
            "valor_real",
            "valor_previsto",
            "GRUPO",
            "periodo",
        }
        if not required.issubset(predictions.columns):
            raise ValueError("predicoes requerem modelo, divisao, fora_amostra, GRUPO e periodo")
        oos = predictions[predictions["fora_amostra"].astype(bool)]
        test = oos[oos["divisao"].astype(str).eq("teste_final")]
        test = test[~test["modelo"].astype(str).str.startswith("baseline")]
        if test.empty:
            raise ValueError("nenhum modelo selecionado no teste_final")
        selected = train_frame.attrs.get("selected_model")
        model_name = (
            str(selected) if selected else str(test.groupby("modelo").size().idxmax())
        )
        test = test[test["modelo"].astype(str).eq(model_name)].copy()
        if test.empty:
            raise ValueError("modelo selecionado sem residuos no teste_final")
        for group, group_frame in test.groupby("GRUPO", sort=False):
            group_frame = group_frame.sort_values("periodo")
            residual = pd.to_numeric(
                group_frame["valor_previsto"], errors="coerce"
            ) - pd.to_numeric(group_frame["valor_real"], errors="coerce")
            residual = residual.dropna()
            if len(residual) < 2 or np.std(residual.to_numpy()) == 0:
                record(
                    "durbin_watson",
                    "insuficiente",
                    np.nan,
                    "WARNING",
                    f"residuos OOS insuficientes ou constantes no grupo {group}",
                    group,
                )
                record(
                    "autocorrelacao",
                    "insuficiente",
                    np.nan,
                    "WARNING",
                    f"residuos OOS insuficientes ou constantes no grupo {group}",
                    group,
                )
                continue
            dw = float(durbin_watson(residual))
            ac = float(residual.autocorr())
            record(
                "durbin_watson",
                "ok",
                dw,
                "WARNING" if dw < 1 or dw > 3 else "INFO",
                f"residuos OOS do modelo {model_name}, divisao teste_final, grupo {group}",
                group,
            )
            record(
                "autocorrelacao",
                "ok",
                ac,
                "WARNING" if abs(ac) > 0.5 else "INFO",
                f"residuos OOS do modelo {model_name}, divisao teste_final, grupo {group}",
                group,
            )

    for name, function in (
        ("vif", vif_check),
        ("correlacao", correlation_check),
        ("algebra", algebra_check),
        ("residuos", residual_check),
        ("breusch_pagan", breusch_pagan_check),
        ("condition_number", condition_check),
        ("influencia_ols", influence_check),
        ("durbin_watson", autocorrelation_check),
    ):
        safe(name, function)
    for name in ("outliers_residuos", "autocorrelacao"):
        if not (pd.DataFrame(rows)["diagnostico"] == name).any():
            record(
                name,
                "insuficiente",
                np.nan,
                "WARNING",
                "diagnostico dependente de OLS/residuos nao disponivel",
            )
    return pd.DataFrame(rows, columns=DIAGNOSTIC_COLUMNS)


def extract_model_explanations(
    train_frame: pd.DataFrame,
    predictions: pd.DataFrame,
    response: str,
    model_name: str = "elastic_net",
    random_state: int = 42,
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
        coefficients = [
            {
                "feature": feature,
                "resposta": response,
                "fonte": meta_by_feature.get(feature, {}).get("fonte", "desconhecida"),
                "campo_original": meta_by_feature.get(feature, {}).get("campo_original", feature),
                "transformacao": meta_by_feature.get(feature, {}).get(
                    "transformacao", "desconhecida"
                ),
                "defasagem": meta_by_feature.get(feature, {}).get("defasagem", np.nan),
                "importancia": float(value),
                "estabilidade": "nao_avaliada",
                "confianca": "exploratoria",
                "status_importancia": "coeficiente",
                "status_semantico": meta_by_feature.get(feature, {}).get(
                    "status_semantico", "nao_confirmado"
                ),
                "risco_vazamento": meta_by_feature.get(feature, {}).get(
                    "risco_vazamento", "nao_avaliado"
                ),
                "texto": (
                    "importancia preditiva; significado operacional confirmado"
                    if str(meta_by_feature.get(feature, {}).get("status_semantico", "")).lower()
                    == "confirmado"
                    else "importancia preditiva; significado operacional nao confirmado"
                ),
            }
            for feature, value in zip(features, values)
        ]
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
    if (
        oos_ok
        and validation is not None
        and len(validation) >= 2
        and target_column in validation
        and set(features).issubset(validation.columns)
    ):
        if hasattr(model, "coef_"):
            base_score = -float(np.mean(np.abs(validation[target_column] - fitted.predict(validation[features]))))
            ranking_values = np.zeros(len(features))
            rng = np.random.RandomState(random_state)
            val_X = validation[features].copy()
            active_indices = [i for i, v in enumerate(values) if abs(v) > 1e-9]
            for idx in active_indices:
                feat_col = features[idx]
                col_orig = val_X[feat_col].to_numpy()
                scores = []
                for _ in range(5):
                    val_X[feat_col] = rng.permutation(col_orig)
                    perm_pred = fitted.predict(val_X)
                    scores.append(-float(np.mean(np.abs(validation[target_column] - perm_pred))))
                val_X[feat_col] = col_orig
                ranking_values[idx] = base_score - float(np.mean(scores))
            ranking_status = "oos_permutacao"
        else:
            result = permutation_importance(
                fitted,
                validation[features],
                validation[target_column],
                n_repeats=5,
                random_state=random_state,
                scoring="neg_mean_absolute_error",
                n_jobs=-1,
            )
            ranking_values = result.importances_mean
            ranking_status = "oos_permutacao"
    ranking = pd.DataFrame(
        [
            {
                **(
                    coefficients[index]
                    if index < len(coefficients)
                    else {"feature": feature, "resposta": response}
                ),
                "fonte": meta_by_feature.get(feature, {}).get("fonte", "desconhecida"),
                "campo_original": meta_by_feature.get(feature, {}).get("campo_original", feature),
                "transformacao": meta_by_feature.get(feature, {}).get(
                    "transformacao", "desconhecida"
                ),
                "defasagem": meta_by_feature.get(feature, {}).get("defasagem", np.nan),
                "importancia": float(value) if np.isfinite(value) else np.nan,
                "estabilidade": (
                    "permutacao_5x" if ranking_status == "oos_permutacao" else "nao_avaliada"
                ),
                "confianca": "exploratoria",
                "status_importancia": ranking_status,
                "status_semantico": meta_by_feature.get(feature, {}).get(
                    "status_semantico", "nao_confirmado"
                ),
                "risco_vazamento": meta_by_feature.get(feature, {}).get(
                    "risco_vazamento", "nao_avaliado"
                ),
                "texto": (
                    (
                        "importancia preditiva; significado operacional confirmado"
                        if str(
                            meta_by_feature.get(feature, {}).get("status_semantico", "")
                        ).lower()
                        == "confirmado"
                        else "importancia preditiva; significado operacional nao confirmado"
                    )
                    if ranking_status == "oos_permutacao"
                    else f"importancia preditiva indisponivel: {oos_reason}; significado operacional nao confirmado"
                ),
            }
            for index, (feature, value) in enumerate(zip(features, ranking_values))
        ],
        columns=EXPLANATION_COLUMNS,
    )
    coefficients_frame = pd.DataFrame(coefficients, columns=EXPLANATION_COLUMNS)
    ranking = ranking.sort_values("importancia", ascending=False).reset_index(drop=True)
    for output in (coefficients_frame, ranking):
        output.attrs["feature_exclusions"] = excluded
        output.attrs["metadata_status"] = "disponivel" if meta_by_feature else "ausente"
    return coefficients_frame, ranking


def classify_validity(
    metrics: pd.DataFrame,
    diagnostics: pd.DataFrame,
    metadata: pd.DataFrame,
    config: Config,
) -> dict[str, str]:
    """Classify only on out-of-sample test evidence and explicit metadata."""
    result = {"classificacao": "INVALIDO", "motivo": "avaliacao fora da amostra nao confiavel"}
    if metrics.empty or "fora_amostra" not in metrics.columns:
        result["motivo"] = "fora_amostra ausente; avaliacao nao confiavel"
        return result
    if "divisao" not in metrics.columns or "modelo" not in metrics.columns:
        result["motivo"] = "divisao/modelo ausente; avaliacao nao confiavel"
        return result
    test = metrics[
        metrics["divisao"].astype(str).eq("teste_final")
        & metrics["fora_amostra"].astype(bool)
    ]
    baseline = test[
        test.get("modelo", pd.Series(dtype=object)).astype(str).str.startswith("baseline")
    ]
    models = test[
        ~test.get("modelo", pd.Series(dtype=object)).astype(str).str.startswith("baseline")
    ]
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
        result["motivo"] = (
            f"amostra OOS/teste insuficiente: {observed_test_rows} < min_test_rows {config.min_test_rows}"
        )
        return result
    model = models.sort_values("mae").iloc[0]
    base_mae = pd.to_numeric(baseline["mae"], errors="coerce").min()
    mae = float(model["mae"]) if pd.notna(model["mae"]) else np.nan
    if (
        not np.isfinite(mae)
        or not np.isfinite(base_mae)
        or mae >= base_mae * (1 - config.min_baseline_improvement)
    ):
        result["motivo"] = "modelo nao supera baseline no teste"
        return result
    violations: list[str] = []
    for field, threshold, comparator in (
        ("r2", config.min_test_r2, lambda value, limit: value < limit),
        ("mape", config.max_test_mape, lambda value, limit: value > limit),
    ):
        if (
            field in model.index
            and pd.notna(model[field])
            and comparator(float(model[field]), threshold)
        ):
            violations.append(f"{field}={model[field]} viola threshold {threshold}")
    if "metric_cv" in model.index:
        cv = float(model["metric_cv"]) if pd.notna(model["metric_cv"]) else np.inf
    elif "variacao_janela" in model.index and pd.notna(model["variacao_janela"]) and mae:
        cv = abs(float(model["variacao_janela"])) / abs(mae)
    else:
        cv = np.nan
    if np.isfinite(cv) and cv > config.max_metric_cv:
        violations.append(f"metric_cv={cv} viola threshold {config.max_metric_cv}")
    vif_rows = (
        diagnostics[diagnostics.get("diagnostico", pd.Series(dtype=object)).eq("vif")]
        if not diagnostics.empty and "diagnostico" in diagnostics
        else pd.DataFrame()
    )
    if not vif_rows.empty and pd.to_numeric(vif_rows["valor"], errors="coerce").max() > config.max_vif:
        violations.append(f"vif viola threshold {config.max_vif}")
    if violations:
        result["motivo"] = "thresholds violados: " + "; ".join(violations)
        return result
    if (
        "leakage" in metadata.columns
        and metadata["leakage"].astype(bool).any()
        or "risco_vazamento" in metadata.columns
        and metadata["risco_vazamento"].astype(str).str.lower().isin({"alto", "confirmado"}).any()
    ):
        result["motivo"] = "risco de vazamento"
        return result
    if (
        not diagnostics.empty
        and diagnostics.get("status", pd.Series(dtype=object)).astype(str).eq("insuficiente").any()
    ):
        result["motivo"] = "amostra insuficiente para teste confiavel"
        return result
    severe = diagnostics.get("gravidade", pd.Series(dtype=object)).astype(str).isin({"ERROR", "CRITICAL"})
    if severe.any():
        result["motivo"] = "diagnostico grave"
        return result
    unconfirmed = (
        "status_semantico" in metadata.columns
        and metadata["status_semantico"].astype(str).str.lower().ne("confirmado").any()
    )
    warning = diagnostics.get("gravidade", pd.Series(dtype=object)).astype(str).eq("WARNING").any()
    if unconfirmed:
        return {
            "classificacao": "DESCOBERTA_EXPLORATORIA",
            "motivo": "previsao mensuravel; semantica nao confirmada",
        }
    if warning:
        return {
            "classificacao": "PARCIALMENTE_VALIDO",
            "motivo": "instabilidade, amostra pequena ou diagnostico de atencao",
        }
    return {
        "classificacao": "VALIDO",
        "motivo": "superacao consistente no teste e mapeamentos confirmados",
    }


__all__ = [
    "DIAGNOSTIC_COLUMNS",
    "EXPLANATION_COLUMNS",
    "_eligible_explanation_features",
    "_oos_validation_status",
    "classify_validity",
    "extract_model_explanations",
    "run_statistical_diagnostics",
]
