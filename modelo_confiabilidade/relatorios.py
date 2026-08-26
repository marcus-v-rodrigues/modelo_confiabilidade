"""Persistência, gráficos e relatório textual."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

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
    return "".join(
        character.lower() if str(character).isalnum() else "_" for character in str(value)
    ).strip("_")


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
    predictions = predictions[
        predictions.get("fora_amostra", pd.Series(True, index=predictions.index)).astype(bool)
    ]
    paths: list[Path] = []
    ranking = _as_frame(results.get("ranking"))
    coefficients = _as_frame(results.get("coeficientes"))
    metrics = _as_frame(results.get("metricas"))
    for response, response_predictions in predictions.groupby("resposta", sort=True):
        slug = _plot_slug(response)
        response_predictions = response_predictions.copy()
        response_predictions["periodo"] = response_predictions.get(
            "periodo", pd.RangeIndex(len(response_predictions))
        )
        for model, model_predictions in response_predictions.groupby("modelo", sort=True):
            model_slug = _plot_slug(model)
            ordered = model_predictions.sort_values("periodo")
            figure, axis = plt.subplots()
            axis.plot(
                ordered["periodo"].astype(str), ordered["valor_real"], marker="o", label="real"
            )
            axis.plot(
                ordered["periodo"].astype(str),
                ordered["valor_previsto"],
                marker="o",
                label="previsto",
            )
            axis.set(
                title=f"Serie real e prevista: {response} / {model}",
                xlabel="periodo",
                ylabel=response,
            )
            axis.legend()
            paths.append(_save_plot(plot_dir / f"serie_real_prevista_{slug}_{model_slug}.png"))

            figure, axis = plt.subplots()
            axis.scatter(ordered["valor_real"], ordered["valor_previsto"])
            values = pd.concat([ordered["valor_real"], ordered["valor_previsto"]]).dropna()
            if not values.empty:
                axis.plot(
                    [values.min(), values.max()],
                    [values.min(), values.max()],
                    linestyle="--",
                    color="black",
                )
            axis.set(title=f"Dispersao y=x: {response} / {model}", xlabel="real", ylabel="previsto")
            paths.append(_save_plot(plot_dir / f"dispersao_yx_{slug}_{model_slug}.png"))

            figure, axis = plt.subplots()
            axis.axhline(0, color="black", linewidth=0.8)
            axis.plot(ordered["periodo"].astype(str), ordered["erro"], marker="o")
            axis.set(
                title=f"Residuos temporais: {response} / {model}",
                xlabel="periodo",
                ylabel="erro",
            )
            paths.append(_save_plot(plot_dir / f"residuos_temporais_{slug}_{model_slug}.png"))

            figure, axis = plt.subplots()
            axis.hist(
                pd.to_numeric(ordered["erro"], errors="coerce").dropna(),
                bins=min(10, max(3, len(ordered))),
            )
            axis.set(
                title=f"Distribuicao de erros: {response} / {model}",
                xlabel="erro",
                ylabel="frequencia",
            )
            paths.append(_save_plot(plot_dir / f"distribuicao_erros_{slug}_{model_slug}.png"))

        for frame, value_key, label, prefix in (
            (ranking, "importancia", "importancia", "importancia"),
            (coefficients, "importancia", "coeficiente", "coeficientes"),
        ):
            selected = (
                frame[frame.get("resposta", pd.Series(dtype=object)).eq(response)]
                if not frame.empty and "resposta" in frame
                else pd.DataFrame()
            )
            if selected.empty or value_key not in selected.columns:
                continue
            selected = selected.sort_values(value_key).tail(15)
            figure, axis = plt.subplots(figsize=(8, 5))
            axis.barh(
                selected["feature"].astype(str),
                pd.to_numeric(selected[value_key], errors="coerce"),
            )
            axis.set(title=f"{label.capitalize()}: {response}", xlabel=label)
            paths.append(_save_plot(plot_dir / f"{prefix}_{slug}.png"))

        comparison = (
            metrics[metrics.get("resposta", pd.Series(dtype=object)).eq(response)]
            if not metrics.empty and "resposta" in metrics
            else pd.DataFrame()
        )
        if not comparison.empty and {"modelo", "mae"}.issubset(comparison.columns):
            comparison = comparison[
                comparison.get("divisao", "teste_final").astype(str).eq("teste_final")
            ]
            figure, axis = plt.subplots()
            axis.bar(
                comparison["modelo"].astype(str),
                pd.to_numeric(comparison["mae"], errors="coerce"),
            )
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
            "",
            "Execucao interrompida antes do treinamento.",
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
        responses = sorted(
            set(metrics.get("resposta", pd.Series(dtype=object)).dropna().astype(str))
        )
        for response in responses:
            lines.append(f"- resposta: {response}")
            response_metrics = metrics[
                (metrics["resposta"].astype(str) == response)
                & metrics.get("divisao", "").astype(str).eq("teste_final")
            ]
            if not response_metrics.empty:
                model_rows = response_metrics[
                    ~response_metrics["modelo"].astype(str).str.startswith("baseline")
                ]
                if not model_rows.empty:
                    winner = model_rows.sort_values("mae", na_position="last").iloc[0]
                    if pd.notna(winner.get("mae")):
                        lines.append(
                            f"  modelo vencedor: {winner['modelo']}; MAE teste: {winner['mae']}"
                        )
                baseline = response_metrics[
                    response_metrics["modelo"].astype(str).str.startswith("baseline")
                ]
                if not baseline.empty and pd.notna(baseline.iloc[0].get("mae")):
                    lines.append(f"  baseline MAE teste: {baseline.iloc[0]['mae']}")
            if not predictions.empty and "resposta" in predictions:
                observed = predictions[predictions["resposta"].astype(str).eq(response)]
                lines.append(f"  previsoes OOS observadas: {len(observed)}")
            classification = (
                classifications[
                    classifications.get("resposta", pd.Series(dtype=object)).astype(str).eq(response)
                ]
                if not classifications.empty and "resposta" in classifications
                else pd.DataFrame()
            )
            if not classification.empty:
                lines.append(
                    f"  classificacao: {classification.iloc[0].get('classificacao', 'indisponivel')}"
                )
        lines.extend([
            "",
            "Importância preditiva:",
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
        lines.append(
            "Limitacoes: consulte features_excluidas.csv, diagnosticos_estatisticos.csv e o status_semantico das features."
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = [
    "RESULT_TABLE_FILES",
    "_as_frame",
    "_plot_slug",
    "_save_plot",
    "generate_plots",
    "save_results",
    "write_final_report",
]
