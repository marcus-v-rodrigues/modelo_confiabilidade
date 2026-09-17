# Guia de início rápido

## Executar

O pipeline lê as quatro planilhas de indicadores e os cinco CSVs operacionais de `./bases` e grava os resultados em `./resultados`:

```bash
python -m modelo_confiabilidade
```

Exemplo com parâmetros explícitos:

```bash
python -m modelo_confiabilidade \
  --input-dir ./bases \
  --output-dir ./resultados \
  --test-months 3 \
  --max-lag 6 \
  --random-state 42
```

Consulte todas as opções com:

```bash
python -m modelo_confiabilidade --help
```

`--device cuda` mantém Elastic Net e Random Forest e executa o XGBoost adicionalmente com CUDA. O treinamento e o pré-processamento numérico usam RAPIDS/cuML e XGBoost na GPU. Instale `requirements-gpu.txt` e tenha um driver NVIDIA compatível. A leitura, auditoria, diagnósticos estatísticos e relatórios continuam na CPU. O padrão (`cpu`) usa as implementações CPU.

## Parâmetros principais

| Opção | Padrão | Função |
|---|---:|---|
| `--test-months` | `3` | Meses finais reservados para o teste OOS |
| `--max-lag` | `6` | Histórico máximo de features, incluindo `lag_0` |
| `--min-train-rows` | `30` | Mínimo de linhas para treino |
| `--min-test-rows` | `10` | Mínimo de linhas no teste |
| `--min-feature-non-null` | `0.5` | Cobertura mínima de uma feature no treino |
| `--min-test-r2` | `0.0` | R² mínimo no teste |
| `--max-test-mape` | `100.0` | MAPE máximo permitido |
| `--min-baseline-improvement` | `0.0` | Melhoria mínima sobre persistência |
| `--max-metric-cv` | `1.0` | Instabilidade máxima entre janelas |
| `--max-vif` | `10.0` | VIF máximo tolerado |
| `--export-models` | todos | Modelos exportados; use `recommended` para salvar somente o melhor modelo OOS |

## Interpretar o status

- `completed`: auditoria e modelagem concluídas.
- `audit_only`: erro estrutural ou insuficiência bloqueou a modelagem; o processo retorna código `1` e não fabrica previsões.
- `VALIDO`, `EXPLORATORIO` e `INVALIDO`: classificação por indicador, conforme os gates de validação.

`VALIDO` significa apenas que os critérios configurados foram atendidos no período avaliado; não é garantia de acerto operacional.

## Principais saídas

- `relatorio_final.txt`: resumo executivo.
- `auditoria_qualidade.csv` e `relatorio_qualidade_dados.csv`: qualidade das fontes.
- `base_analitica.csv`: base usada na modelagem.
- `metricas_modelos.csv` e `previsoes_fora_amostra.csv`: desempenho e previsões OOS/OOF.
- `classificacao_validade.csv`: parecer por indicador.
- `mapeamento_features.csv` e `features_excluidas.csv`: rastreabilidade das features.
- `diagnosticos_estatisticos.csv`, `importancia_variaveis.csv` e `coeficientes_elastic_net.csv`: diagnósticos e explicabilidade.
- `real_x_meta.csv` e `correlacoes_indicadores.csv`: análises descritivas.
- `graficos/`: visualizações OOS.
- `modelos/`: pipelines treinados em arquivos `.joblib` e `manifest.json`.
- `modelos_exportados.csv`: inventário dos modelos exportados e sua permissão de uso.

## Utilizar um modelo exportado

A execução da CLI exporta automaticamente os estimadores treinados. Após a validação, o artefato é refitado com todo o histórico rotulado e contém o pipeline completo (imputador, normalizador e modelo) e o contrato das features:

```python
from pathlib import Path
from modelo_confiabilidade.deploy import predict_latest_from_artifact

previsoes = predict_latest_from_artifact(
    Path("resultados/modelos/MTBF_REAL__random_forest.joblib"),
    base_analitica,
)
```

A instrução `from modelo_confiabilidade.deploy import predict_latest_from_artifact` importa, do módulo `deploy`, a função que utiliza o modelo salvo. Ela valida as features, seleciona o período mais recente de cada grupo, chama `predict()` e informa o período previsto (`t+1`). O `.joblib` contém o modelo, enquanto `deploy.py` concentra a lógica segura de utilização.

Embora seja possível fazer manualmente com `joblib`, essa forma não valida o contrato completo:

```python
import joblib

artefato = joblib.load("resultados/modelos/MTBF_REAL__random_forest.joblib")
previsoes = artefato["estimator"].predict(
    base_analitica[artefato["feature_columns"]]
)
```

Por isso, `predict_latest_from_artifact` é a forma recomendada. `base_analitica` deve ter as mesmas colunas agregadas e defasadas (`lag_0` até `lag_6`) do treinamento. Por segurança, modelos classificados como `INVALIDO` ou `EXPLORATORIO` são bloqueados; para experimentação, use explicitamente `allow_invalid=True`.

### Escolher quais modelos exportar

#### Salvar apenas Random Forest

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

#### Salvar vários modelos

```bash
python -m modelo_confiabilidade \
  --export-models elastic_net xgboost
```

#### Salvar somente o melhor modelo OOS

```bash
python -m modelo_confiabilidade \
  --export-models recommended
```

Nesse caso, o melhor modelo é escolhido pelo menor MAE no teste fora da amostra. Os três modelos continuam sendo treinados para comparação; essa opção controla somente quais artefatos serão exportados.

Para testes automatizados:

```bash
pytest -q
```
