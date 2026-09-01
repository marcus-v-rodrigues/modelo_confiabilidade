# Diagnósticos Estatísticos e Critérios de Validade

Este documento detalha os diagnósticos econométricos, testes estatísticos de resíduos, cálculo de importância preditiva fora da amostra e os critérios de validação do modelo implementados no módulo [`diagnosticos.py`](../modelo_confiabilidade/diagnosticos.py).

---

## 1. Importância Preditiva Fora da Amostra (OOS)

O modelo avalia a contribuição das variáveis explicativas exclusivamente sobre o conjunto de teste final (Out-of-Sample):

* **Permutation Importance OOS:** Mede o aumento do erro de previsão quando os valores de uma feature específica são aleatorizados no conjunto de teste.
* **Coeficientes Elastic Net:** Registrados como magnitude e direção da influência linear penalizada.
* **Distinção Fundamental:** A importância das variáveis reflete **contribuição preditiva** para estimar o indicador no mês seguinte ($t+1$), não prova de causalidade física ou mecânica.

---

## 2. Bateria de Diagnósticos Estatísticos

Para cada variável-alvo modelada, são executados os seguintes diagnósticos para verificar a robustez matemática e as premissas dos resíduos:

### 1. Fator de Inflação da Variância (VIF)
* **Objetivo:** Detectar multicolinearidade severa entre as variáveis operacionais e seus lags.
* **Critério de Alerta:** $\text{VIF} > \text{max\_vif}$ (padrão: $10.0$). Features com alta colinearidade são sinalizadas.

### 2. Autocorrelação de Resíduos (Durbin-Watson e autocorrelação simples)
* **Objetivo:** Verificar se os erros de previsão são temporalmente independentes (ruído branco) ou se ainda contêm dinâmica temporal não capturada.
* **Estatística de Durbin-Watson:** Valores próximos a $2.0$ indicam ausência de autocorrelação de 1ª ordem.

### 3. Heteroscedasticidade (Breusch-Pagan)
* **Objetivo:** Avaliar se a variância dos resíduos é constante ao longo do tempo e dos níveis de previsão.

### 4. Normalidade dos Resíduos (Jarque-Bera)
* **Objetivo:** Avaliar a assimetria e curtose da distribuição dos erros de previsão.

### 5. Estabilidade Temporal (Coeficiente de Variação das Métricas)
* **Objetivo:** Medir a estabilidade da acurácia entre diferentes dobras da validação temporal:
  $$\text{CV}_{\text{métrica}} = \frac{\sigma_{\text{MAE}}}{\mu_{\text{MAE}}}$$
* **Critério de Alerta:** $\text{CV} > \text{max\_metric\_cv}$ (padrão: $1.0$).

---

## 3. Critérios de Classificação do Modelo

Ao término da validação temporal e dos diagnósticos, cada resposta de confiabilidade recebe uma classificação conclusiva:

```text
                                 [ Avaliação do Modelo ]
                                            │
                        ┌───────────────────┴───────────────────┐
                        ▼                                       ▼
             Atende a todos os gates?                 Viola algum gate?
                        │                                       │
                        ▼                                       ▼
                   [ VALIDO ]                        Supera baseline mas
                        │                            tem violação moderada?
                        │                                       │
                        │                           ┌───────────┴───────────┐
                        │                           ▼                       ▼
                        │                   [ EXPLORATORIO ]           [ INVALIDO ]
```

### Categorias de Status:
1. **`VALIDO`**:
   * O modelo de Machine Learning supera com folga o baseline de persistência ($\text{MAE}_{\text{modelo}} < \text{MAE}_{\text{baseline}} \times (1 - \text{min\_baseline\_improvement})$).
   * $R^2 \ge \text{min\_test\_r2}$ (padrão: $0.0$).
   * $\text{MAPE} \le \text{max\_test\_mape}$ (padrão: $100.0\%$).
   * Coeficiente de variação das métricas $\le \text{max\_metric\_cv}$ (padrão: $1.0$).
   * $\text{VIF} \le \text{max\_vif}$ (padrão: $10.0$).
   * Ausência de risco de vazamento temporal (*leakage*).
   * Amostra de teste suficiente ($\ge \text{min\_test\_rows}$).

2. **`EXPLORATORIO`**:
   * O modelo apresenta ganhos preditivos relevantes ou sinal identificável, mas possui limitações amostrais ou violações leves de premissas estatísticas (ex.: VIF ligeiramente elevado ou variância moderada entre janelas).

3. **`INVALIDO`**:
   * O modelo não supera a persistência ingênua (isto é, o erro é maior que repetir o mês anterior).
   * Amostra insuficiente de treino ou teste.
   * Violação grave de thresholds de erro ($R^2 < 0$, $\text{MAPE} > 100\%$, instabilidade temporal extrema).
   * Detecção de risco de vazamento de dados.

---

## 4. Rastreabilidade e Auditoria Contínua

Todos os diagnósticos, valores observados, limites de tolerância e eventuais violações são registrados detalhadamente no arquivo `diagnosticos_estatisticos.csv` e consolidados no sumário executivo em `relatorio_final.txt`.
