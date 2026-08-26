# Fontes de Indicadores de Confiabilidade

Este documento detalha os arquivos de indicadores mensais de confiabilidade da frota, suas variáveis-alvo, estrutura e requisitos de qualidade.

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

## 2. Variáveis-Alvo Modeladas

O pipeline modela e prevê cinco indicadores operacionais de confiabilidade para o mês subsequente ($t+1$):

1. **`DF (REAL)` — Disponibilidade Física Real:**
   * Proporção de tempo em que o equipamento esteve mecanicamente disponível para operação.
   * Fórmula conceitual: $(HT - (HMC + HM)) / HT$ ou equivalente apurado pela engenharia.
2. **`MTBF (REAL)` — Mean Time Between Failures:**
   * Tempo médio de operação entre falhas mecânicas/elétricas corretivas.
3. **`MTBS (REAL)` — Mean Time Between Stops:**
   * Tempo médio entre paradas (incluindo corretivas e preventivas).
4. **`MTTR` — Mean Time To Repair:**
   * Tempo médio de reparo por intervenção de manutenção.
5. **`NIC (VMINA)` — Número de Intervenções Corretivas:**
   * Volume total de manutenções corretivas não planejadas registradas no período.

---

## 3. Estrutura e Formatação dos Arquivos

* **Aba Obrigatória:** Todos os arquivos devem conter uma aba denominada `Export`.
* **Identificadores Chave:**
  * `ANO MÊS`: Período no formato `YYYYMM` (ou representação de data mensal).
  * `EQUIPAMENTO`: Tag/código do ativo (ex.: `CA-01`, `PF-03`, `ES-05`).
* **Estrutura de 26 Colunas:**
  ```text
  ANO MÊS, EQUIPAMENTO,
  DF (META), DF (REAL),
  MTBF (META), MTBF (REAL),
  MTBS (META), MTBS (REAL),
  MTTR (META), MTTR,
  NIC (META), NIC (VMINA),
  UF (META), UF (REAL),
  RO (META), RO (REAL),
  HO (REAL),
  HT (META), HT (REAL),
  HM (META), HM (REAL),
  HMC (META), HMC (REAL),
  MPS (REAL), MPNS (REAL), HAC (REAL)
  ```

---

## 4. Regras de Limpeza e Integridade Automatizadas

Durante a carga pelo módulo [`dados.py`](file:///home/marcus/projects/vale/trigger/modelo_confiabilidade/dados.py):
1. **Remoção de Linhas de Rodapé:** Linhas contendo agregadores físicos como `Total`, linhas em branco ou textos de filtros aplicados são descartadas automaticamente.
2. **Coerção Numérica Auditada:** Colunas numéricas com pontuação brasileira (vírgula decimal) são convertidas para ponto flutuante; qualquer valor incompatível é transformado em `NaN` e auditado no log.
3. **Padronização Temporal:** `ANO MÊS` é parseado e validado como períodos mensais (`pd.Period(freq="M")`).
