# `modelo_confiabilidade.dados`

Funções de entrada e preparação de dados. Em geral, entradas são `DataFrame` pandas e os retornos são cópias normalizadas, sem modificar o objeto original.

- `load_indicator_files(input_dir: Path) -> dict[str, DataFrame]`: lê os quatro XLSX definidos em `INDICATOR_FILES`, normaliza cada universo e retorna um dicionário por universo. Lança `DataValidationError` para arquivo ausente ou inválido.
- `load_operational_files(input_dir: Path) -> dict[str, DataFrame]`: lê os cinco CSVs definidos em `OPERATIONAL_FILES` e retorna um dicionário por fonte. Lança `DataValidationError` em falhas obrigatórias.
- `normalize_columns(df: DataFrame) -> DataFrame`: normaliza nomes de colunas para comparação e uso interno, preservando os dados.
- `parse_month_series(series: Series, column_name: str) -> Series`: converte valores de mês para uma série mensal consistente; valores inválidos geram `DataValidationError` contextualizado.
- `normalize_indicator_frame(df: DataFrame, source: str) -> DataFrame`: valida e padroniza uma planilha de indicadores, incluindo `ANOMES`, `EQUIPAMENTO` e respostas numéricas.
- `derive_tplnr_hierarchy(frame: DataFrame, tplnr_column: str = "TPLNR") -> DataFrame`: deriva `GRUPO` do penúltimo e `EQUIPAMENTO` do último segmento de `TPLNR`; retorna o frame com as colunas adicionadas. Rejeita hierarquia ausente ou inválida.
- `build_hierarchy_group_mapping(indicators: DataFrame, operational: Mapping[str, DataFrame]) -> DataFrame`: constrói o mapeamento equipamento–grupo a partir da hierarquia operacional e valida cobertura/ambiguidade.
- `build_group_mapping(indicators, operational, map_file: Path | None) -> DataFrame`: usa o CSV explícito quando `map_file` é informado; caso contrário delega à hierarquia `TPLNR`. Retorna o mapeamento validado.
- `aggregate_monthly_data(frame: DataFrame, excluded_columns: Sequence[str] = ()) -> DataFrame`: agrega colunas numéricas por grupo e mês, excluindo as colunas indicadas. Retorna um frame mensal.
- `build_operational_features(operational, feature_config=None) -> DataFrame`: transforma as fontes operacionais em features mensais por `GRUPO`/`MES`. `feature_config` pode ser mapeamento, sequência de mapeamentos ou `None` (configuração padrão). Retorna a base de features e metadados em `DataFrame.attrs`.
- `create_lag_features(frame, feature_columns, max_lag, response_columns=None) -> DataFrame`: cria `lag_0` até `lag_max_lag` por grupo e ordem temporal. `response_columns` impede que respostas sejam tratadas como preditores. Retorna o frame com as novas colunas.

### Fluxo recomendado

```python
ind = load_indicator_files(Path("bases"))
ops = load_operational_files(Path("bases"))
features = build_operational_features(ops)
features = create_lag_features(features, ["alguma_feature"], max_lag=6)
```
