# Documentação da Análise AMS e Confiabilidade

Esta pasta registra o que o notebook faz, o papel de cada fonte e os conflitos que precisam ser resolvidos para executar a análise com os arquivos atuais.

## Documentos

- [Fluxo do notebook](notebook.md): entradas, preparação, métricas derivadas,
  agregações, lags, correlações, regressões e limitações.
- [Arquivos de indicadores](indicadores.md): os quatro XLSX por universo,
  incluindo o arquivo de caminhão corrigido.
- [Fontes operacionais](operacionais.md): AMS, calendário AMS, AMC, APR e
  backlog.
- [Conflitos](conflitos.md): diferenças técnicas e semânticas entre o notebook
  e os arquivos atuais.
- [Diferenças entre bases](diferencas-bases.md): comparação entre os arquivos
  históricos e as bases novas.
- [Dicionário de correspondência](dicionario.md): campos diretos, derivados e
  ainda indefinidos.

## Arquivos Relacionados

- [`../Correlacao_AMS_DF_frota.ipynb`](../Correlacao_AMS_DF_frota.ipynb)
- `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx`
- `INDICADORES MENSAIS POR UNIVERSO carga.xlsx`
- `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx`
- `INDICADORES MENSAIS POR UNIVERSO infra.xlsx`
- `AMS_Contador.csv`
- `AMS_Calendario.csv`
- `AMC_ITABIRA.csv`
- `APR_ITABIRA.csv`
- `Backlog_mina_itabira.csv`
- `../Correlacoes_AMS_Indicadores.pdf`

## Estado Atual

Os quatro XLSX estão disponíveis e estruturalmente consistentes. O arquivo de caminhão está íntegro, possui a aba `Export` e cobre `202501`–`202608`.

Os CSVs atuais são fontes detalhadas, enquanto o notebook espera tabelas já normalizadas e agregáveis. Por isso, a análise ainda requer uma camada de transformação para chaves, períodos e métricas AMS, AMC, APR e backlog.
