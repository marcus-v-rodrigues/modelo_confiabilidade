# Guia de Execução CLI e Catálogo de Saídas

Este guia detalha os parâmetros de execução do pacote `modelo_confiabilidade`, os modos de execução e o catálogo completo de artefatos gerados no diretório de resultados.

---

## 1. Como Executar

O pipeline é empacotado como um módulo Python executável:

```bash
# Execução padrão recomendada
python -m modelo_confiabilidade \
  --input-dir ./bases \
  --output-dir ./resultados \
  --test-months 3 \
  --max-lag 6
```

---

## 2. Referência Completa de Parâmetros da CLI

| Parâmetro | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| **`--input-dir`** | `Path` | `./bases` | Diretório onde estão os 4 arquivos XLSX de indicadores e os 5 CSVs operacionais. |
| **`--output-dir`** | `Path` | `./resultados` | Diretório onde todos os relatórios, CSVs, logs e gráficos são gerados. |
| **`--test-months`** | `int` | `3` | Quantidade de meses finais reservados para o teste fora da amostra (OOS). |
| **`--max-lag`** | `int` | `6` | Número máximo de meses de defasagem histórica ($t-1$ até $t-6$) gerados para as features. |
| **`--random-state`** | `int` | `42` | Semente para garantir reprodutibilidade exata em modelos e permutações estocásticas. |
| **`--group-map-file`** | `Path` | `None` | *Opcional:* Caminho para CSV de mapeamento manual (`EQUIPAMENTO`/`TPLNR` $\to$ `GRUPO`). Omitir para usar a regra padrão por hierarquia `TPLNR`. |
| **`--min-train-rows`** | `int` | `30` | Mínimo de observações necessárias no treino para permitir o ajuste de modelos. |
| **`--min-test-rows`** | `int` | `10` | Mínimo de observações necessárias no teste OOS para validação estatística. |
| **`--min-feature-non-null`** | `float` | `0.5` | Fração mínima de preenchimento de uma feature no período de treino para ela ser mantida. |
| **`--min-test-r2`** | `float` | `0.0` | $R^2$ mínimo no teste OOS para aprovação do modelo. |
| **`--max-test-mape`** | `float` | `100.0` | Limite máximo de MAPE (%) no teste OOS. |
| **`--min-baseline-improvement`** | `float` | `0.0` | Ganho mínimo percentual de MAE exigido sobre o baseline ingênuo de persistência. |
| **`--max-metric-cv`** | `float` | `1.0` | Limite de dispersão (CV) das métricas entre dobras temporais para assegurar estabilidade. |
| **`--max-vif`** | `float` | `10.0` | Limite máximo de VIF permitido antes de acusar multicolinearidade prejudicial. |

---

## 3. Modos de Execução

### A. Execução Completa (`status = "completed"`)
Ocorre quando:
1. Todas as fontes são lidas com sucesso e passam na auditoria de qualidade.
2. A hierarquia `TPLNR` é consistente e cobre todos os equipamentos.
3. Há meses suficientes com dados operacionais e de confiabilidade.

*Retorno:* Código `0` (sucesso). Gera todos os modelos, diagnósticos, gráficos e relatórios finais.

### B. Modo Somente Auditoria (`status = "audit_only"`)
Ocorre quando:
1. Há erros estruturais bloqueantes em arquivos (ex.: abas ausentes, corrupção).
2. Há falhas graves de hierarquia (equipamento associado a múltiplos grupos ou falta de cobertura).
3. Dados insuficientes para treinamento seguro.

*Retorno:* Código `1` (erro). O pipeline não treina modelos nem inventa resultados de ML; grava imediatamente o log, a auditoria de qualidade e o relatório textual explicativo apontando a causa raiz e a correção necessária.

---

## 4. Catálogo de Arquivos Gerados

Após a execução, o diretório configurado em `--output-dir` conterá:

### Arquivos Estruturais e de Auditoria
* **`auditoria_qualidade.csv`**: Registro completo de testes de integridade, conversões de tipo, severidades (`INFO`, `WARNING`, `ERROR`) e diagnósticos de dados.
* **`relatorio_qualidade_dados.csv`**: Sumário executivo por fonte de dados.
* **`validar_modelo.log`**: Log detalhado da execução com timestamps e mensagens operacionais.

### Arquivos de Modelagem e Métricas
* **`base_analitica.csv`**: Tabela analítica consolidada com variáveis de confiabilidade ($t+1$), features operacionais defasadas ($t-1 \dots t-6$), grupo e mês.
* **`metricas.csv`**: Métricas de performance (MAE, RMSE, MAPE, $R^2$) de cada modelo (Elastic Net, Random Forest e Baseline de Persistência) em treino e teste OOS.
* **`previsoes.csv`**: Série temporal completa de valores reais observados vs valores previstos por modelo para cada grupo e mês.
* **`classificacao.csv`**: Classificação conclusiva (`VALIDO`, `EXPLORATORIO`, `INVALIDO`) e justificativas para cada um dos 5 indicadores.

### Arquivos de Explicabilidade e Diagnósticos
* **`importancia.csv`**: Ranking de importância preditiva das variáveis operacionais no conjunto de teste OOS.
* **`coeficientes.csv`**: Coeficientes lineares regularizados do modelo Elastic Net.
* **`diagnosticos.csv`**: Resultados dos testes de multicolinearidade (VIF), normalidade e autocorrelação de resíduos.
* **`features_excluidas.csv`**: Lista de variáveis operacionais que foram descartadas (ex.: por vazamento temporal, cardinalidade ou esparsidade) e o motivo do descarte.
* **`cobertura_temporal.csv`**: Auditoria do horizonte temporal coberto por cada fonte e universo.

### Relatório Textual e Visualizações
* **`relatorio_final.txt`**: Relatório executivo consolidado com diagnóstico das fontes, performance comparativa contra o baseline, ranking de variáveis explicativas e recomendações.
* **Gráficos (`.png`)**:
  * `real_vs_previsto_<RESPOSTA>.png`: Gráficos de dispersão e aderência temporal no teste OOS.
  * `residuos_<RESPOSTA>.png`: Distribuição e dispersão dos resíduos de previsão.
  * `importancia_<RESPOSTA>.png`: Gráficos de barras com as variáveis operacionais mais influentes.
