# Dicionário de dados e metadados de features

Este documento cobre as variáveis geradas pelo pipeline. As definições de indicadores de negócio estão em [indicadores.md](indicadores.md).

## Convenção de features

```text
<FONTE>__<CAMPO_ORIGINAL>_<AGREGACAO>_lag_<N>
```

- **FONTE**: origem operacional, como `AMS_Contador` ou `Backlog_mina_itabira`.
- **CAMPO_ORIGINAL**: campo extraído do SAP.
- **AGREGACAO**: transformação mensal, como `sum`, `mean` ou `count`.
- **lag_N**: defasagem; `lag_0` é o mês atual e `lag_1` em diante são meses anteriores.

Exemplo: `AMS_Contador__IMAINDI383_sum_lag_1`.

## Metadados em `mapeamento_features.csv`

| Atributo | Descrição |
|---|---|
| `feature` | Nome final da variável analítica |
| `fonte` | Fonte operacional de origem |
| `campo_original` | Campo original do SAP |
| `transformacao` | Agregação ou transformação aplicada |
| `lag` | Defasagem mensal |
| `risco_vazamento` | `baixo`, `medio`, `alto` ou `confirmado` |
| `status_semantico` | `confirmado` ou `nao_confirmado` |

## Status semântico

- **`confirmado`**: fórmula, filtros, unidade e significado homologados pela equipe técnica.
- **`nao_confirmado`**: usado como sinal estatístico, sem assumir aliases ou significado de engenharia não validado.

Importância preditiva e correlação não provam causalidade.

## Chaves e alinhamento

| Chave | Tipo | Descrição |
|---|---|---|
| `GRUPO` | `str` | Grupo operacional derivado do penúltimo segmento de `TPLNR` ou de mapeamento explícito. |
| `EQUIPAMENTO` | `str` | Identificador do ativo, derivado do último segmento de `TPLNR` ou presente nos indicadores. |
| `MES` | `Period[M]` | Período mensal no formato `YYYY-MM`. |
| `ANO MÊS` | entrada | Campo original de período nas planilhas de indicadores. |
