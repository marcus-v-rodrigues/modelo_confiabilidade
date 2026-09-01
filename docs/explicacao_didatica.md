# Explicação didática do projeto

## 1. Em uma frase

Este projeto lê dados de manutenção e operação de equipamentos de mina, verifica se esses dados são confiáveis, organiza-os por grupo e mês e tenta **prever o indicador de confiabilidade do mês seguinte**.

Exemplo:

> Com os dados de manutenção observados até janeiro, o sistema tenta prever o MTBF, a DF ou outro indicador de fevereiro.

O sistema é um apoio analítico. Ele **não decide sozinho** quando fazer uma manutenção e não prova que uma variável causou uma falha.

---

## 2. O que o código está fazendo

O fluxo principal está em `modelo_confiabilidade/__main__.py` e funciona como uma linha de produção:

```text
Arquivos de entrada
        ↓
Leitura e padronização
        ↓
Auditoria de qualidade
        ↓
Identificação de equipamento e grupo
        ↓
Agregação por grupo e mês
        ↓
Criação do histórico (lags)
        ↓
Treinamento e teste dos modelos
        ↓
Diagnósticos, classificações e relatórios
```

São analisados cinco alvos:

- **DF (REAL)**: Disponibilidade Física, em percentual.
- **MTBF (REAL)**: tempo médio entre falhas, em horas.
- **MTBS (REAL)**: tempo médio entre paradas, em horas.
- **MTTR**: tempo médio para reparar, em horas.
- **NIC (VMINA)**: número de intervenções corretivas.

A **UF (Utilização Física)** não entra na previsão temporal, conforme a regra do projeto. Ela pode aparecer na análise de Real x Meta.

---

## 3. Arquivos de entrada

O diretório padrão é `bases/`.

### 3.1 Indicadores de confiabilidade

São quatro planilhas Excel. Todas devem ter a aba `Export`:

| Arquivo                                              | Universo                               |
| ---------------------------------------------------- | -------------------------------------- |
| `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx`   | Caminhões fora de estrada             |
| `INDICADORES MENSAIS POR UNIVERSO carga.xlsx`      | Escavadeiras e carregadeiras           |
| `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` | Perfuratrizes                          |
| `INDICADORES MENSAIS POR UNIVERSO infra.xlsx`      | Equipamentos de infraestrutura e apoio |

Essas planilhas fornecem os resultados de confiabilidade e suas metas mensais.

### 3.2 Dados operacionais do SAP

São cinco arquivos CSV, separados por ponto e vírgula (`;`):

| Arquivo                      | O que representa                                              |
| ---------------------------- | ------------------------------------------------------------- |
| `AMS_Contador.csv`         | Horímetros, contadores e leituras                            |
| `AMS_Calendario.csv`       | Planos e ciclos de manutenção                               |
| `AMC_ITABIRA.csv`          | Notificações e aderência de manutenção                   |
| `APR_ITABIRA.csv`          | Programação e execução de atividades                      |
| `Backlog_mina_itabira.csv` | Ordens pendentes, vencimentos, criticidade e horas em backlog |

Os dados operacionais são detalhados — normalmente uma linha por ordem, atividade, notificação ou leitura — e precisam ser resumidos antes de serem usados no modelo.

---

## 4. O que cada parte do código faz

### `__main__.py` — coordenador

É o ponto de entrada de `python -m modelo_confiabilidade`. Ele chama as demais partes na ordem correta:

1. Lê as quatro planilhas e os cinco CSVs.
2. Normaliza os indicadores.
3. Executa a auditoria.
4. Cria o relacionamento entre equipamento e grupo.
5. Cria as variáveis mensais e históricas.
6. Executa um modelo para cada indicador-alvo.
7. Gera diagnósticos, arquivos CSV, gráficos e relatório final.
8. Retorna código `0` quando conclui e `1` quando há erro ou insuficiência.

### `configuracao.py` — configurações e comandos

Define os arquivos esperados, os valores padrão, os parâmetros da linha de comando e o registro de logs. Também valida parâmetros como quantidade de meses e limites numéricos.

### `dados.py` — preparação dos dados

Faz quatro trabalhos principais:

- **Leitura:** Excel pela aba `Export`; CSV com separador `;` e codificação UTF-8.
- **Limpeza:** remove linhas vazias, rodapés e marcadores como `TOTAL` e `FILTRO`; converte números com vírgula decimal.
- **Validação:** transforma datas em períodos mensais, expurga infinitos, percentuais fora de `0` a `100` e indicadores negativos quando não fazem sentido.
- **Criação de variáveis:** resume as fontes por `GRUPO × MES` e cria as defasagens históricas.

### `auditoria.py` — controle de qualidade

Procura problemas estruturais e de conteúdo, como arquivo inválido, coluna essencial ausente, nulos, duplicidades, valores fora da escala e inconsistências. Cada ocorrência recebe severidade, por exemplo `INFO`, `WARNING` ou `ERROR`.

Um `ERROR` estrutural bloqueia a modelagem. Nesse caso, o sistema entra em modo **somente auditoria**, para não produzir uma previsão baseada em dados defeituosos.

### `modelagem.py` — treinamento e validação

Prepara o alvo futuro, separa passado e teste recente, treina os modelos e calcula as métricas de erro. O treinamento ocorre separadamente para cada um dos cinco indicadores.

### `diagnosticos.py` — avaliação e explicação

Calcula a importância das variáveis, coeficientes do Elastic Net, VIF, testes sobre resíduos e estabilidade entre janelas temporais. Depois atribui uma classificação: `VALIDO`, `EXPLORATORIO` ou `INVALIDO`.

### `relatorios.py` — resultados

Salva tabelas CSV, gráficos PNG e o relatório textual `relatorio_final.txt`. Também calcula a comparação entre o valor real e a meta e as correlações entre indicadores e variáveis operacionais.

### `Correlacao_AMS_DF_frota.ipynb` e PDF

São materiais de análise exploratória/documentação. A execução oficial e reproduzível do pipeline ocorre pelo pacote `modelo_confiabilidade`.

---

## 5. Como o sistema faz

### 5.1 Padronização e limpeza

Os nomes das colunas são aparados, meses como `202501` são convertidos para períodos mensais e números são convertidos para formato numérico.

Linhas de totalização ou filtros exportados junto com a planilha não são tratadas como equipamentos. Valores impossíveis são transformados em ausentes (`NaN`) e registrados na auditoria, em vez de serem silenciosamente usados.

### 5.2 Associação entre equipamento e grupo

Os indicadores precisam ser associados a um `GRUPO` de manutenção.

Por padrão, o código lê o campo SAP `TPLNR` e usa sua hierarquia. Em estruturas com cinco ou mais segmentos, utiliza os segmentos de grupo e equipamento definidos pela posição hierárquica esperada; em estruturas menores, usa os dois últimos segmentos. Depois verifica se:

- o `TPLNR` existe e tem estrutura válida;
- um equipamento não aparece associado a grupos conflitantes;
- todos os equipamentos dos indicadores têm cobertura operacional.

Também é possível fornecer um arquivo manual com `--group-map-file`.

### 5.3 Agregação mensal

Cada fonte operacional é processada separadamente, evitando multiplicar indevidamente registros quando várias bases são cruzadas.

Para campos numéricos, o sistema pode calcular:

- soma;
- média;
- mediana;
- mínimo;
- máximo;
- quantidade de registros;
- quantidade de valores distintos.

Para alguns campos textuais com poucos valores, calcula proporções. Campos que parecem ser identificadores, chaves ou datas detalhadas são excluídos ou usados apenas para contagem.

Os nomes gerados preservam a origem, por exemplo:

```text
AMS_Contador__IMAINDI383_sum
```

Isso significa: soma mensal do campo `IMAINDI383` vindo da fonte `AMS_Contador`.

### 5.4 Histórico e defasagens

Para cada variável operacional são criadas versões históricas por grupo:

- `lag_0`: valor do mês atual `t`;
- `lag_1`: valor de um mês atrás;
- ...
- `lag_6`: valor de seis meses atrás, usando o padrão atual.

O `lag_0` é permitido porque o objetivo é usar as informações disponíveis no mês `t` para prever `t+1`. Os primeiros meses podem ser removidos quando ainda não possuem histórico suficiente.

Metas, UF e respostas de confiabilidade não são aceitas como preditores operacionais. Isso reduz o risco de o modelo receber uma informação que só estaria disponível depois do evento previsto — o chamado **vazamento de informação**.

### 5.5 Criação do alvo futuro

Para cada grupo, o valor da resposta é deslocado um mês para frente:

```text
informações de janeiro  → previsão de fevereiro
informações de fevereiro → previsão de março
```

O código só mantém pares que realmente sejam meses consecutivos. Se janeiro for seguido diretamente por março, esse par não é tratado como uma previsão válida de fevereiro.

---

## 6. Que algoritmos usa

O projeto compara três referências para cada indicador.

### 6.1 Baseline de persistência (`baseline_t1`)

É a previsão mais simples:

```text
previsão do próximo mês = valor do mês atual
```

Ele funciona como uma régua. Um modelo complexo só é útil se conseguir ser melhor do que simplesmente repetir o último valor conhecido.

### 6.2 Elastic Net

É uma regressão linear com regularização:

- **L1:** ajuda a deixar alguns coeficientes próximos de zero, selecionando variáveis;
- **L2:** reduz a instabilidade causada por variáveis muito parecidas entre si.

Antes do treinamento, o pipeline substitui ausentes pela mediana e padroniza as escalas. Os coeficientes indicam uma associação linear, mas não provam causalidade.

### 6.3 Random Forest

É um conjunto de árvores de decisão. Cada árvore aprende regras diferentes e o resultado é combinado. Esse método pode capturar relações não lineares e interações entre manutenção, operação e histórico.

No modo padrão (`cpu`), usa `RandomForestRegressor` do scikit-learn. No modo `cuda`, usa `XGBRegressor` do XGBoost na GPU NVIDIA; portanto, o modo CUDA não é exatamente o mesmo algoritmo do Random Forest da CPU.

### 6.4 Escolha de parâmetros

O `GridSearchCV` testa pequenas combinações de parâmetros, como força de regularização do Elastic Net e profundidade/número de árvores. A escolha usa o **MAE** e respeita a ordem do tempo.

---

## 7. Como valida o resultado

O projeto não mistura aleatoriamente meses antigos e novos. Ele usa validação temporal (*walk-forward*):

```text
treina nos meses antigos → testa em meses posteriores
expande a janela          → testa em meses ainda mais recentes
```

Além dessas janelas, os últimos `--test-months` meses são separados como teste final fora da amostra (**OOS**). Esse teste representa o cenário mais próximo de prever um futuro ainda não visto.

As principais métricas são:

- **MAE:** erro absoluto médio, na unidade original;
- **RMSE:** penaliza mais os erros grandes;
- **MAPE:** erro percentual médio, quando o valor real não é zero;
- **R²:** quanto da variação observada é explicada pela previsão.

O resultado também é comparado ao baseline.

### Classificações

- **`VALIDO`:** atende aos limites configurados, tem amostra suficiente, não apresenta risco relevante de vazamento e supera o baseline.
- **`EXPLORATORIO`:** apresenta algum sinal, mas possui limitações ou alertas estatísticos.
- **`INVALIDO`:** não supera a referência, tem amostra insuficiente ou viola limites importantes.

Essas classificações são uma governança do resultado; `VALIDO` não significa que a previsão seja certa em todos os meses.

---

## 8. Que resultado e arquivos gera

O diretório padrão é `resultados/`.

### Auditoria e rastreabilidade

| Arquivo                              | Para que serve                                                                                                                                  |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `auditoria_qualidade.csv`          | Lista os testes feitos nos dados, problemas encontrados e severidade (`INFO`, `WARNING` ou `ERROR`).                                      |
| `relatorio_qualidade_dados.csv`    | Resume, por fonte, quantas linhas foram lidas, aproveitadas ou perdidas e a cobertura temporal.                                                 |
| `validar_modelo.log`               | Registro operacional da execução: início, etapas, alertas, erros e localização dos arquivos gerados.                                       |
| `cobertura_temporal_validacao.csv` | Mostra quais meses e linhas entraram ou foram descartados na validação de cada indicador.                                                     |
| `mapeamento_features.csv`          | Dicionário das variáveis criadas: fonte, campo original, transformação, lag e risco/status semântico.                                      |
| `features_excluidas.csv`           | Explica quais colunas não foram usadas e por quê — por exemplo, meta, identificador, alta cardinalidade, campo posterior ou baixa cobertura. |

### Dados, previsões e métricas

| Arquivo                        | Para que serve                                                                                                    |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `base_analitica.csv`         | Base final que alimenta os modelos: grupo, mês, indicadores, variáveis operacionais e histórico por lags.      |
| `previsoes_fora_amostra.csv` | Compara valor real, previsão e erro para cada modelo nos períodos OOS e nas dobras de validação.              |
| `metricas_modelos.csv`       | Tabela numérica para comparar Elastic Net, Random Forest e baseline usando MAE, RMSE, MAPE, R² e correlações. |
| `classificacao_validade.csv` | Parecer resumido por indicador (`VALIDO`, `EXPLORATORIO` ou `INVALIDO`) e justificativa dos gates violados. |
| `real_x_meta.csv`            | Compara resultado real e meta, calculando desvio absoluto, desvio percentual, atingimento e status.               |

### Explicabilidade, correlação e diagnósticos

| Arquivo                            | Para que serve                                                                                             |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `coeficientes_elastic_net.csv`   | Mostra quais variáveis tiveram associação linear positiva, negativa ou próxima de zero no Elastic Net. |
| `importancia_variaveis.csv`      | Ordena as variáveis pelo quanto contribuíram para a previsão no teste; não é prova de causalidade.    |
| `ranking_dados_recomendados.csv` | Reúne o ranking de variáveis mais úteis para priorizar investigação ou melhoria de dados.             |
| `correlacoes_indicadores.csv`    | Mede associação Pearson e Spearman entre variáveis operacionais e indicadores, priorizando MTBF e DF.   |
| `diagnosticos_estatisticos.csv`  | Registra alertas de VIF, resíduos, autocorrelação, normalidade, outliers e estabilidade.                |

### Gráficos e relatório

A pasta `resultados/graficos/` contém séries real versus previsto, dispersão, resíduos, distribuição de erros, importância e comparação dos modelos.

O `relatorio_final.txt` reúne os principais achados em texto.

Em uma execução com erro estrutural, o sistema gera apenas os artefatos de auditoria e relatório de erro; ele não fabrica previsões.

---

## 9. Interpretação dos resultados atuais

Esta interpretação considera os arquivos que já estão versionados em `resultados/`.

### Conclusão executiva

**Os resultados preditivos não estão bons o suficiente para uso operacional.** A execução terminou tecnicamente (`status: completed`), mas os cinco indicadores foram classificados como `INVALIDO`. Isso significa que o código conseguiu ler, preparar e modelar os dados, porém os modelos não demonstraram confiabilidade suficiente para serem tratados como previsões de produção.

| Indicador   |       Melhor MAE no teste | Baseline MAE | Leitura                                                                               |
| ----------- | ------------------------: | -----------: | ------------------------------------------------------------------------------------- |
| DF (REAL)   |    0,176 — Random Forest |        0,214 | Melhorou o baseline, mas R² = -0,049; não explica adequadamente a variação.       |
| MTBF (REAL) |  89,63 h — Random Forest |      86,90 h | Pior que simplesmente repetir o mês anterior.                                        |
| MTBS (REAL) |  28,01 h — Random Forest |      30,96 h | Melhorou o baseline, mas houve instabilidade muito alta entre janelas (CV = 2,31).    |
| MTTR        | 223,59 h — Random Forest |      80,93 h | Muito pior que o baseline; erro percentual extremamente alto.                         |
| NIC (VMINA) |     3,24 — Random Forest |         3,59 | Pequena melhora, mas a amostra foi considerada insuficiente para um teste confiável. |

### Por que foram considerados ruins?

1. **Não basta ter um modelo treinado.** Ele precisa funcionar em meses que não viu e superar o baseline. MTBF e MTTR falharam diretamente nesse critério.
2. **Há R² negativo ou próximo de zero.** Para DF, o R² negativo indica que a previsão não acompanhou melhor a variação dos valores reais do que uma referência simples.
3. **Existe instabilidade temporal.** No MTBS, o desempenho muda muito de uma janela para outra. Um modelo instável pode parecer bom em um período e falhar no seguinte.
4. **Há erros percentuais muito elevados.** MTBF e principalmente MTTR apresentam MAPE alto, indicando previsões muito distantes em relação aos valores observados; zeros e valores pequenos também tornam o MAPE sensível.
5. **Amostra insuficiente.** NIC não teve quantidade de observações considerada suficiente para uma conclusão confiável, mesmo apresentando pequena melhora numérica.
6. **Os diagnósticos têm alertas.** O arquivo `diagnosticos_estatisticos.csv` registra VIF insuficiente, diagnósticos de resíduos não suportados e ausência de modelo selecionado em algumas verificações. Portanto, não há evidência estatística forte para validar as previsões.

### O que ainda foi positivo

- A auditoria e o fluxo completo foram executados sem bloqueio estrutural.
- O Random Forest foi melhor que o baseline em DF, MTBS e NIC, embora isso não tenha sido suficiente para aprovação.
- A análise Real x Meta pode continuar sendo útil descritivamente: ela mostra como o realizado se compara às metas, mas não transforma essa comparação em uma previsão confiável.
- As correlações e importâncias podem orientar investigação. Elas devem ser interpretadas como associações e não como causas; além disso, o próprio relatório marca o significado operacional das features como não confirmado.

**Recomendação:** usar esta execução para diagnóstico e aprendizado, não para automatizar decisões de manutenção. Antes de uma nova avaliação, revisar cobertura temporal, qualidade dos indicadores, significado dos campos operacionais, agregações e quantidade de meses disponíveis.

---

## 10. Quais comandos existem

### Execução padrão

```bash
python -m modelo_confiabilidade
```

### Execução especificando entradas e saídas

```bash
python -m modelo_confiabilidade \
  --input-dir ./bases \
  --output-dir ./resultados \
  --test-months 3 \
  --max-lag 6 \
  --random-state 42
```

### Ver ajuda

```bash
python -m modelo_confiabilidade --help
```

### Usar GPU NVIDIA

```bash
python -m modelo_confiabilidade --device cuda
```

Esse modo exige driver NVIDIA funcional e `xgboost>=2.0`. O Elastic Net continua na CPU.

### Executar testes automatizados

```bash
pytest
pytest -q
```

### Parâmetros de qualidade e amostra

Além dos comandos acima, a CLI permite controlar:

| Parâmetro                     | Padrão | Função                                          |
| ------------------------------ | ------: | ------------------------------------------------- |
| `--min-train-rows`           |      30 | mínimo de linhas para treino                     |
| `--min-test-rows`            |      10 | mínimo de linhas para teste                      |
| `--min-feature-non-null`     |     0.5 | cobertura mínima das features por linha          |
| `--min-test-r2`              |     0.0 | R² mínimo no teste                              |
| `--max-test-mape`            |   100.0 | MAPE máximo permitido                            |
| `--min-baseline-improvement` |     0.0 | melhoria mínima sobre persistência              |
| `--max-metric-cv`            |     1.0 | instabilidade máxima entre janelas               |
| `--max-vif`                  |    10.0 | limite de multicolinearidade                      |
| `--group-map-file`           | ausente | mapeamento manual de equipamento/TPLNR para grupo |

`--test-months`, `--max-lag` e `--random-state` também podem ser alterados; seus padrões são, respectivamente, `3`, `6` e `42`.

---

## 11. Limitações dos dados e dos resultados

### Limitações de cobertura

- O resultado depende dos nove arquivos fornecidos. Se uma fonte não tiver um equipamento, grupo ou mês, haverá perda de cobertura no cruzamento.
- As bases não necessariamente começam e terminam no mesmo mês. Os indicadores podem ter histórico anterior aos dados operacionais.
- Com `max-lag=6`, são necessários meses suficientes para formar o histórico. Poucos meses deixam pouco material para treino e teste.
- O teste padrão usa apenas os três meses finais; isso pode ser uma amostra pequena para concluir sobre todos os equipamentos.

### Limitações de qualidade

- Nulos, zeros e registros ausentes podem representar tanto ausência real de atividade quanto erro de preenchimento; o código não consegue descobrir sozinho qual dos dois é o caso.
- Valores impossíveis são expurgados para `NaN`, não corrigidos. A causa deve ser corrigida na fonte SAP.
- O grupo é inferido pela estrutura do `TPLNR` quando não há mapeamento manual. Uma hierarquia incorreta gera agrupamento incorreto.
- A agregação mensal resume detalhes. Depois da soma ou média, eventos individuais e sua ordem exata deixam de estar disponíveis para o modelo.
- A cobertura é medida por dados presentes, não garante que cada leitura ou ordem esteja correta.

### Limitações estatísticas e de negócio

- Importância de variável e correlação indicam associação/poder preditivo; **não comprovam causa e efeito**.
- O modelo aprende padrões históricos. Mudanças de frota, processo, política de manutenção, clima, produção ou cadastro podem reduzir sua validade.
- A previsão é mensal e por grupo; não prevê necessariamente a falha de uma máquina específica em um dia específico.
- O MAPE é problemático quando o valor real é zero; nesses casos o código não cria um percentual válido.
- R² negativo significa que o modelo foi pior do que uma referência baseada na média, e não que o indicador tenha valor negativo.
- Variáveis muito correlacionadas entre si podem tornar a interpretação dos coeficientes instável; por isso o projeto calcula VIF.
- Uma classificação `VALIDO` é válida apenas dentro dos critérios, período e dados usados naquela execução. Ela não substitui validação operacional por especialistas.

### Situação dos resultados versionados neste projeto

Os CSVs já presentes em `resultados/` são artefatos de uma execução anterior e devem ser tratados como histórico, não como previsão atualizada. Nessa execução, os cinco alvos aparecem classificados como `INVALIDO` por motivos como baixo desempenho frente ao baseline, instabilidade temporal ou amostra insuficiente. Para obter um resultado novo, é necessário executar novamente o pipeline com as bases atuais.

---

## 12. Mensagem principal para uma pessoa não técnica

O projeto é uma esteira que transforma registros de manutenção em uma tentativa controlada de previsão. Ele primeiro pergunta **“os dados estão bons?”**, depois aprende com o passado e, por fim, pergunta **“a previsão foi melhor do que simplesmente repetir o último mês?”**.

Se os dados forem insuficientes ou o modelo não demonstrar vantagem, a resposta correta do sistema é sinalizar a limitação — e não apresentar uma previsão como se fosse confiável.
