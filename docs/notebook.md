# O que o Notebook Faz

Fonte: [`../Correlacao_AMS_DF_frota.ipynb`](../Correlacao_AMS_DF_frota.ipynb).

## Objetivo

O notebook relaciona indicadores mensais de confiabilidade de equipamentos
(`DF`, `MTBF`, `MTBS`, `MTTR` e `NIC`) com indicadores de manutenção planejada,
notificações, atividades programadas e backlog. A unidade analítica final é
`ANO MÊS + GRUPO`.

## Entradas Esperadas

O notebook referencia quatro planilhas de indicadores e quatro CSVs:

```text
INDICADORES MENSAIS POR UNIVERSO.xlsx
INDICADORES MENSAIS POR UNIVERSO (2).xlsx
INDICADORES MENSAIS POR UNIVERSO (3).xlsx
INDICADORES MENSAIS POR UNIVERSO (4).xlsx
AMS_ativos_mina.csv
AMC_ativos_mina.csv
APR_ativos_mina.csv
Backlog_imos_ativos_mina.csv
```

Os arquivos atuais equivalentes estão descritos em [Indicadores](indicadores.md)
e [Fontes Operacionais](operacionais.md). Os conflitos de nomes e esquema estão
em [Conflitos](conflitos.md).

## Preparação

1. Os quatro DataFrames de indicadores são concatenados em `df`.
2. As colunas têm espaços laterais removidos.
3. `CALMONTH-Calendar_year_month` é renomeada para `ANO MÊS` nas fontes
   operacionais.
4. Datas são convertidas com o formato `%Y%m`; datas inválidas viram `NaT` e
   são removidas da base de indicadores.
5. Números com vírgula decimal são convertidos para numérico; valores inválidos
   viram `NaN`.
6. O `GRUPO` é extraído do penúltimo segmento de `TPLNR05`.
7. Um mapa de equipamento para grupo é obtido a partir do AMS e usado para
   enriquecer `df`.

O notebook registra aproximadamente 1,24% de linhas de indicadores sem grupo
após esse merge.

## Indicadores Derivados

### AMS

- `AMS_PREVISTAS`: ordens previstas.
- `AMS_EXECUTADAS`: ordens fechadas.
- `AMS_PENDENTES`: previstas menos executadas.
- `AMS_PCT_PENDENTE`: pendentes divididas pelas previstas.

### AMC

- `AMC_PREVISTAS`: notificações planejadas.
- `AMC_EXECUTADAS`: previstas multiplicadas por `AMC_00I / 100`.
- `AMC_NAO_ADERENTES`: previstas menos executadas.
- `AMC_PCT_NAO_ADERENTE`: não aderentes divididas pelas previstas.

### APR

- `APR_PREVISTAS`: total planejado.
- `APR_EXECUTADAS`: previstas multiplicadas por `APR / 100`.
- `APR_NAO_ADERENTES`: previstas menos executadas.
- `APR_PCT_NAO_ADERENTE`: não aderentes divididas pelas previstas.

### Backlog

O notebook renomeia as horas de backlog para conceitos analíticos, calcula
percentuais vencidos por categoria e calcula a evolução mensal por equipamento:

- `BACKLOG_TOTAL` e `BACKLOG_VENCIDO`.
- Percentuais vencidos geral, YPM, YCM, corretiva, prioridade 1 e prioridade 2.
- `BACKLOG_DELTA`: diferença mensal do backlog.
- `BACKLOG_CRESCIMENTO`: variação percentual mensal.

## Agregação

Os dados são agrupados por `ANO MÊS` e `GRUPO`:

- Indicadores de confiabilidade: média de `DF (REAL)`, `MTBF (REAL)`,
  `MTBS (REAL)`, `MTTR` e `NIC (VMINA)`.
- AMS, AMC e APR: médias para taxas e somas para contagens.
- Backlog: soma das horas e média dos percentuais vencidos.

O backlog recebe `QTD_ATIVOS`, calculado como quantidade distinta de
equipamentos por grupo. A partir disso são calculados `BACKLOG_POR_ATIVO` e
`BACKLOG_VENCIDO_POR_ATIVO`, além da evolução desses valores por grupo.

Depois dos merges, a base analítica registrada no notebook possui 35 colunas e
324 linhas. O primeiro merge, entre indicadores e AMS, é `inner`; AMC, APR e
backlog entram com `left`.

## Lags e Correlações

O notebook cria defasagens de zero a seis meses por grupo para 19 drivers:

- AMS: `AMS_00H`, `AMS_PENDENTES`, `AMS_PCT_PENDENTE`.
- AMC: `AMC_00I`, `AMC_NAO_ADERENTES`, `AMC_PCT_NAO_ADERENTE`.
- APR: `APR`, `APR_NAO_ADERENTES`, `APR_PCT_NAO_ADERENTE`.
- Backlog absoluto: backlog total e vencido por ativo.
- Backlog percentual: geral, YPM, YCM, corretiva, prioridade 1 e prioridade 2.
- Tendência: `BACKLOG_DELTA` e `BACKLOG_CRESCIMENTO`.

Para cada resposta e driver, são calculados Pearson e Spearman, com p-valores.
São descartados valores ausentes, variáveis constantes e combinações com menos
de 30 observações. A seleção de candidatos usa `p < 0,05` e correlação absoluta
maior ou igual a `0,10`.

As respostas são:

```text
DF (REAL), MTBF (REAL), MTBS (REAL), MTTR, NIC (VMINA)
```

## Modelos e Gráficos

Para cada resposta, o notebook seleciona até dez drivers, ajusta um modelo OLS
com intercepto e armazena os resultados. Os resultados registrados foram:

| Resposta | N | R² | R² ajustado |
|---|---:|---:|---:|
| `DF (REAL)` | 98 | 0,296 | 0,232 |
| `MTBF (REAL)` | 31 | 0,500 | 0,348 |
| `MTBS (REAL)` | 34 | 0,525 | 0,347 |
| `MTTR` | 69 | 0,113 | -0,005 |
| `NIC (VMINA)` | 33 | 0,632 | 0,489 |

Também são gerados dispersões, linhas de tendência, boxplots por quartil de
backlog e gráficos de observado versus previsto.

## Limitações Registradas

- Os resultados gravados no notebook são de uma execução anterior, com dados
  até junho de 2026.
- Há risco de multicolinearidade porque contagens, percentuais e taxas são
  algebricamente relacionadas.
- Alguns modelos têm amostras pequenas e números de condição elevados.
- Percentuais agregados são médias simples, não percentuais recalculados a
  partir dos totais.
- A regra de grupo depende da estrutura específica de `TPLNR05`.
