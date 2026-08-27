# Modelo Preditivo de Confiabilidade de Ativos (`modelo_confiabilidade`)

Pipeline em Python para **auditoria de qualidade de dados**, **engenharia de atributos temporais** e **modelagem preditiva supervisionada** dos indicadores mensais de confiabilidade de frotas industriais e equipamentos de mina.

---

## 1. Propósito do Projeto

### O Desafio

Na gestão de ativos de mineração e operações industriais pesadas, a manutenção tradicional costuma atuar de forma reativa ou baseada em relatórios históricos defasados. Saber o que falhou no passado não é suficiente para planejar preventivamente a disponibilidade da frota.

### A Solução

Este pacote implementa um modelo de **Machine Learning de previsão temporal ($t \to t+1$)**. Ele utiliza o histórico recente de apontamentos operacionais do SAP (contadores de horas, cumprimento de planos de manutenção, notificações de anomalias, programação de atividades e horas de backlog acumulado) observados até o mês atual ($t$) para **prever os indicadores de confiabilidade do próximo mês ($t+1$)**.

```text
[ Dados Operacionais do SAP em t, t-1, ... t-6 ] ──► [ Modelo de ML ] ──► [ Previsão de Confiabilidade em t+1 ]
- Contadores e horímetros (AMS)                                           - Disponibilidade Física (DF)
- Cumprimento de planos (AMS/AMC)                                         - Tempo Médio Entre Falhas (MTBF)
- Aderência de programação (APR)                                          - Tempo Médio Entre Paradas (MTBS)
- Carteira e ordens vencidas (Backlog)                                    - Tempo Médio Para Reparo (MTTR)
                                                                          - Intervenções Corretivas (NIC)
```

---

## 2. Indicadores Modelados e Definições Oficiais

O modelo apura e projeta métricas fundamentais por grupo e equipamento com suas unidades e escalas oficiais:

1. **`DF (REAL)` — Disponibilidade Física Real (`%`, escala `[0, 100]`):** Proporção do tempo em que os equipamentos estão mecanicamente aptos para operação ($\text{DF} = (\text{Tempo disponível} / \text{Tempo total}) \times 100$). Impactada diretamente pela **manutenção preventiva**.
2. **`MTBF (REAL)` — Mean Time Between Failures (`Horas`, escala $\ge 0$):** Tempo médio de operação contínua entre ocorrências de falhas corretivas. **Foco prioritário de correlação**.
3. **`MTBS (REAL)` — Mean Time Between Stops (`Horas`, escala $\ge 0$):** Tempo médio entre paradas (preventivas ou corretivas).
4. **`MTTR` — Mean Time To Repair (`Horas`, escala $\ge 0$):** Duração média necessária para reparar um equipamento após uma parada.
5. **`NIC (VMINA)` — Número de Intervenções Corretivas (`Quantidade`, escala $\ge 0$):** Contagem de manutenções corretivas não programadas no mês.
6. **`UF (REAL)` — Utilização Física (`%`, escala `[0, 100]`):** Proporção do tempo disponível efetivamente trabalhado ($\text{UF} = (\text{Tempo trabalhado} / \text{Tempo disponível}) \times 100$). Impactada pelo **planejamento operacional**; desconsiderada da previsão temporal ($t+1$).
7. **`RO (REAL)` — Rendimento Operacional (`%`, escala `[0, 100]`):** Rendimento e produtividade operacional efetiva.
8. **Análise Real x Meta (`real_x_meta.csv`):** As colunas de meta `(META)` são segregadas dos preditores (sem vazamento) e utilizadas para comparar o atingimento real versus o planejamento corporativo.

---

## 3. Requisitos e Instalação

### Pré-requisitos

* **Python:** Versão 3.10, 3.11 ou 3.12.
* **Sistema Operacional:** Linux, macOS ou Windows.

### Passo a Passo de Instalação

1. **Clone ou acesse a pasta do repositório:**

   ```bash
   cd /caminho/para/modelo_confiabilidade
   ```
2. **Crie e ative um ambiente virtual:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. **Instale as dependências:**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## 4. Estrutura dos Dados de Entrada (`bases/`)

O pipeline consome 9 arquivos organizados no diretório de entrada (padrão `./bases`):

### A. Indicadores de Confiabilidade (4 arquivos Excel `.xlsx`)

Devem conter a aba `Export` com 26 colunas padronizadas (`ANO MÊS`, `EQUIPAMENTO`, `DF (REAL)`, `MTBF (REAL)`, etc.):

* `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx` (Caminhões Fora-de-Estrada)
* `INDICADORES MENSAIS POR UNIVERSO carga.xlsx` (Escavadeiras e Carregadeiras)
* `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` (Perfuratrizes)
* `INDICADORES MENSAIS POR UNIVERSO infra.xlsx` (Equipamentos de Infraestrutura/Apoio)

### B. Fontes Operacionais SAP (5 arquivos CSV delimitados por `;`)

Exportações com a coluna `TPLNR` (Local de Instalação no SAP):

* `AMS_Contador.csv`: Contadores de horímetro, leituras e limites.
* `AMS_Calendario.csv`: Calendário de planos de manutenção e ciclos.
* `AMC_ITABIRA.csv`: Notificações de manutenção e aderência AMC.
* `APR_ITABIRA.csv`: Programação e apontamento de atividades APR.
* `Backlog_mina_itabira.csv`: Ordens em carteira, criticidades e horas pendentes.

---

## 5. Como Executar o Modelo

### Execução Padrão

Para rodar o pipeline com todas as configurações padrão:

```bash
python -m modelo_confiabilidade
```

### Execução com Parâmetros Customizados

Você pode especificar diretórios de entrada/saída e calibrar parâmetros temporais:

```bash
python -m modelo_confiabilidade \
  --input-dir ./bases \
  --output-dir ./resultados \
  --test-months 3 \
  --max-lag 6 \
  --random-state 42
```

### Visualizar Todas as Opções e Ajuda da CLI

```bash
python -m modelo_confiabilidade --help
```

---

## 6. Parâmetros Principais da Linha de Comando

| Argumento                                |     Padrão     | Descrição                                                                                                                  |
| :--------------------------------------- | :--------------: | :--------------------------------------------------------------------------------------------------------------------------- |
| **`--input-dir`**                |   `./bases`   | Diretório contendo os 4 XLSX e 5 CSVs de entrada.                                                                           |
| **`--output-dir`**               | `./resultados` | Diretório onde serão gravados os relatórios, CSVs e gráficos.                                                            |
| **`--test-months`**              |      `3`      | Meses finais reservados para teste fora da amostra (OOS).                                                                    |
| **`--max-lag`**                  |      `6`      | Defasagem histórica máxima ($t-1$ a $t-6$) das features operacionais.                                                  |
| **`--random-state`**             |      `42`      | Semente para garantir reprodutibilidade matemática dos modelos.                                                             |
| **`--group-map-file`**           |     `None`     | *Opcional:* Caminho para CSV de mapeamento explícito. Se omitido, o agrupamento é derivado automaticamente do `TPLNR`. |
| **`--min-train-rows`**           |      `30`      | Quantidade mínima de linhas de treino necessárias.                                                                         |
| **`--min-test-rows`**            |      `10`      | Quantidade mínima de observações no teste OOS.                                                                            |
| **`--min-feature-non-null`**     |     `0.5`     | Fração mínima de preenchimento de uma feature no treino.                                                                  |
| **`--min-test-r2`**              |     `0.0`     | $R^2$ mínimo no teste para aprovação do modelo.                                                                         |
| **`--max-test-mape`**            |    `100.0`    | Limite máximo de erro percentual médio (MAPE %).                                                                           |
| **`--min-baseline-improvement`** |     `0.0`     | Ganho mínimo sobre o baseline ingênuo de persistência.                                                                    |
| **`--max-vif`**                  |     `10.0`     | Limite do Fator de Inflação da Variância (multicolinearidade).                                                            |

---

## 7. Entendendo os Modos de Execução e Quality Gates

O pipeline possui travas de segurança rigorosas (*Quality Gates*) para garantir a confiabilidade dos resultados:

1. **Modo Completo (`status = "completed"`):**

   * Os dados passam em todas as verificações estruturais e de hierarquia.
   * O pipeline executa a engenharia de features, treina os modelos (**Elastic Net** e **Random Forest**), compara contra o **Baseline de Persistência**, executa diagnósticos estatísticos (VIF, autocorrelação e resíduos) e gera os gráficos e relatórios.
2. **Modo Somente Auditoria (`status = "audit_only"`):**

   * Se for detectado erro estrutural grave (ex.: porcentagens > 100% em bases brutas, corrupção de abas, inconsistência de chaves), o pipeline **não inventa resultados de ML**.
   * Ele interrompe o treinamento, gera o relatório de auditoria detalhado (`auditoria_qualidade.csv`), registra o motivo no log e sai com código `1`, indicando exatamente o ponto a ser corrigido na fonte de dados.

---

## 8. Catálogo de Saídas Geradas (`resultados/`)

Quando a execução finaliza, o diretório de saída contém:

* **`relatorio_final.txt`**: Relatório executivo completo em formato texto com diagnósticos, performance dos modelos e recomendações.
* **`auditoria_qualidade.csv`**: Registro auditável de todas as colunas, tipos, nulos e anomalias estruturais.
* **`base_analitica.csv`**: Base consolidada de treino e teste com alvos ($t+1$) e variáveis operacionais defasadas.
* **`metricas.csv`**: MAE, RMSE, MAPE e $R^2$ de cada modelo no treino e no teste fora da amostra (OOS).
* **`previsoes.csv`**: Comparativo mensal por grupo entre o valor real e os valores previstos por cada modelo.
* **`importancia.csv`**: Ranking de importância preditiva das variáveis operacionais no teste OOS.
* **`classificacao.csv`**: Parecer final do modelo para cada variável (`VALIDO`, `EXPLORATORIO` ou `INVALIDO`).
* **Gráficos (`.png`)**:
  * `real_vs_previsto_*.png`: Curvas de aderência temporal no teste cego.
  * `residuos_*.png`: Análise da distribuição dos erros.
  * `importancia_*.png`: Gráficos de barras com as variáveis mais influentes.

---

## 9. Como Executar a Suíte de Testes

O projeto possui 105 testes automatizados cobrindo leitura, auditoria, derivação de `TPLNR`, integridade temporal, expurgo de desvios, análise Real x Meta e modelagem:

```bash
# Execução simples
pytest

# Execução resumida
pytest -q
```

---

## 10. Arquitetura do Código

```text
modelo_confiabilidade/
├── __init__.py           # Identificador do pacote Python
├── __main__.py           # Entry point (orquestrador da execução CLI)
├── configuracao.py       # Configurações, dataclass Config e parse_args
├── dados.py              # Leitura de XLSX/CSVs, hierarquia TPLNR e lags
├── auditoria.py          # Quality gates e relatórios de integridade
├── modelagem.py          # Elastic Net, Random Forest, Baseline e validação OOS
├── diagnosticos.py       # Diagnósticos estatísticos, VIF e classificação
└── relatorios.py         # Exportação de CSVs, gráficos PNG e relatório TXT
```

---

## 11. Documentação Técnica Completa

Para aprofundar nos fundamentos matemáticos, regras de negócio e detalhes de implementação, consulte a pasta [`docs/`](docs/):

* [**Visão Geral da Documentação**](docs/README.md)
* [**Pipeline de Modelagem e Validação Temporal**](docs/pipeline_modelagem.md)
* [**Diagnósticos Estatísticos e Critérios de Validade**](docs/diagnosticos_e_validacao.md)
* [**Guia Completo da CLI e Catálogo de Saídas**](docs/cli_e_resultados.md)
* [**Fontes de Indicadores de Confiabilidade**](docs/indicadores.md)
* [**Fontes Operacionais SAP**](docs/operacionais.md)
* [**Dicionário de Dados e Metadados de Features**](docs/dicionario.md)
* [**Evolução Arquitetural do Projeto**](docs/evolucao_e_contexto.md)
