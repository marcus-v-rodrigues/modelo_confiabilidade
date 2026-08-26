# Histórico de Atualização das Bases de Dados

> **Nota:** Este documento registra o histórico de atualização das bases de dados, comparando os recortes temporais antigos (`até 2026-06`) com a fotografia oficial consolidada (`até 2026-08`) consumida pelo pacote [`modelo_confiabilidade`](README.md).

---

## 1. Atualização dos Indicadores de Confiabilidade

As bases de indicadores foram atualizadas para o período completo de `2025-01` a `2026-08`. Todos os 4 arquivos possuem 26 colunas padronizadas e a aba oficial `Export`:

| Universo | Arquivo Atual | Período | Registros | Equipamentos Ativos |
| :--- | :--- | :---: | ---: | ---: |
| **Caminhão** | `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx` | `202501`–`202608` | 1.202 | 69 |
| **Carga** | `INDICADORES MENSAIS POR UNIVERSO carga.xlsx` | `202501`–`202608` | 241 | 15 |
| **Infra** | `INDICADORES MENSAIS POR UNIVERSO infra.xlsx` | `202501`–`202608` | 1.293 | 74 |
| **Perfuração** | `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` | `202501`–`202608` | 271 | 19 |

---

## 2. Bases Operacionais SAP

As exportações operacionais brutas cobrem o período de `2025-05` a `2026-08`:

| Fonte | Arquivo | Registros | Colunas |
| :--- | :--- | ---: | ---: |
| **AMS Contador** | `AMS_Contador.csv` | 70.786 | 157 |
| **AMS Calendário** | `AMS_Calendario.csv` | 63.476 | 134 |
| **AMC** | `AMC_ITABIRA.csv` | 101.519 | 117 |
| **APR** | `APR_ITABIRA.csv` | 135.729 | 109 |
| **Backlog** | `Backlog_mina_itabira.csv` | 306.004 | 129 |

---

## 3. Janela de Modelagem

Como os modelos preditivos exigem tanto os indicadores de confiabilidade quanto as variáveis operacionais explicativas, a janela temporal elegível para treinamento e teste corresponde à interseção comum entre as fontes (`202505` a `202608`). Meses anteriores dos XLSX sem registros operacionais correspondentes são automaticamente descartados da modelagem.
