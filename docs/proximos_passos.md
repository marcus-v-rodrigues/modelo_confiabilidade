Tecnicamente, a pipeline já está funcionando, já que todos os **105 testes passam** e a execução chega ao status de **concluída**. Mas isso só indica que o processamento foi executado corretamente.

Até o momento, **nenhum dos cinco modelos avaliados atingiu os critérios necessários para ser aprovado para uso preditivo**.

Para avançar, os principais pontos a serem trabalhados são:

## 1. Revisar e confirmar a definição dos indicadores

Antes de ajustar os modelos, é importante garantir que os indicadores estejam sendo interpretados e calculados corretamente. Alguns pontos ainda precisam ser confirmados:

- Validar a escala da **DF**, verificando se os valores estão entre `[0, 1]` ou `[0, 100]`;
- Investigar os valores extremos de **MTTR**, que chegam a aproximadamente **744 horas**, para entender se são casos reais ou possíveis inconsistências nos dados;
- Confirmar as fórmulas e regras de cálculo utilizadas para **MTBF, MTBS, MTTR e NIC**;
- Definir o tratamento adequado para valores zerados e ausentes, principalmente antes do cálculo de métricas como o **MAPE**.

## 2. Aumentar o histórico disponível e validar a janela de memória

Atualmente, as bases operacionais cobrem aproximadamente o período de **maio de 2025 a agosto de 2026**, ou seja, cerca de **16 meses de histórico**. É um período relativamente curto para testar diferentes configurações temporais e avaliar se o desempenho dos modelos se mantém estável ao longo do tempo.

Hoje, cada previsão pode considerar os dados dos **seis meses anteriores**. Não é somente uma questão de aumentar essa janela, pois utilizar lags maiores também aumenta a quantidade de variáveis e pode elevar o risco de sobreajuste.

O ideal seria:

- Obter pelo menos **24 a 36 meses de histórico** operacional e dos indicadores;
- Comparar diferentes janelas de memória, como `lag=3`, `lag=6` e `lag=12`;
- Verificar quantos períodos continuam realmente utilizáveis em cada configuração;
- Escolher a janela com melhor desempenho em dados fora da amostra;
- Realizar **backtesting** em diferentes períodos históricos, em vez de avaliar apenas os três meses finais;
- Reservar um período final que não participe das etapas anteriores e seja utilizado exclusivamente para a **validação definitiva**.

A escolha da janela deve considerar o equilíbrio entre:

- Quantidade de histórico disponível;
- Número de períodos úteis para treinamento;
- Desempenho preditivo;
- Risco de sobreajuste.

## 3. Reduzir e qualificar as variáveis utilizadas

A base analítica atual possui **1.478 linhas e 22.508 colunas**. Na prática, temos uma quantidade muito maior de variáveis do que de observações, o que aumenta significativamente o risco de **sobreajuste** e também dificulta entender quais fatores realmente estão contribuindo para as previsões.

Por isso, é importante:

- Remover IDs, chaves técnicas, códigos administrativos e campos constantes;
- Excluir variáveis numéricas que, apesar do formato, funcionam apenas como identificadores;
- Priorizar indicadores operacionais cujo significado esteja claramente definido;
- Agrupar categorias com poucas ocorrências;
- Eliminar variáveis redundantes ou muito correlacionadas entre si;
- Realizar a seleção de variáveis **dentro de cada janela de treinamento**, evitando utilizar qualquer informação do futuro.

## 4. Validar o significado dos campos

Outro ponto importante é que várias das variáveis consideradas relevantes pelo modelo ainda aparecem com o significado marcado como **"não confirmado"**.

Antes de utilizar essas informações em produção, é necessário construir e validar um **dicionário dos dados** que deixe claro:

- O significado de cada `IMAINDI`;
- Sua unidade de medida;
- Se o campo representa planejamento, execução, atraso, backlog, status ou outro conceito operacional;
- Qual é a forma correta de agregação: soma, média, máximo, contagem, proporção etc.;
- Se aquela informação realmente estaria disponível no momento em que a previsão fosse realizada.

Essa validação é fundamental porque um modelo pode estar matematicamente correto e, ainda assim, utilizar variáveis de forma inadequada do ponto de vista operacional.

Sem entender claramente o que cada campo representa e quando ele está disponível, fica difícil confiar nas previsões e, principalmente, defendê-las como suporte para decisões reais.