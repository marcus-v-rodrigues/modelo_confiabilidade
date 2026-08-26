# Fontes Operacionais de Manutenção e Produção

Este documento detalha as cinco fontes operacionais brutas exportadas do SAP, suas características estruturais, campos principais e processo de agregação.

---

## 1. Visão Geral das Fontes

As bases operacionais são arquivos CSV detalhados no nível de transação, ordem de manutenção, notificação ou item de planejamento:

| Fonte | Arquivo | Registros Aprox. | Colunas | Foco Operacional |
| :--- | :--- | :---: | :---: | :--- |
| **AMS Contador** | `AMS_Contador.csv` | ~70.800 | 157 | Apontamento de contadores, horímetros, leituras e limites operacionais. |
| **AMS Calendário** | `AMS_Calendario.csv` | ~63.500 | 134 | Calendário de planos de manutenção, ciclos programados e datas de execução. |
| **AMC** | `AMC_ITABIRA.csv` | ~101.500 | 117 | Notificações de manutenção, aderência de planejamento e estados de ordem. |
| **APR** | `APR_ITABIRA.csv` | ~135.700 | 109 | Programação e execução de atividades de manutenção da mina. |
| **Backlog** | `Backlog_mina_itabira.csv` | ~306.000 | 129 | Ordens em carteira, horas pendentes, criticidade e ordens vencidas. |

---

## 2. Características Técnicas Comuns

* **Formato:** Arquivos CSV delimitados por ponto e vírgula (`;`).
* **Codificação:** UTF-8 com suporte automático a BOM (`utf-8-sig`).
* **Período Coberto nas Exportações Atuais:** `202505` a `202608`.
* **Identificador de Hierarquia:** Campo `TPLNR` (Local de Instalação no SAP).
* **Identificadores Temporais:** Combinações de `CALMONTH`, `YEAR`, `AMSYEAR` + `AMSMON`, etc.

---

## 3. Campos Principais por Fonte

### 1. AMS Contador (`AMS_Contador.csv`)
* **Chaves e Estrutura:** `TPLNR`, `EQUNR`, `POINT`, `READG`, `PYEAR`, `IDATE`.
* **Indicadores Brutos:** `IMAINDI383`, `IMAINDI384`, `IMAINDI385`, contadores acumulados e deltas operacionais.

### 2. AMS Calendário (`AMS_Calendario.csv`)
* **Chaves e Datas:** `TPLNR`, `AMSYEAR`, `AMSMON`, `AMSWEEK`, `AMSDAY_DATE`, `AMSCALC`.
* **Indicadores e Status:** `ITOSMPT`, `ITEOSMPT`, `IMAINDI265`, `IMAINDI292`, `IMAINDI370`, `IMAINDI378`, `IMAINDI382`.

### 3. AMC Itabira (`AMC_ITABIRA.csv`)
* **Chaves e Notificações:** `TPLNR`, `QMNUM`, `STRMN`, `LTRMN`, `AMCYEAR`, `AMCMON`, `AMCCALC`.
* **Aderência e Indicadores:** `IMAINDI189`, `IMAINDI189_ACTUAL`, `IMAINDI189_ACTUAL_NA`, `IMAINDI190`, `AMCCALC_NA`.

### 4. APR Itabira (`APR_ITABIRA.csv`)
* **Chaves e Operações:** `TPLNR`, `VORNR`, `AUFPL`, `APLZL`, `FSAVD`, `WWSDT`, `WWFDT`.
* **Indicadores:** `IMAINDI63`, `IMAINDI64`, `IMAINDI65`, unidades de medida e tempos programados.

### 5. Backlog Mina Itabira (`Backlog_mina_itabira.csv`)
* **Chaves e Ordens:** `TPLNR`, `PRIOK` (prioridade), `LTRMN`, `DATA_VENCIMENTO_NEW`, `DIAS_PARA_VENC_NEW`, `VENC_NEW`.
* **Indicadores de Horas e Carteira:** `IMAINDI37`, `IMAINDI38`, `IMAINDI266`, `IMAINDI354`, `IMAINDI381`, `IMAINDI389`, `IMAINDI390`, `IMAINDI401`.

---

## 4. Estratégia de Agregação e Isolamento de Fontes

Para evitar a multiplicação espúria de registros (explosão combinatorial de linhas decorrente de cruzamentos entre ordens e notificações não normalizadas):
1. **Agregação Isolada:** Cada uma das cinco bases operacionais é agrupada individualmente por `GRUPO` e `MES` antes de qualquer join.
2. **Transformações Suportadas:** Soma (`sum`), média (`mean`) e contagem (`count`) de transações ativas no período.
3. **Preservação de Nomenclatura:** Os nomes originais das colunas são preservados no formato `<FONTE>__<CAMPO>_<AGREGACAO>` (ex.: `AMS_Contador__IMAINDI383_sum`), garantindo rastreabilidade completa até o campo de origem no SAP.
