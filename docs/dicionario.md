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

## 4. Chaves Primárias e Alinhamento

| Chave | Tipo | Descrição |
| :--- | :--- | :--- |
| **`GRUPO`** | `str` | Família/grupo operacional de equipamentos derivado do penúltimo segmento do `TPLNR`. |
| **`EQUIPAMENTO`** | `str` | Identificador único do ativo derivado do último segmento do `TPLNR` e presente nos XLSX. |
| **`MES` / `ANO MÊS`** | `Period[M]` | Período mensal de apuração dos dados no formato `YYYY-MM`. |
