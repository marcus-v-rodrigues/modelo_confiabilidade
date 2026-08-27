"""Métricas, pipelines e validação temporal."""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .configuracao import Config
from .dados import _column_key

PREDICTION_COLUMNS = [
    "resposta",
    "modelo",
    "periodo",
    "valor_real",
    "valor_previsto",
    "erro",
    "erro_absoluto",
    "erro_percentual",
    "divisao",
    "fora_amostra",
]

CANONICAL_RELIABILITY_RESPONSES = {
    "DF (REAL)",
    "MTBF (REAL)",
    "MTBS (REAL)",
    "MTTR",
    "NIC (VMINA)",
}


def _is_reliability_response_feature(
    column: str,
    metadata_by_feature: Mapping[str, Mapping[str, object]],
) -> bool:
    """Identify a canonical response or any feature explicitly derived from one."""
    response_keys = {_column_key(name) for name in CANONICAL_RELIABILITY_RESPONSES}
    details = metadata_by_feature.get(column, {})
    values = (column, details.get("campo_original", ""), details.get("papel", ""))
    return str(details.get("papel", "")).lower() == "resposta" or any(
        response_key and response_key in _column_key(str(value))
        for response_key in response_keys
        for value in values
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
        column_key = _column_key(str(column))
        if column not in frame.columns:
            excluded.append({"feature": str(column), "motivo": "preditor ausente"})
        elif "META" in column_key:
            excluded.append({"feature": str(column), "motivo": "meta de planejamento (reservada para real x meta)"})
        elif column_key.startswith("UF") or "UTILIZACAO" in column_key:
            excluded.append({"feature": str(column), "motivo": "indicador UF desconsiderado da modelagem preditiva"})
        elif column in {response, "_target"} or _is_reliability_response_feature(
            column, metadata_by_feature
        ):
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
        return {
            name: float("nan")
            for name in (
                "mae",
                "rmse",
                "mape",
                "r2",
                "r2_ajustado",
                "pearson",
                "spearman",
                "erro_medio",
                "erro_percentual_medio",
            )
        }
    error = predicted - actual
    nonzero = actual.ne(0)
    percentage_error = error[nonzero].div(actual[nonzero]) * 100
    actual_values = actual.to_numpy()
    predicted_values = predicted.to_numpy()
    ss_total = float(((actual - actual.mean()) ** 2).sum())
    ss_residual = float((error**2).sum())
    r2 = float(1 - ss_residual / ss_total) if ss_total > 0 else float("nan")
    n = len(actual)
    p = max(int(n_features), 0)
    adjusted = (
        float(1 - (1 - r2) * (n - 1) / (n - p - 1))
        if np.isfinite(r2) and n > p + 1
        else float("nan")
    )
    pearson = float(pd.Series(actual_values).corr(pd.Series(predicted_values)))
    spearman = float(pd.Series(actual_values).corr(pd.Series(predicted_values), method="spearman"))
    return {
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape": float(np.abs(percentage_error).mean()) if not percentage_error.empty else float("nan"),
        "r2": r2,
        "r2_ajustado": adjusted,
        "pearson": pearson,
        "spearman": spearman,
        "erro_medio": float(error.mean()),
        "erro_percentual_medio": (
            float(percentage_error.mean()) if not percentage_error.empty else float("nan")
        ),
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
    response: str,
    model: str,
    periods: pd.Series,
    actual: pd.Series,
    predicted: pd.Series,
    division: str,
    groups: pd.Series,
) -> pd.DataFrame:
    error = predicted - actual
    denominator = actual.replace(0, np.nan)
    result = pd.DataFrame({
        "resposta": response,
        "modelo": model,
        "periodo": periods,
        "GRUPO": groups,
        "valor_real": actual,
        "valor_previsto": predicted,
        "erro": error,
        "erro_absoluto": error.abs(),
        "erro_percentual": error.div(denominator) * 100,
        "divisao": division,
        "fora_amostra": True,
    })
    return result.reset_index(drop=True)


def _fit_search(
    model_name: str,
    X: pd.DataFrame,
    y: pd.Series,
    periods: pd.Series,
    random_state: int,
    n_splits: int,
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
    search = GridSearchCV(
        pipeline,
        grid,
        cv=splitter,
        scoring="neg_mean_absolute_error",
        refit=True,
        n_jobs=1,
    )
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
        "divisao",
        "fold",
        "train_rows",
        "test_rows",
        "train_max_period",
        "test_min_period",
        "train_periods",
        "test_periods",
        "train_max_target_period",
        "test_min_target_period",
        "train_target_periods",
        "test_target_periods",
    ])
    period_column = (
        "MES" if "MES" in data.columns else "periodo" if "periodo" in data.columns else None
    )
    if period_column is None or response not in data.columns:
        return empty_predictions, empty_splits, {
            "status": "insuficiente",
            "motivo": "periodo ou resposta ausente",
        }
    frame = data.copy()
    frame[period_column] = frame[period_column].map(
        lambda value: value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
    )
    frame = frame.sort_values(
        [period_column, "GRUPO"] if "GRUPO" in frame.columns else [period_column]
    ).reset_index(drop=True)
    group_column = "GRUPO" if "GRUPO" in frame.columns else None
    if group_column:
        grouped = frame.groupby(group_column, sort=False)
        frame["_target"] = grouped[response].shift(-1)
        frame["_target_period"] = grouped[period_column].shift(-1)
    else:
        frame["_target"] = frame[response].shift(-1)
        frame["_target_period"] = frame[period_column].shift(-1)
    frame = frame.loc[
        frame["_target"].notna() & frame["_target_period"].eq(frame[period_column] + 1)
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
    test_periods = periods[-config.test_months :] if len(periods) else periods
    train_periods = (
        periods[: -config.test_months] if len(periods) > config.test_months else periods[:0]
    )
    metadata_context = {
        "feature_columns": feature_columns,
        "predictor_columns": feature_columns,
        "excluded_features": excluded_features,
        "coverage_audit": coverage_audit,
        "dropped_periods": coverage_audit["dropped_target_periods"],
    }
    if (
        len(train_periods) < 3
        or len(test_periods) == 0
        or not feature_columns
        or int(frame[frame["_target_period"].isin(train_periods)].shape[0]) < config.min_train_rows
        or int(frame[frame["_target_period"].isin(test_periods)].shape[0]) < config.min_test_rows
    ):
        train_rows = int(frame[frame["_target_period"].isin(train_periods)].shape[0])
        test_rows = int(frame[frame["_target_period"].isin(test_periods)].shape[0])
        empty_metric_values = {
            name: float("nan")
            for name in (
                "mae",
                "rmse",
                "mape",
                "r2",
                "r2_ajustado",
                "pearson",
                "spearman",
                "erro_medio",
                "erro_percentual_medio",
                "variacao_janela",
            )
        }
        insufficient_metrics = [
            {
                "resposta": response,
                "modelo": model_name,
                "divisao": "teste_final",
                "fold": "final",
                "fora_amostra": True,
                "train_rows": train_rows,
                "test_rows": test_rows,
                "observacoes_teste": test_rows,
                "periodos_teste": tuple(test_periods),
                "status": "insuficiente",
                **empty_metric_values,
            }
            for model_name in ("elastic_net", "random_forest", "baseline_t1")
        ]
        return (
            empty_predictions,
            empty_splits,
            {
                "status": "insuficiente",
                "motivo": "linhas ou periodos insuficientes",
                "train_rows": train_rows,
                "test_rows": test_rows,
                "metricas": insufficient_metrics,
                **metadata_context,
            },
        )
    train = frame[frame["_target_period"].isin(train_periods)].copy()
    final_test = frame[frame["_target_period"].isin(test_periods)].copy()
    n_splits = min(3, len(train_periods) - 1)
    if n_splits < 2:
        return (
            empty_predictions,
            empty_splits,
            {
                "status": "insuficiente",
                "motivo": "janelas temporais insuficientes",
                **metadata_context,
            },
        )
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
        for fold, (fit_indices, validation_indices) in enumerate(
            oof_splitter.split(train[feature_columns])
        ):
            fit_frame = train.iloc[fit_indices]
            validation = train.iloc[validation_indices]
            estimator, params = _fit_search(
                model_name,
                fit_frame[feature_columns],
                fit_frame["_target"],
                fit_frame["_target_period"],
                config.random_state,
                min(2, len(pd.Index(fit_frame["_target_period"].unique())) - 1),
            )
            estimator.fit(fit_frame[feature_columns], fit_frame["_target"])
            predicted = pd.Series(
                estimator.predict(validation[feature_columns]), index=validation.index
            )
            oof_predictions.append(
                _prediction_frame(
                    response,
                    model_name,
                    validation["_target_period"],
                    validation["_target"],
                    predicted,
                    "oof",
                    validation[group_column]
                    if group_column
                    else pd.Series("*", index=validation.index),
                )
            )
            fold_metric = calculate_regression_metrics(
                validation["_target"], predicted, len(feature_columns)
            )
            fold_metrics.append(fold_metric)
            metric_records.append({
                "resposta": response,
                "modelo": model_name,
                "divisao": "oof",
                "fold": fold,
                "fora_amostra": True,
                "train_rows": len(fit_frame),
                "test_rows": len(validation),
                "observacoes_teste": len(validation),
                "periodos_teste": tuple(validation["_target_period"].unique()),
                **fold_metric,
            })
            split_records.append({
                "divisao": "oof",
                "fold": fold,
                "modelo": model_name,
                "train_rows": len(fit_frame),
                "test_rows": len(validation),
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
            model_name,
            train[feature_columns],
            train["_target"],
            train["_target_period"],
            config.random_state,
            n_splits,
        )
        predicted_test = pd.Series(
            final_estimator.predict(final_test[feature_columns]), index=final_test.index
        )
        prediction_frames.extend(oof_predictions)
        prediction_frames.append(
            _prediction_frame(
                response,
                model_name,
                final_test["_target_period"],
                final_test["_target"],
                predicted_test,
                "teste",
                final_test[group_column]
                if group_column
                else pd.Series("*", index=final_test.index),
            )
        )
        hyperparameters[model_name] = final_params
        final_estimators[model_name] = final_estimator
        final_metric = calculate_regression_metrics(
            final_test["_target"], predicted_test, len(feature_columns)
        )
        metric_records.append({
            "resposta": response,
            "modelo": model_name,
            "divisao": "teste_final",
            "fold": "final",
            "fora_amostra": True,
            "train_rows": len(train),
            "test_rows": len(final_test),
            "observacoes_teste": len(final_test),
            "periodos_teste": tuple(final_test["_target_period"].unique()),
            **final_metric,
        })
        variation = (
            float(np.nanstd([row["mae"] for row in fold_metrics])) if fold_metrics else float("nan")
        )
        for record in metric_records:
            if record["modelo"] == model_name:
                record["variacao_janela"] = variation
        metric_names = (
            "mae",
            "rmse",
            "mape",
            "r2",
            "r2_ajustado",
            "pearson",
            "spearman",
            "erro_medio",
            "erro_percentual_medio",
        )
        metric_stability[model_name] = {}
        for metric in metric_names:
            window_values = [row[metric] for row in fold_metrics]
            finite_values = [float(value) for value in window_values if np.isfinite(value)]
            metric_stability[model_name][metric] = {
                "media": float(np.mean(finite_values)) if finite_values else None,
                "desvio_padrao": float(np.std(finite_values)) if finite_values else None,
                "por_janela": [
                    float(value) if np.isfinite(value) else None for value in window_values
                ],
            }
    baseline = final_test.copy()
    baseline_pred = baseline[response]
    prediction_frames.append(
        _prediction_frame(
            response,
            "baseline_t1",
            baseline["_target_period"],
            baseline["_target"],
            baseline_pred,
            "baseline",
            baseline[group_column] if group_column else pd.Series("*", index=baseline.index),
        )
    )
    baseline_metric = calculate_regression_metrics(baseline["_target"], baseline_pred, 1)
    metric_records.append({
        "resposta": response,
        "modelo": "baseline_t1",
        "divisao": "teste_final",
        "fold": "final",
        "fora_amostra": True,
        "train_rows": len(train),
        "test_rows": len(final_test),
        "observacoes_teste": len(final_test),
        "periodos_teste": tuple(final_test["_target_period"].unique()),
        "variacao_janela": float("nan"),
        **baseline_metric,
    })
    split_records.append({
        "divisao": "teste",
        "fold": "final",
        "modelo": "todos",
        "train_rows": len(train),
        "test_rows": len(final_test),
        "train_max_period": train["_target_period"].max(),
        "test_min_period": final_test["_target_period"].min(),
        "train_periods": tuple(train["_target_period"].unique()),
        "test_periods": tuple(final_test["_target_period"].unique()),
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
        "status": "ok",
        "response": response,
        "test_months": config.test_months,
        "train_rows": len(train),
        "test_rows": len(final_test),
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
    return (
        pd.concat(prediction_frames, ignore_index=True),
        pd.DataFrame(split_records),
        metadata,
    )


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
        exclusions["campo_original"] = exclusions.get(
            "feature", pd.Series(index=exclusions.index, dtype=object)
        )
    return coverage_row, exclusions


temporal_validation_audit = _temporal_validation_audit

__all__ = [
    "CANONICAL_RELIABILITY_RESPONSES",
    "PREDICTION_COLUMNS",
    "_as_frame",
    "_is_reliability_response_feature",
    "_operational_coverage_mask",
    "_periods_as_text",
    "_select_predictor_columns",
    "_temporal_validation_audit",
    "build_model_pipeline",
    "calculate_regression_metrics",
    "run_temporal_validation",
    "temporal_validation_audit",
]
