"""Exportação e consumo dos artefatos de modelos treinados.

Os artefatos incluem o pipeline completo (imputação, escala e estimador) e o
contrato de features. Isso evita que um consumidor aplique ``predict`` em
colunas diferentes das usadas no treinamento.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.utils.validation import check_is_fitted


ARTIFACT_VERSION = 1
MANIFEST_FILENAME = "manifest.json"


def _slug(value: object) -> str:
    """Cria um identificador estável e seguro para o sistema de arquivos."""
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._-")
    return result or "modelo"


def _period_text(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        return [str(values)]
    try:
        return [str(value) for value in values]
    except TypeError:
        return [str(values)]


def _config_dict(config: object | None) -> dict[str, Any]:
    """Serializa os campos relevantes da Config imutável sem acoplar importações."""
    if config is None:
        return {}
    names = (
        "test_months",
        "max_lag",
        "random_state",
        "device",
        "min_feature_non_null",
        "min_train_rows",
        "min_test_rows",
    )
    return {name: getattr(config, name) for name in names if hasattr(config, name)}


def fit_production_estimators(
    estimators: Mapping[str, Any],
    data: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    target_column: str = "_target",
) -> dict[str, Any]:
    """Refaz o ajuste dos estimadores selecionados com todo o histórico rotulado após a validação OOS.

    Os hiperparâmetros dos estimadores selecionados na validação são mantidos,
    mas a cópia de produção aprende com os períodos de treino e do teste OOS
    final. O último mês da fonte, que não possui alvo ``t+1`` conhecido, é
    naturalmente excluído pelo contrato dos dados e pelo chamador.
    """
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Histórico de produção vazio")
    features = [str(feature) for feature in feature_columns]
    missing = [feature for feature in [*features, target_column] if feature not in data.columns]
    if missing:
        raise ValueError(f"Dados de produção incompletos; colunas ausentes: {missing}")
    labeled = data.loc[data[target_column].notna()].copy()
    if labeled.empty:
        raise ValueError("Histórico de produção não possui alvos observados")
    fitted: dict[str, Any] = {}
    for name, estimator in estimators.items():
        candidate = clone(estimator)
        candidate.fit(labeled.loc[:, features], labeled[target_column])
        fitted[str(name)] = candidate
    return fitted


def export_model_artifact(
    estimator: Any,
    output_dir: Path,
    response: str,
    model_name: str,
    feature_columns: Sequence[str],
    *,
    classification: str | None = None,
    training_periods: Sequence[object] = (),
    config: object | None = None,
    fit_scope: str = "treino_final",
    recommended: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Serializa um estimador ajustado e seu contrato de previsão.

    ``estimator`` já deve estar ajustado. O ``Pipeline`` do sklearn é salvo
    inteiro, portanto o imputador/normalizador usado no treino é restaurado
    junto com o estimador final.
    """
    if estimator is None or not hasattr(estimator, "predict"):
        raise ValueError("O estimador exportado deve ser treinado e possuir predict()")
    try:
        check_is_fitted(estimator)
    except (TypeError, ValueError) as exc:
        raise ValueError("O estimador exportado ainda não foi treinado") from exc
    features = [str(feature) for feature in dict.fromkeys(feature_columns)]
    if not features:
        raise ValueError("Um artefato requer pelo menos uma feature")

    model_dir = output_dir / "modelos"
    model_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_slug(response)}__{_slug(model_name)}.joblib"
    path = model_dir / filename
    created_at = datetime.now(timezone.utc).isoformat()
    allowed = classification is None or str(classification).upper() == "VALIDO"
    payload = {
        "artifact_version": ARTIFACT_VERSION,
        "created_at_utc": created_at,
        "response": str(response),
        "model_name": str(model_name),
        "recommended": bool(recommended),
        "estimator": estimator,
        "feature_columns": features,
        "feature_contract": {
            "grain": "GRUPO x MES",
            "target_horizon": "t+1",
            "required_columns": features,
            "max_lag": getattr(config, "max_lag", None),
        },
        "training_periods": _period_text(training_periods),
        "fit_scope": fit_scope,
        "classification": classification,
        "allowed_for_production": bool(allowed),
        "config": _config_dict(config),
    }

    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - dependência declarada explicitamente
        raise RuntimeError("A exportação requer joblib (pip install joblib)") from exc
    joblib.dump(payload, path)
    record = {
        "resposta": str(response),
        "modelo": str(model_name),
        "arquivo": str(path.relative_to(output_dir)),
        "features": len(features),
        "periodo_treino_inicio": payload["training_periods"][0]
        if payload["training_periods"]
        else "",
        "periodo_treino_fim": payload["training_periods"][-1]
        if payload["training_periods"]
        else "",
        "classificacao": classification or "NAO_CLASSIFICADO",
        "permitido_uso": "SIM" if allowed else "NAO",
        "recomendado": "SIM" if recommended else "NAO",
        "fit_scope": fit_scope,
        "artifact_version": ARTIFACT_VERSION,
    }
    return path, record


def export_model_artifacts(
    requests: Sequence[Mapping[str, Any]], output_dir: Path
) -> pd.DataFrame:
    """Exporta todos os estimadores produzidos pelo pipeline e grava um manifesto.

    Cada solicitação deve conter ``estimators``, ``response`` e
    ``feature_columns``; opcionalmente, pode conter ``classification``,
    ``training_periods`` e ``config``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "modelos").mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for request in requests:
        estimators = request.get("estimators", {})
        if not isinstance(estimators, Mapping):
            continue
        for model_name, estimator in estimators.items():
            _, record = export_model_artifact(
                estimator,
                output_dir,
                str(request["response"]),
                str(model_name),
                request.get("feature_columns", ()),
                classification=request.get("classification"),
                training_periods=request.get("training_periods", ()),
                config=request.get("config"),
                fit_scope=str(request.get("fit_scope", "treino_final")),
                recommended=str(model_name) == str(request.get("recommended_model", "")),
            )
            records.append(record)

    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": records,
    }
    (output_dir / "modelos" / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return pd.DataFrame(records, columns=[
        "resposta",
        "modelo",
        "arquivo",
        "features",
        "periodo_treino_inicio",
        "periodo_treino_fim",
        "classificacao",
        "permitido_uso",
        "recomendado",
        "fit_scope",
        "artifact_version",
    ])


def load_model_artifact(path: Path | str) -> dict[str, Any]:
    """Carrega e valida minimamente um artefato de modelo exportado."""
    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - dependência declarada explicitamente
        raise RuntimeError("A utilização requer joblib (pip install joblib)") from exc
    payload = joblib.load(Path(path))
    if not isinstance(payload, dict):
        raise ValueError("Artefato de modelo inválido: esperado um dicionário")
    required = {"estimator", "feature_columns", "response", "model_name"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Artefato de modelo incompleto; campos ausentes: {sorted(missing)}")
    if not hasattr(payload["estimator"], "predict"):
        raise ValueError("Artefato de modelo inválido: estimator sem predict()")
    return payload


def _artifact_payload(artifact: Path | str | Mapping[str, Any]) -> Mapping[str, Any]:
    return load_model_artifact(artifact) if isinstance(artifact, (Path, str)) else artifact


def predict_from_artifact(
    artifact: Path | str | Mapping[str, Any],
    data: pd.DataFrame,
    *,
    allow_invalid: bool = False,
) -> pd.DataFrame:
    """Aplica um modelo exportado a features já preparadas do período atual.

    ``data`` deve conter uma ou mais linhas no nível do modelo e todas as
    colunas de ``feature_columns``. A função não recria agregações SAP nem
    lags: essas transformações devem ser executadas pelo mesmo pipeline de
    dados usado no treino. Por padrão, artefatos classificados como
    ``INVALIDO`` são bloqueados e exigem ``allow_invalid=True`` explícito para
    experimentação.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data deve ser um pandas.DataFrame")
    payload = _artifact_payload(artifact)
    classification_value = payload.get("classification")
    classification = str(classification_value).upper() if classification_value is not None else ""
    if classification and classification != "VALIDO" and not allow_invalid:
        raise ValueError(
            f"Artefato classificado como {classification}; "
            "uso bloqueado. Passe allow_invalid=True apenas para avaliação."
        )
    features = [str(feature) for feature in payload["feature_columns"]]
    missing = [feature for feature in features if feature not in data.columns]
    if missing:
        raise ValueError(
            "Dados de previsão não possuem as features do artefato: "
            + ", ".join(missing[:20])
            + (" ..." if len(missing) > 20 else "")
        )
    if data.empty:
        return pd.DataFrame(columns=[
            "resposta", "modelo", "GRUPO", "periodo_referencia", "periodo_previsto", "valor_previsto"
        ])

    predicted = np.asarray(payload["estimator"].predict(data.loc[:, features])).reshape(-1)
    period_column = next(
        (column for column in ("MES", "periodo", "ANO MÊS") if column in data.columns),
        None,
    )
    result: dict[str, Any] = {
        "resposta": str(payload["response"]),
        "modelo": str(payload["model_name"]),
        "valor_previsto": predicted,
    }
    if "GRUPO" in data.columns:
        result["GRUPO"] = data["GRUPO"].to_numpy()
    else:
        result["GRUPO"] = np.nan
    if period_column is not None:
        reference = data[period_column].to_numpy()
        result["periodo_referencia"] = reference
        future: list[object] = []
        for value in reference:
            try:
                period = value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
                future.append(period + 1)
            except (TypeError, ValueError):
                future.append(np.nan)
        result["periodo_previsto"] = future
    else:
        result["periodo_referencia"] = np.nan
        result["periodo_previsto"] = np.nan
    return pd.DataFrame(result)


def predict_latest_from_artifact(
    artifact: Path | str | Mapping[str, Any],
    data: pd.DataFrame,
    *,
    allow_invalid: bool = False,
) -> pd.DataFrame:
    """Prevê somente a linha mais recente disponível para cada grupo."""
    period_column = next(
        (column for column in ("MES", "periodo", "ANO MÊS") if column in data.columns),
        None,
    )
    if period_column is None or data.empty:
        return predict_from_artifact(artifact, data, allow_invalid=allow_invalid)
    ordered = data.copy()
    ordered["_serving_period"] = ordered[period_column].map(
        lambda value: value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
    )
    if "GRUPO" in ordered.columns:
        latest = ordered.sort_values("_serving_period").groupby("GRUPO", sort=False).tail(1)
    else:
        latest = ordered.sort_values("_serving_period").tail(1)
    return predict_from_artifact(
        artifact, latest.drop(columns=["_serving_period"]), allow_invalid=allow_invalid
    )


__all__ = [
    "ARTIFACT_VERSION",
    "MANIFEST_FILENAME",
    "export_model_artifact",
    "export_model_artifacts",
    "fit_production_estimators",
    "load_model_artifact",
    "predict_from_artifact",
    "predict_latest_from_artifact",
]
