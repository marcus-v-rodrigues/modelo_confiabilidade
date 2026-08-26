# Dicionário de Correspondência

Este dicionário compara os nomes usados pelo notebook com os campos encontrados
nos arquivos atuais. `Direto` significa que o campo existe com o mesmo nome;
`derivado` indica que pode exigir transformação; `indefinido` significa que não
há equivalência confirmada apenas pela inspeção dos nomes.

Os nomes operacionais brutos são mantidos no pipeline. Em especial,
`IMAINDI*` recebe `status_semantico=nao_confirmado` até validação de negócio;
não se cria um alias AMS, AMC, APR ou backlog apenas pelo nome. A importância
do modelo é preditiva e não afirma causalidade.

## Indicadores de Confiabilidade

| Notebook | Arquivo atual | Status | Observação |
|---|---|---|---|
| `ANO MÊS` | `ANO MÊS` | Direto | Precisa ser convertido para uma data mensal no fluxo. |
| `EQUIPAMENTO` | `EQUIPAMENTO` | Direto | Presente nos quatro XLSX. |
| `DF (REAL)` | `DF (REAL)` | Direto | Usado como resposta. |
| `MTBF (REAL)` | `MTBF (REAL)` | Direto | Usado como resposta. |
| `MTBS (REAL)` | `MTBS (REAL)` | Direto | Usado como resposta. |
| `MTTR` | `MTTR` | Direto | Usado como resposta. |
| `NIC (VMINA)` | `NIC (VMINA)` | Direto | Usado como resposta. |
| `GRUPO` | Não existe nos XLSX | Derivado | Regra normal: penúltimo segmento do `TPLNR` operacional (`TPLNR[-2]`). |

## Chaves Temporais e de Equipamento

| Notebook | Atual | Status | Observação |
|---|---|---|---|
| `TPLNR05` | `TPLNR` | Derivado | Regra normal: `GRUPO=TPLNR[-2]` e `EQUIPAMENTO=TPLNR[-1]`; `--group-map-file` é apenas override explícito opcional. |
| `CALMONTH-Calendar_year_month` | `CALMONTH` | Derivado | Requer padronização para `ANO MÊS`. |
| `ANO MÊS` | `YEAR` + `CALMONTH` | Derivado | Pode ser reconstruído, preservando zeros e formato `YYYYMM`. |

## AMS

| Notebook | Atual | Status | Observação |
|---|---|---|---|
| `AMS_00H` | Não identificado diretamente | Indefinido | Definir se é campo bruto ou cálculo. |
| Campo bruto preservado | `IMAINDI383` | Indefinido | Não atribuir alias operacional antes de confirmar significado e agregação. |
| Campo bruto preservado | `IMAINDI384` | Indefinido | Não atribuir alias operacional antes de confirmar significado e agregação. |
| `AMS_PREVISTAS` | Contagem agregada de ordens | Derivado | O notebook espera uma tabela já agregada. |
| `AMS_EXECUTADAS` | Contagem agregada de fechadas | Derivado | O notebook calcula pendentes por diferença. |

## AMC

| Notebook | Atual | Status | Observação |
|---|---|---|---|
| `AMC_00I` | Não identificado diretamente | Indefinido | Não assumir equivalência com outro indicador. |
| Campo bruto preservado | `IMAINDI189_ACTUAL_NA` ou relacionados | Indefinido | Não atribuir alias operacional antes da validação da regra usada pela tabela original. |
| `AMC_PREVISTAS` | Contagem agregada de notificações | Derivado | Depende dos filtros de período e status. |
| `AMC_EXECUTADAS` | Previstas × `AMC_00I / 100` | Derivado | Fórmula existente no notebook. |

## APR

| Notebook | Atual | Status | Observação |
|---|---|---|---|
| `.APR` | `IMAINDI64` e relacionados | Indefinido | O nome parecido não comprova a mesma definição. |
| `IMAINDI64_TOT` | `IMAINDI64` | Indefinido | O campo atual não possui o sufixo `_TOT`. |
| `APR_PREVISTAS` | Total planejado agregado | Derivado | Requer definição do universo e dos filtros. |
| `APR_EXECUTADAS` | Previstas × `APR / 100` | Derivado | Fórmula existente no notebook. |

## Backlog

| Notebook | Atual | Status | Observação |
|---|---|---|---|
| `HH_EM CARTEIRA` | Indicadores `IMAINDI*` | Indefinido | Não há campo com o mesmo nome. |
| `hh_em_ordens_vencidas` | `IMAINDI37`, `IMAINDI38` ou relacionados | Indefinido | Exige validação da regra de vencimento. |
| YPM/YCM | Indicadores de backlog atuais | Indefinido | Não há correspondência nominal confirmada. |
| Corretiva | Indicadores de backlog atuais | Indefinido | Exige filtro por tipo de ordem. |
| Prioridade 1/2 | `PRIOK` e indicadores relacionados | Derivado | A prioridade existe, mas a métrica de horas vencidas precisa ser definida. |
| `BACKLOG_POR_ATIVO` | Backlog agregado / `QTD_ATIVOS` | Derivado | Fórmula existente no notebook. |
| `BACKLOG_DELTA` | Variação mensal | Derivado | Calculado após agregação por grupo. |
| `BACKLOG_CRESCIMENTO` | `pct_change()` mensal | Derivado | Valores infinitos são substituídos por `NaN` no agregado. |

## Convenções de Status

- **Direto:** nome e conceito estão presentes na fonte.
- **Derivado:** requer renomeação, combinação, filtro ou agregação.
- **Indefinido:** o nome atual pode ser relacionado, mas a regra de negócio não
  foi confirmada.
