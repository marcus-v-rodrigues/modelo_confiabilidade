# Evolução Arquitetural e Contexto do Projeto

Este documento registra a evolução do projeto, saindo de um estudo exploratório inicial em notebook para uma arquitetura robusta de aprendizado de máquina supervisionado e previsão temporal no pacote `modelo_confiabilidade`.

---

## 1. O Estudo Exploratório Inicial (Notebook)

O projeto iniciou-se com a exploração contida em `Correlacao_AMS_DF_frota.ipynb`, cujo objetivo era investigar se indicadores de manutenção (AMS, AMC, APR e Backlog) possuíam correlação estatística com os indicadores de confiabilidade (`DF`, `MTBF`, `MTBS`, `MTTR`, `NIC`).

### Limitações da Abordagem Inicial:
1. **Correlação Contemporânea e Risco de Vazamento:** O estudo inicial calculava correlações e regressões no mesmo mês ($t \to t$), o que não permite prever o futuro operacional e introduz risco de utilizar informações contemporâneas ou posteriores.
2. **Multicolinearidade e Relações Algébricas:** Variáveis construídas por soma e subtração (ex.: `previstas`, `executadas`, `pendentes`) eram incluídas simultaneamente em regressões OLS lineares sem regularização, elevando o número de condição e inflando a variância dos coeficientes (VIF extremo).
3. **Ausência de Validação Fora da Amostra (OOS):** As métricas de $R^2$ eram apuradas em amostra (*in-sample*), sem teste cego em períodos futuros para aferir capacidade de generalização real.
4. **Dependência de Mapeamentos Manuais e Nomes Específicos:** O código dependia de aliases fixos e planilhas pré-agregadas que não refletiam as exportações brutas do SAP.

---

## 2. A Arquitetura do Pacote `modelo_confiabilidade`

Para transformar o estudo em uma ferramenta confiável e utilizável em produção, o sistema foi totalmente remodelado com os seguintes pilares:

### 1. Previsão Temporal Verdadeira ($t \to t+1$)
* Toda a modelagem foi reestruturada para **prever o próximo mês** a partir das informações conhecidas até o mês atual, permitindo planejamento proativo de manutenção.

### 2. Validação Temporal Rígida (Out-of-Sample)
* Separação estrita entre conjunto de treino e conjunto de teste OOS nos meses mais recentes.
* Comparação obrigatória contra o **Baseline de Persistência** ($y_{t+1} = y_t$). Modelos que não superam a persistência ingênua são classificados como inválidos.

### 3. Modelagem Regularizada e Não Linear
* Substituição do OLS simples por **Elastic Net** (com penalidades L1/L2 para lidar com colinearidade) e **Random Forest** (para capturar interações não lineares).

### 4. Derivação Hierárquica Automática (`TPLNR`)
* Extração determinística de grupo e equipamento diretamente da árvore do SAP (`TPLNR`), eliminando a necessidade de manutenção manual de tabelas de grupos.

### 5. Quality Gates e Auditoria Completa
* Implementação de verificações automáticas de integridade de dados, testes de resíduos (Durbin-Watson, Breusch-Pagan, Jarque-Bera), VIF e relatórios de auditoria que impedem o treinamento com dados corrompidos.
