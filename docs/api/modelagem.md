# `modelo_confiabilidade.modelagem`

## `calculate_regression_metrics(y_true: Series, y_pred: Series, n_features: int) -> dict[str, float]`

Calcula métricas de regressão para valores reais e previstos: MAE, RMSE, MAPE, R², correlação e métricas ajustadas quando aplicáveis. `n_features` informa a quantidade de preditores para cálculos que dependem dela. Retorna um dicionário numérico; valores indefinidos são `NaN`.

## `build_model_pipeline(model_name: str, random_state: int, device: str = "cpu") -> sklearn.pipeline.Pipeline`

Cria o pipeline estimador. `model_name` aceita `elastic_net`, `random_forest` e, quando disponível, `xgboost`; `random_state` controla reprodutibilidade; `device` aceita `cpu` ou `cuda` (CUDA usa XGBoost). Retorna um `Pipeline` ainda não treinado.

## `run_temporal_validation(data: DataFrame, response: str, config: Config, predictor_columns: Sequence[str] | None = None) -> dict[str, Any]`

Executa treino, busca de hiperparâmetros e validação cronológica para uma resposta. `data` deve conter `GRUPO`, período, a coluna `response` e features; `config` define meses OOS, lags/limites e semente; `predictor_columns=None` aplica a seleção padrão.

Retorna um dicionário com, entre outros, métricas, previsões OOS/OOF, estimadores, importâncias/coeficientes, períodos e auditoria temporal. Não grava arquivos. Insuficiência de dados pode produzir status de auditoria em vez de um modelo válido.

## Classe interna `_PeriodTimeSeriesSplit`

Implementação interna de divisão temporal com janelas progressivas. Possui `__init__(n_splits, periods)`, `get_n_splits(...) -> int` e `split(X, y=None, groups=None)`. Não é API pública estável; seu propósito é impedir treino com períodos posteriores ao teste.
