# Contexto Histórico: O Notebook Exploratório Inicial

> **Nota:** Este documento registra o comportamento do estudo exploratório inicial realizado em [`../Correlacao_AMS_DF_frota.ipynb`](../Correlacao_AMS_DF_frota.ipynb). A documentação oficial da versão atual em produção está disponível em [**`README.md`**](README.md) e [**`Evolução Arquitetural`**](evolucao_e_contexto.md).

---

## 1. Escopo da Análise Inicial

O notebook original relacionava indicadores mensais de confiabilidade de equipamentos (`DF`, `MTBF`, `MTBS`, `MTTR` e `NIC`) com métricas de manutenção planejada, notificações e backlog em nível contemporâneo ($t \to t$).

## 2. Entradas Históricas Esperadas

Na versão do notebook, esperavam-se arquivos genéricos pré-agregados:
* `INDICADORES MENSAIS POR UNIVERSO.xlsx` (e suas variantes numeradas)
* `AMS_ativos_mina.csv`
* `AMC_ativos_mina.csv`
* `APR_ativos_mina.csv`
* `Backlog_imos_ativos_mina.csv`

## 3. Limitações que Motivaram o Desenvolvimento do Pacote `modelo_confiabilidade`

* **Sem previsão temporal ($t+1$):** Calculava apenas correlações no mesmo mês de referência.
* **Multicolinearidade severa:** Incluía variáveis correlacionadas algebricamente em regressões lineares sem regularização.
* **Falta de validação fora da amostra (OOS):** As métricas de acurácia eram restritas ao conjunto de treino.

Essas limitações foram superadas pela arquitetura implementada no pacote [`modelo_confiabilidade`](pipeline_modelagem.md).
