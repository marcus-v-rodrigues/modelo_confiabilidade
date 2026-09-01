# `modelo_confiabilidade.diagnosticos`

## `run_statistical_diagnostics(train_frame, predictions, response, algebra_relations=None) -> pandas.DataFrame`

Executa diagnósticos para uma resposta e retorna uma tabela de registros (`diagnostico`, `valor`, `status` e mensagem). `train_frame` contém treino e preditores; `predictions` deve conter previsões com `GRUPO`, período e marcador `fora_amostra`; `response` é a resposta avaliada. `algebra_relations` opcional descreve relações algébricas a verificar.

Inclui VIF, correlação, relações algébricas, resíduos OLS, Breusch-Pagan, número de condição, influência OLS e Durbin-Watson/autocorrelação. A função não grava arquivos.

## `extract_model_explanations(train_frame, predictions, response, model_name="elastic_net", random_state=42, validation_frame=None, estimator=None, response_column=None) -> pandas.DataFrame`

Extrai explicações do modelo: coeficientes do Elastic Net ou importâncias de árvores, priorizando features elegíveis e OOS quando disponível. `estimator` permite reutilizar um pipeline treinado; sem ele, o modelo é ajustado conforme os argumentos. `validation_frame` restringe a avaliação a um frame de validação. Retorna uma tabela com feature, importância/coeficiente e metadados de interpretação.

## `classify_validity(metrics, diagnostics, metadata, config: Config) -> pandas.DataFrame`

Aplica os gates configurados a métricas, diagnósticos e metadados. Retorna uma linha por resposta/modelo com classificação (`VALIDO`, `EXPLORATORIO` ou `INVALIDO`), violações e justificativas. Usa principalmente desempenho OOS, comparação com baseline, estabilidade, VIF, cobertura e status semântico.
