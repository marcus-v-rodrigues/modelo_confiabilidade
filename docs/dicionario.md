# Dicionário de Dados e Metadados de Features

Este documento apresenta a estrutura de metadados, convenções de nomenclatura e catálogo de variáveis do pipeline preditivo de confiabilidade.

---

## 1. Convenções de Nomenclatura

Para garantir total rastreabilidade entre os dados brutos e os preditores nos modelos de Machine Learning, as variáveis geradas seguem uma convenção determinística:

### Padrão de Nomenclatura de Features
```text
<FONTE>__<CAMPO_ORIGINAL>_<AGREGACAO>_lag_<N>
```

* **`<FONTE>`**: Nome da fonte operacional de origem (`AMS_Contador`, `AMS_Calendario`, `AMC_ITABIRA`, `APR_ITABIRA`, `Backlog_mina_itabira`).
* **`<CAMPO_ORIGINAL>`**: Nome do campo extraído diretamente do arquivo SAP (ex.: `IMAINDI383`, `IMAINDI64`, `IMAINDI37`).
* **`<AGREGACAO>`**: Função de agregação mensal utilizada (`sum`, `mean`, `count`, etc.).
* **`lag_<N>`**: Quantidade de meses de defasagem histórica ($N \in [1, \text{max\_lag}]$).

---

## 2. Metadados de Features (`mapeamento_features`)

Cada feature gerada no pipeline possui uma linha de metadados registrada na base e nos relatórios de auditoria com os seguintes atributos:

| Atributo | Descrição | Exemplo |
| :--- | :--- | :--- |
| **`feature`** | Nome final da variável no dataset analítico | `AMS_Contador__IMAINDI383_sum_lag_1` |
| **`fonte`** | Arquivo operacional de origem | `AMS_Contador` |
| **`campo_original`** | Campo de origem no SAP | `IMAINDI383` |
| **`transformacao`** | Função aplicada na agregação | `sum` |
| **`lag`** | Defasagem temporal em meses | `1` |
| **`risco_vazamento`** | Avaliação de risco de vazamento temporal (`baixo`, `medio`, `alto`, `confirmado`) | `baixo` |
| **`status_semantico`** | Validação de negócio do significado (`confirmado`, `nao_confirmado`) | `nao_confirmado` |

---

## 3. Classificação de Status Semântico

* **`confirmado`**: O campo teve sua fórmula, regras de filtro, unidade de medida e significado de engenharia formalmente homologados pela equipe técnica.
* **`nao_confirmado`**: O campo é tratado pelo modelo puramente como um sinal estatístico/numérico. Sua importância preditiva é medida matematicamente, mas o pipeline **não assume aliases arbitrários** (como chamar `IMAINDI383` de `AMS_00H` sem validação explícita).

---

## 4. Catálogo de Indicadores e Variáveis de Confiabilidade

| Indicador | Unidade | Escala | Papel no Pipeline | Descrição |
| :--- | :---: | :---: | :--- | :--- |
| **`DF (REAL)`** | `%` | `[0, 100]` | Resposta Preditiva ($t+1$) e Correlação | Disponibilidade Física apurada. Impacto de manutenção preventiva. |
| **`MTBF (REAL)`** | Horas | $\ge 0$ | Resposta Preditiva ($t+1$) e Foco Principal de Correlação | Mean Time Between Failures apurado (tempo médio entre falhas). |
| **`MTBS (REAL)`** | Horas | $\ge 0$ | Resposta Preditiva ($t+1$) | Mean Time Between Stops (tempo médio entre paradas). |
| **`MTTR`** | Horas | $\ge 0$ | Resposta Preditiva ($t+1$) | Mean Time to Repair (tempo médio de reparo). |
| **`NIC (VMINA)`** | Quantidade | $\ge 0$ | Resposta Preditiva ($t+1$) | Número de Intervenções Corretivas não planejadas. |
| **`UF (REAL)`** | `%` | `[0, 100]` | Avaliação Real x Meta (Excluído da Previsão) | Utilização Física apurada. Impacto de planejamento operacional. |
| **`RO (REAL)`** | `%` | `[0, 100]` | Avaliação Real x Meta | Rendimento Operacional apurado. |
| **`* (META)`** | Variada | Conforme métrica | Avaliação Real x Meta (Excluído dos Preditores) | Metas corporativas de planejamento para DF, MTBF, MTBS, MTTR, NIC, UF, RO, HT, HM, HMC. |

---

## 5. Chaves Primárias e Alinhamento

| Chave | Tipo | Descrição |
| :--- | :--- | :--- |
| **`GRUPO`** | `str` | Família/grupo operacional de equipamentos derivado do penúltimo segmento do `TPLNR`. |
| **`EQUIPAMENTO`** | `str` | Identificador único do ativo derivado do último segmento do `TPLNR` e presente nos XLSX. |
| **`MES` / `ANO MÊS`** | `Period[M]` | Período mensal de apuração dos dados no formato `YYYY-MM`. |
