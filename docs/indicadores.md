# Fontes de Indicadores de Confiabilidade

Este documento detalha os arquivos de indicadores mensais de confiabilidade da frota, suas definições oficiais, unidades de medida, escalas, regras de limpeza/expurgo e o papel das metas de planejamento.

---

## 1. Visão Geral das Fontes

Os indicadores de confiabilidade são disponibilizados em quatro pastas de trabalho Excel (`.xlsx`), correspondentes aos quatro universos de equipamentos da mina:

| Arquivo | Universo | Período Típico | Colunas | Registros Aprox. |
| :--- | :--- | :--- | :---: | :---: |
| `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx` | Caminhão Fora-de-Estrada | `202501`–`202608` | 26 | ~1.200 |
| `INDICADORES MENSAIS POR UNIVERSO carga.xlsx` | Equipamentos de Carga | `202501`–`202608` | 26 | ~240 |
| `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` | Perfuratrizes | `202501`–`202608` | 26 | ~270 |
| `INDICADORES MENSAIS POR UNIVERSO infra.xlsx` | Equipamentos de Infraestrutura | `202501`–`202608` | 26 | ~1.290 |

---

## 2. Definições Oficiais dos Indicadores, Unidades e Escalas

Todas as métricas seguem os padrões de engenharia e gestão de ativos:

| Indicador | Nome Completo | Unidade | Escala Válida | Descrição / Fórmula | Foco e Impacto Analítico |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **`DF`** | Disponibilidade Física | `%` | `[0, 100]` | $\text{DF} = \left(\frac{\text{Tempo Disponível}}{\text{Tempo Total}}\right) \times 100$ | *(A máquina está pronta para trabalhar?)* Impactada diretamente pela **manutenção preventiva**. |
| **`UF`** | Utilização Física | `%` | `[0, 100]` | $\text{UF} = \left(\frac{\text{Tempo Trabalhado}}{\text{Tempo Disponível}}\right) \times 100$ | *(A máquina disponível está sendo usada com eficiência?)* Impactada pelo **planejamento operacional**. |
| **`MTBF`** | Mean Time Between Failures | Horas | $\ge 0$ | Tempo médio de operação entre falhas mecânicas/elétricas corretivas. | Foco principal de correlação e confiabilidade. |
| **`MTBS`** | Mean Time Between Stoppages | Horas | $\ge 0$ | Tempo médio entre paradas (incluindo paradas corretivas e preventivas). | Indicador de estabilidade global. |
| **`MTTR`** | Mean Time to Repair | Horas | $\ge 0$ | Tempo médio de reparo por intervenção corretiva. | Eficiência da equipe de manutenção. |
| **`NIC`** | Número de Intervenções Corretivas | Quantidade | $\ge 0$ (Inteiro/Real) | Volume total de manutenções corretivas não planejadas no período. | Frequência de quebras. |
| **`RO`** | Rendimento Operacional | `%` | `[0, 100]` | Percentual de rendimento e produtividade operacional efetiva. | Performance de operação. |

> **Distinção Crítica entre DF e UF:**
> * **Disponibilidade Física (DF):** Percentual do tempo em que o equipamento está apto a operar, desconsiderando paradas por manutenção corretiva ou preventiva.
> * **Utilização Física (UF):** Percentual do tempo disponível que realmente foi utilizado em operação.
> * Uma gestão eficiente precisa acompanhar ambos simultaneamente: manutenção preventiva atua na DF, enquanto planejamento e despacho operacional atuam na UF.

---

## 3. Diretrizes de Modelagem Preditiva e Correlação

1. **Variáveis-Alvo Modeladas no Pipeline ($t+1$):**
   * `DF (REAL)`
   * `MTBF (REAL)`
   * `MTBS (REAL)`
   * `MTTR`
   * `NIC (VMINA)`
2. **Exclusão de UF da Previsão:**
   * Conforme diretriz operacional, a coluna `UF` é excluída do cálculo de previsão temporal.
3. **Foco de Correlação com Bases Operacionais:**
   * O pipeline prioriza **`MTBF`** e **`DF`** para as análises de correlação (Pearson e Spearman) contra contadores, ordens e backlog (com `MTBF` como foco prioritário caso seja necessário eleger uma única referência).

---

## 4. Papel das Colunas de Meta: Análise Real x Meta

* **Sem Vazamento de Informação:** As colunas terminadas em `(META)` (como `DF (META)`, `MTBF (META)`, `UF (META)`, etc.) representam metas de planejamento corporativo e são **estritamente excluídas** do conjunto de variáveis preditoras nos modelos de Machine Learning.
* **Finalidade Analítica:** São utilizadas exclusivamente para apurar a diferença entre o resultado efetivamente atingido versus o esperado pela companhia (**Real x Meta**):
  $$\text{Desvio Absoluto} = \text{Valor Real} - \text{Valor Meta}$$
  $$\text{Desvio Percentual} = \left(\frac{\text{Valor Real} - \text{Valor Meta}}{\text{Valor Meta}}\right) \times 100$$
  $$\text{Atingimento Percentual} = \left(\frac{\text{Valor Real}}{\text{Valor Meta}}\right) \times 100$$
* A tabela consolidada é salva em `real_x_meta.csv`.

---

## 5. Regras de Limpeza, Validação e Expurgo de Desvios

Durante a carga pelo módulo [`dados.py`](file:///home/marcus/projects/vale/trigger/modelo_confiabilidade/dados.py):
1. **Remoção de Linhas de Rodapé:** Linhas contendo agregadores físicos como `Total`, linhas em branco ou textos de filtros aplicados são descartadas automaticamente.
2. **Coerção Numérica Auditada:** Colunas com pontuação brasileira (vírgula decimal) são convertidas para ponto flutuante.
3. **Tratamento de Dados Ausentes em `UF (META)`:** Valores em branco/vazios são tratados como dados ausentes ou erros de cálculo na origem (`NaN`), sem imputação arbitrária na base bruta.
4. **Expurgo de Valores `inf` e Anomalias de Processo:**
   * Valores infinitos (`inf`, `-inf`), causados por erro de processo (como divisões por zero em horas nulas), são tratados como desvios de processo e **expurgados para `NaN`**.
   * Valores absurdamente grandes ou negativos encontrados em colunas percentuais (ex.: $6{,}58 \times 10^{14}$ e $-3{,}58 \times 10^{15}$ em `UF (META)` de infraestrutura) são identificados como erros de processo e **expurgados para `NaN`**, respeitando a escala oficial `[0, 100]`.
   * Todos os desvios expurgados são catalogados e auditados em `relatorio_qualidade_dados.csv`.
5. **Padronização Temporal:** `ANO MÊS` é parseado e validado como períodos mensais (`pd.Period(freq="M")`).
