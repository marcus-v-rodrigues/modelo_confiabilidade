"""Persistência, gráficos e relatório textual."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from .dados import _column_key

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
    "real_x_meta": "real_x_meta.csv",
    "correlacoes": "correlacoes_indicadores.csv",
}


def _as_frame(value: object, columns: Sequence[str] = ()) -> pd.DataFrame:
    """Converte resultados opcionais em um DataFrame estável e serializável."""
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return pd.DataFrame(list(value), columns=list(columns) if columns else None)
    return pd.DataFrame(columns=list(columns))


def save_results(results: Mapping[str, Any], output_dir: Path) -> None:
    """Persiste tabelas de resultados canônicos após a conclusão da execução do modelo. 

    As execuções de auditoria persistem intencionalmente apenas os relatórios de qualidade e a tabela de auditoria. 
    Portanto, uma tabela de ML vazia não deve ser confundida com evidência de um modelo.
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
    """Gera gráficos OOS por resposta e gráficos de explicabilidade rastreáveis."""
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


REAL_VS_META_INDICATORS = {
    "DF": {"real": "DF (REAL)", "meta": "DF (META)", "unidade": "%", "tipo": "maior_melhor"},
    "MTBF": {"real": "MTBF (REAL)", "meta": "MTBF (META)", "unidade": "Horas", "tipo": "maior_melhor"},
    "MTBS": {"real": "MTBS (REAL)", "meta": "MTBS (META)", "unidade": "Horas", "tipo": "maior_melhor"},
    "MTTR": {"real": "MTTR", "meta": "MTTR (META)", "unidade": "Horas", "tipo": "menor_melhor"},
    "NIC": {"real": "NIC (VMINA)", "meta": "NIC (META)", "unidade": "Quantidade", "tipo": "menor_melhor"},
    "UF": {"real": "UF (REAL)", "meta": "UF (META)", "unidade": "%", "tipo": "maior_melhor"},
    "RO": {"real": "RO (REAL)", "meta": "RO (META)", "unidade": "%", "tipo": "maior_melhor"},
    "HT": {"real": "HT (REAL)", "meta": "HT (META)", "unidade": "Horas", "tipo": "neutro"},
    "HM": {"real": "HM (REAL)", "meta": "HM (META)", "unidade": "Horas", "tipo": "menor_melhor"},
    "HMC": {"real": "HMC (REAL)", "meta": "HMC (META)", "unidade": "Horas", "tipo": "menor_melhor"},
}


def compute_real_vs_meta(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate Real vs Meta gaps, percent deviations and target achievement."""
    if frame.empty:
        return pd.DataFrame(columns=[
            "indicador",
            "unidade",
            "periodo",
            "GRUPO",
            "EQUIPAMENTO",
            "valor_real",
            "valor_meta",
            "desvio_absoluto",
            "desvio_percentual",
            "atingimento_percentual",
            "status_atingimento",
        ])

    period_col = "MES" if "MES" in frame.columns else "ANO MÊS" if "ANO MÊS" in frame.columns else "periodo" if "periodo" in frame.columns else None
    equipment_col = "EQUIPAMENTO" if "EQUIPAMENTO" in frame.columns else None
    group_col = "GRUPO" if "GRUPO" in frame.columns else None

    records: list[dict[str, Any]] = []

    for ind_name, config in REAL_VS_META_INDICATORS.items():
        real_col = config["real"]
        meta_col = config["meta"]

        real_match = next((c for c in frame.columns if _column_key(c) == _column_key(real_col)), None)
        meta_match = next((c for c in frame.columns if _column_key(c) == _column_key(meta_col)), None)

        if real_match is None or meta_match is None:
            continue

        real_vals = pd.to_numeric(frame[real_match], errors="coerce")
        meta_vals = pd.to_numeric(frame[meta_match], errors="coerce")

        for idx in frame.index:
            r = real_vals.loc[idx]
            m = meta_vals.loc[idx]

            period_val = frame.loc[idx, period_col] if period_col else np.nan
            eq_val = frame.loc[idx, equipment_col] if equipment_col else np.nan
            grp_val = frame.loc[idx, group_col] if group_col else np.nan

            desvio_abs = float(r - m) if pd.notna(r) and pd.notna(m) else np.nan

            if pd.notna(r) and pd.notna(m) and m != 0 and np.isfinite(m):
                desvio_pct = float(((r - m) / m) * 100)
                atingimento_pct = float((r / m) * 100)
            else:
                desvio_pct = np.nan
                atingimento_pct = np.nan

            status = "INDETERMINADO"
            if pd.notna(r) and pd.notna(m):
                if config["tipo"] == "maior_melhor":
                    status = "ATINGIDO" if r >= m else "NAO_ATINGIDO"
                elif config["tipo"] == "menor_melhor":
                    status = "ATINGIDO" if r <= m else "NAO_ATINGIDO"
                else:
                    status = "APURADO"

            records.append({
                "indicador": ind_name,
                "unidade": config["unidade"],
                "periodo": str(period_val) if pd.notna(period_val) else "",
                "GRUPO": str(grp_val) if pd.notna(grp_val) else "",
                "EQUIPAMENTO": str(eq_val) if pd.notna(eq_val) else "",
                "valor_real": r if pd.notna(r) else np.nan,
                "valor_meta": m if pd.notna(m) else np.nan,
                "desvio_absoluto": desvio_abs,
                "desvio_percentual": desvio_pct,
                "atingimento_percentual": atingimento_pct,
                "status_atingimento": status,
            })

    if not records:
        return pd.DataFrame(columns=[
            "indicador",
            "unidade",
            "periodo",
            "GRUPO",
            "EQUIPAMENTO",
            "valor_real",
            "valor_meta",
            "desvio_absoluto",
            "desvio_percentual",
            "atingimento_percentual",
            "status_atingimento",
        ])

    return pd.DataFrame(records)


def compute_indicator_correlations(
    analytic_frame: pd.DataFrame,
    feature_columns: Sequence[str] | None = None,
    response_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Calcula correlações de Pearson e Spearman priorizando MTBF e DF."""
    if analytic_frame.empty:
        return pd.DataFrame(columns=[
            "indicador",
            "feature",
            "prioridade_analitica",
            "correlacao_pearson",
            "p_valor_pearson",
            "correlacao_spearman",
            "p_valor_spearman",
            "observacoes_validas",
        ])

    responses = list(response_columns) if response_columns else [
        c for c in analytic_frame.columns if _column_key(c) in {
            "MTBFREAL", "DFREAL", "MTBSREAL", "MTTR", "NICVMINA"
        }
    ]

    def _response_priority(resp_name: str) -> tuple[int, str]:
        key = _column_key(resp_name)
        if "MTBF" in key:
            return (0, "ALTA (MTBF - Foco Principal)")
        elif "DF" in key:
            return (1, "ALTA (DF - Foco Secundario)")
        else:
            return (2, "PADRAO")

    if feature_columns is None:
        feat_meta = analytic_frame.attrs.get("feature_metadata")
        if isinstance(feat_meta, pd.DataFrame) and "feature" in feat_meta.columns:
            features = feat_meta["feature"].tolist()
        else:
            features = [
                c for c in analytic_frame.select_dtypes(include=[np.number]).columns
                if c not in responses and not _column_key(c).startswith("UF") and "META" not in _column_key(c)
            ]
    else:
        features = list(feature_columns)

    records: list[dict[str, Any]] = []
    for resp in responses:
        if resp not in analytic_frame.columns:
            continue
        prio_rank, prio_label = _response_priority(resp)
        y = pd.to_numeric(analytic_frame[resp], errors="coerce")
        for feat in features:
            if feat not in analytic_frame.columns:
                continue
            x = pd.to_numeric(analytic_frame[feat], errors="coerce")
            valid = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
            n_obs = int(valid.sum())
            if n_obs < 3:
                continue
            x_val = x[valid].to_numpy()
            y_val = y[valid].to_numpy()

            if np.std(x_val) == 0 or np.std(y_val) == 0:
                continue

            try:
                p_corr, p_val = pearsonr(x_val, y_val)
            except Exception:
                p_corr, p_val = np.nan, np.nan
            try:
                s_corr, s_val = spearmanr(x_val, y_val)
            except Exception:
                s_corr, s_val = np.nan, np.nan

            records.append({
                "indicador": resp,
                "feature": feat,
                "prioridade_analitica": prio_label,
                "_prio_rank": prio_rank,
                "correlacao_pearson": float(p_corr) if np.isfinite(p_corr) else np.nan,
                "p_valor_pearson": float(p_val) if np.isfinite(p_val) else np.nan,
                "correlacao_spearman": float(s_corr) if np.isfinite(s_corr) else np.nan,
                "p_valor_spearman": float(s_val) if np.isfinite(s_val) else np.nan,
                "observacoes_validas": n_obs,
            })

    if not records:
        return pd.DataFrame(columns=[
            "indicador",
            "feature",
            "prioridade_analitica",
            "correlacao_pearson",
            "p_valor_pearson",
            "correlacao_spearman",
            "p_valor_spearman",
            "observacoes_validas",
        ])

    df_corr = pd.DataFrame(records)
    df_corr["_abs_corr"] = df_corr["correlacao_pearson"].abs().fillna(0)
    df_corr = (
        df_corr.sort_values(["_prio_rank", "_abs_corr"], ascending=[True, False])
        .drop(columns=["_prio_rank", "_abs_corr"])
        .reset_index(drop=True)
    )
    return df_corr


def write_final_report(results: Mapping[str, Any], output_dir: Path) -> Path:
    """Escreve relatório factual, omitindo evidências numéricas indisponíveis."""
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
        real_vs_meta = _as_frame(results.get("real_x_meta"))
        correlations = _as_frame(results.get("correlacoes"))

        lines.extend([
            "",
            "============================================================",
            "1. DEFINICOES OFICIAIS E DIRETRIZES DE INDICADORES",
            "============================================================",
            "- DF (Disponibilidade Fisica): % (0 a 100). Proporcao do tempo apto a operar. Impactado por manutencao preventiva.",
            "- UF (Utilizacao Fisica): % (0 a 100). Proporcao do tempo disponivel em operacao. Impactado por planejamento operacional.",
            "  * Nota de modelagem: UF desconsiderada da previsao; foco de correlacao em MTBF e DF (prioridade: MTBF).",
            "- MTBF (Mean Time Between Failures): Horas (>= 0). Tempo medio entre falhas corretivas.",
            "- MTBS (Mean Time Between Stoppages): Horas (>= 0). Tempo medio entre paradas (corretivas e preventivas).",
            "- MTTR (Mean Time to Repair): Horas (>= 0). Tempo medio de reparo por intervencao.",
            "- NIC (Numero de Intervencoes Corretivas): Quantidade / Numero real (>= 0).",
            "- RO (Rendimento Operacional): % (0 a 100).",
            "- Tratamento de desvios: valores 'inf', negativos ou fora da escala [0, 100]% foram expurgados (erro no processo).",
            "- Colunas de META: reservadas para comparacao de atingimento (Real x Meta) e excluidas das preditoras.",
        ])

        if not real_vs_meta.empty and {"indicador", "atingimento_percentual", "desvio_absoluto"}.issubset(real_vs_meta.columns):
            lines.extend([
                "",
                "============================================================",
                "2. RESUMO DE ATINGIMENTO REAL X META",
                "============================================================",
            ])
            for ind, group_df in real_vs_meta.groupby("indicador"):
                valid_real = pd.to_numeric(group_df["valor_real"], errors="coerce").dropna()
                valid_meta = pd.to_numeric(group_df["valor_meta"], errors="coerce").dropna()
                valid_ating = pd.to_numeric(group_df["atingimento_percentual"], errors="coerce").dropna()
                unit = group_df["unidade"].iloc[0] if "unidade" in group_df.columns else ""
                media_real = float(valid_real.mean()) if not valid_real.empty else np.nan
                media_meta = float(valid_meta.mean()) if not valid_meta.empty else np.nan
                media_ating = float(valid_ating.mean()) if not valid_ating.empty else np.nan
                lines.append(
                    f"- {ind} ({unit}): Media Real={media_real:.2f} | Media Meta={media_meta:.2f} | Atingimento Medio={media_ating:.1f}%"
                )

        if not correlations.empty and {"indicador", "feature", "correlacao_pearson"}.issubset(correlations.columns):
            lines.extend([
                "",
                "============================================================",
                "3. CORRELACOES OPERACIONAIS (FOCO MTBF E DF)",
                "============================================================",
            ])
            for prio_ind in ["MTBF (REAL)", "DF (REAL)"]:
                ind_corrs = correlations[correlations["indicador"].astype(str) == prio_ind]
                if not ind_corrs.empty:
                    top_corr = ind_corrs.iloc[0]
                    lines.append(
                        f"- Top Correlacao {prio_ind}: {top_corr['feature']} "
                        f"(Pearson={top_corr['correlacao_pearson']:.3f}, Spearman={top_corr['correlacao_spearman']:.3f})"
                    )

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
            "Limitacoes: consulte features_excluidas.csv, diagnosticos_estatisticos.csv, real_x_meta.csv, correlacoes_indicadores.csv e o status_semantico das features."
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = [
    "REAL_VS_META_INDICATORS",
    "RESULT_TABLE_FILES",
    "_as_frame",
    "_plot_slug",
    "_save_plot",
    "compute_indicator_correlations",
    "compute_real_vs_meta",
    "generate_plots",
    "save_results",
    "write_final_report",
]
