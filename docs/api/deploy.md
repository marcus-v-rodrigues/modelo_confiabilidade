# `modelo_confiabilidade.deploy`

Este módulo exporta os pipelines treinados e permite utilizá-los em novos dados.

## Exportação automática

A execução normal da CLI grava os modelos em `resultados/modelos/` e cria:

- `*.joblib`: artefato contendo o pipeline completo, incluindo imputação, escala e estimador; a CLI refaz o ajuste com todo o histórico rotulado após a validação;
- `manifest.json`: inventário dos artefatos, features, período de treino, classificação e modelo recomendado;
- `../modelos_exportados.csv`: inventário tabular.

A classificação `INVALIDO` ou `EXPLORATORIO` bloqueia o uso padrão do artefato. Isso evita que um resultado não aprovado seja usado acidentalmente em produção.

## Escolher quais modelos exportar

A CLI permite controlar os arquivos que serão salvos:

### Salvar apenas Random Forest

```bash
python -m modelo_confiabilidade \
  --export-models random_forest
```

Serão gerados, por exemplo:

```text
resultados/modelos/DF_REAL__random_forest.joblib
resultados/modelos/MTBF_REAL__random_forest.joblib
...
```

### Salvar vários modelos

```bash
python -m modelo_confiabilidade \
  --export-models elastic_net xgboost
```

### Salvar somente o melhor modelo OOS

```bash
python -m modelo_confiabilidade \
  --export-models recommended
```

`recommended` escolhe o modelo com menor MAE no teste fora da amostra. Os três modelos continuam sendo treinados para comparação; `--export-models` controla somente quais artefatos serão gravados.

## Utilização

As funções públicas são `export_model_artifact`, `export_model_artifacts`, `fit_production_estimators`, `load_model_artifact`, `predict_from_artifact` e `predict_latest_from_artifact`. `fit_production_estimators` preserva os hiperparâmetros escolhidos no OOS e refaz o ajuste com todo o histórico rotulado.

Os dados devem estar no mesmo contrato da base analítica: uma linha por `GRUPO × MES`, com as features agregadas e os mesmos `lag_0` até `lag_max` usados no treinamento.

```python
from pathlib import Path
from modelo_confiabilidade.deploy import (
    load_model_artifact,
    predict_latest_from_artifact,
)

# ``deploy`` concentra a lógica de utilização dos artefatos.
# Esta importação traz a função que valida as features, seleciona o último
# período de cada grupo e chama o predict() do pipeline salvo.
artifact = load_model_artifact(
    Path("resultados/modelos/MTBF_REAL__random_forest.joblib")
)
previsoes = predict_latest_from_artifact(artifact, base_analitica)
```

A instrução `from modelo_confiabilidade.deploy import predict_latest_from_artifact` significa: importar, do módulo `deploy` do pacote `modelo_confiabilidade`, a função responsável por utilizar o modelo. O arquivo `.joblib` contém o estimador, mas o módulo `deploy` também garante o contrato de features, escolhe a linha mais recente por grupo e informa o período `t+1`.

É possível chamar o artefato manualmente, mas isso exige reproduzir essas validações:

```python
import joblib

artefato = joblib.load("resultados/modelos/MTBF_REAL__random_forest.joblib")
modelo = artefato["estimator"]
X = base_analitica[artefato["feature_columns"]]
previsoes = modelo.predict(X)
```

Por isso, a função do módulo `deploy` é a forma recomendada de utilização.

Para testar um artefato ainda não aprovado, a liberação precisa ser explícita:

```python
previsoes = predict_latest_from_artifact(
    artifact, base_analitica, allow_invalid=True
)
```

`predict_from_artifact` prevê todas as linhas recebidas; `predict_latest_from_artifact` seleciona a linha mais recente de cada grupo e informa `periodo_previsto = periodo_referencia + 1`. O campo `recomendado` do manifesto identifica o melhor modelo OOS; ele continua bloqueado se a classificação da resposta não for `VALIDO`.

O módulo não lê os CSVs brutos nem recria agregações e lags. Essa preparação deve ser feita pelo mesmo pipeline de dados usado no treinamento. A última linha sem alvo `t+1` não participa do refit, mas é a linha usada como entrada para a previsão seguinte.
