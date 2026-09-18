# `modelo_confiabilidade.deploy`

Exportação, carregamento e utilização dos pipelines treinados. Os artefatos
preservam o estimador completo e o contrato de features usado no treinamento.

## `fit_production_estimators(estimators: Mapping[str, Any], data: DataFrame, feature_columns: Sequence[str], *, target_column: str = "_target") -> dict[str, Any]`

Refaz o ajuste dos estimadores selecionados usando todo o histórico rotulado
após a validação fora da amostra. Mantém os hiperparâmetros dos estimadores
recebidos e retorna cópias ajustadas para produção. O último período, sem alvo
`t+1` conhecido, deve ser excluído de `data` pelo chamador.

`data` deve conter `feature_columns` e `target_column`. Histórico vazio,
colunas ausentes ou ausência de alvos observados gera `ValueError`.

## `export_model_artifact(estimator: Any, output_dir: Path, response: str, model_name: str, feature_columns: Sequence[str], *, classification: str | None = None, training_periods: Sequence[object] = (), config: object | None = None, fit_scope: str = "treino_final", recommended: bool = False) -> tuple[Path, dict[str, Any]]`

Serializa um estimador já ajustado e seu contrato de previsão em
`output_dir/modelos/{resposta}__{modelo}.joblib`. O pipeline completo,
incluindo imputação, escala e estimador, é salvo no artefato.

Retorna o caminho do arquivo e um registro tabular com resposta, modelo,
período de treino, classificação e permissão de uso. O estimador precisa estar
ajustado e possuir `predict()`; ao menos uma feature deve ser informada.

## `export_model_artifacts(requests: Sequence[Mapping[str, Any]], output_dir: Path) -> pandas.DataFrame`

Exporta vários estimadores e grava `output_dir/modelos/manifest.json`. Cada
item de `requests` deve conter `estimators`, `response` e `feature_columns`;
pode também conter `classification`, `training_periods`, `config`, `fit_scope`
e `recommended_model`.

Retorna o inventário dos artefatos como `DataFrame` e cria também o arquivo
`output_dir/modelos_exportados.csv` quando o resultado é persistido pelo
pipeline de relatórios. O manifesto registra a versão, a data de geração e os
arquivos exportados.

## `load_model_artifact(path: Path | str) -> dict[str, Any]`

Carrega um arquivo `.joblib` e valida sua estrutura mínima. O retorno contém,
entre outros campos, `estimator`, `feature_columns`, `response` e `model_name`.
Artefatos que não sejam dicionários, não tenham os campos obrigatórios ou não
contenham um estimador com `predict()` geram `ValueError`.

## `predict_from_artifact(artifact: Path | str | Mapping[str, Any], data: DataFrame, *, allow_invalid: bool = False) -> pandas.DataFrame`

Aplica o artefato a todas as linhas de `data`. `artifact` pode ser o caminho de
um arquivo ou o dicionário retornado por `load_model_artifact`. Os dados devem
conter todas as colunas listadas em `feature_columns`; as agregações e os lags
não são recriados pela função.

Retorna colunas como `resposta`, `modelo`, `GRUPO`,
`periodo_referencia`, `periodo_previsto` e `valor_previsto`. Quando houver um
período (`MES`, `periodo` ou `ANO MÊS`), `periodo_previsto` corresponde ao mês
seguinte.

Por segurança, uma classificação diferente de `VALIDO` bloqueia a previsão.
Para avaliação controlada, a liberação deve ser explícita com
`allow_invalid=True`.

## `predict_latest_from_artifact(artifact: Path | str | Mapping[str, Any], data: DataFrame, *, allow_invalid: bool = False) -> pandas.DataFrame`

Seleciona a linha mais recente de cada `GRUPO` e delega a previsão a
`predict_from_artifact`. Sem uma coluna de período reconhecida, ou sem dados,
usa diretamente todas as linhas recebidas.

## Constantes

- `ARTIFACT_VERSION`: versão do formato dos artefatos; atualmente `1`.
- `MANIFEST_FILENAME`: nome do manifesto gerado, `manifest.json`.

## Exportação automática pela CLI

A execução normal da CLI refaz o ajuste dos modelos com todo o histórico
rotulado após a validação e exporta os modelos selecionados em
`resultados/modelos/`. A opção `--export-models` aceita `elastic_net`,
`random_forest`, `xgboost` ou `recommended`:

```bash
python -m modelo_confiabilidade --export-models random_forest
python -m modelo_confiabilidade --export-models recommended
```

`recommended` exporta o modelo com menor MAE no teste fora da amostra. Os
artefatos não aprovados continuam bloqueados pela API de previsão.

## Exemplo

```python
from pathlib import Path
from modelo_confiabilidade.deploy import predict_latest_from_artifact

previsoes = predict_latest_from_artifact(
    Path("resultados/modelos/MTBF_REAL__random_forest.joblib"),
    base_analitica,
)
```

`base_analitica` deve seguir o mesmo contrato do treinamento: uma linha por
`GRUPO × MES`, com as features agregadas e os mesmos lags. O módulo não lê os
CSVs brutos nem recria a preparação dos dados.
