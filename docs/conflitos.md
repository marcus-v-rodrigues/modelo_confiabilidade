# Histórico de Ajustes Técnicos e Semânticos

> **Nota:** Este documento registra o mapeamento técnico de migração entre as saídas preliminares do notebook e a estrutura de dados bruta do SAP adotada no pacote [`modelo_confiabilidade`](README.md).

---

## 1. Mapeamento de Nomes de Arquivos

| Nome Histórico (Notebook) | Arquivo Oficial em Produção | Universo / Função |
| :--- | :--- | :--- |
| `INDICADORES MENSAIS POR UNIVERSO.xlsx` | `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx` | Confiabilidade Caminhão |
| `INDICADORES MENSAIS POR UNIVERSO (2).xlsx` | `INDICADORES MENSAIS POR UNIVERSO carga.xlsx` | Confiabilidade Carga |
| `INDICADORES MENSAIS POR UNIVERSO (3).xlsx` | `INDICADORES MENSAIS POR UNIVERSO infra.xlsx` | Confiabilidade Infraestrutura |
| `INDICADORES MENSAIS POR UNIVERSO (4).xlsx` | `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` | Confiabilidade Perfuração |
| `AMS_ativos_mina.csv` | `AMS_Contador.csv` / `AMS_Calendario.csv` | Contadores e Calendário AMS |
| `AMC_ativos_mina.csv` | `AMC_ITABIRA.csv` | Notificações e Aderência AMC |
| `APR_ativos_mina.csv` | `APR_ITABIRA.csv` | Programação de Manutenção APR |
| `Backlog_imos_ativos_mina.csv` | `Backlog_mina_itabira.csv` | Carteira e Horas de Backlog |

---

## 2. Resolução da Hierarquia via `TPLNR`

No pipeline atual, o agrupamento de equipamentos é resolvido diretamente pela hierarquia do SAP:
* **`GRUPO = TPLNR.str.split("-")[-2]`**
* **`EQUIPAMENTO = TPLNR.str.split("-")[-1]`**

Essa regra elimina a necessidade de tabelas externas de de-para no fluxo padrão, mantendo consistência estrutural com a árvore de ativos da mina.

Para mais detalhes da arquitetura atual, consulte o [**`Pipeline de Modelagem`**](pipeline_modelagem.md).
