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

Os campos operacionais brutos, inclusive os que começam por `IMAINDI`, são
preservados com seus nomes de origem. Eles têm `status_semantico=nao_confirmado`
até que uma regra de negócio os confirme; o pipeline não cria aliases
semânticos como AMS, AMC, APR ou backlog a partir do nome de uma coluna.

## Validação preditiva

O pipeline executável será disponibilizado pelo pacote `modelo_confiabilidade`:

```bash
python -m modelo_confiabilidade \
  --input-dir ./bases \
  --output-dir ./resultados-auditoria \
  --test-months 3 \
  --max-lag 6
```

Sem `--group-map-file`, o pipeline deriva `GRUPO` e `EQUIPAMENTO` dos dois
últimos segmentos de cada `TPLNR` operacional: `GRUPO=TPLNR[-2]` e
`EQUIPAMENTO=TPLNR[-1]`. O `TPLNR` deve estar preenchido, conter ao menos dois
segmentos não vazios e associar cada equipamento a somente um grupo. A
derivação também precisa cobrir os equipamentos dos indicadores.

`--group-map-file ./config/grupos.csv` é um override opcional e compatível para
casos em que a regra hierárquica não deve ser usada. Esse arquivo deve conter
uma chave `EQUIPAMENTO` ou `TPLNR` e a coluna `GRUPO`.

Diante de erro estrutural, de hierarquia ou do mapeamento explícito, o pipeline
roda somente a auditoria, grava `auditoria_qualidade.csv`,
`relatorio_qualidade_dados.csv`, o log e `relatorio_final.txt`, retorna código
diferente de zero e não produz métricas de ML.

As saídas de uma execução completa incluem a base analítica, métricas,
previsões fora da amostra, coeficientes, importância, ranking de dados,
features excluídas, metadata, diagnósticos, classificação, relatório e
gráficos. A importância é preditiva; o significado AMS/AMC/APR/backlog só é
apresentado como confirmado quando houver configuração semântica explícita.
Ela mostra contribuição para a previsão, não causalidade sobre o indicador de
confiabilidade. A janela com cobertura operacional comum aos CSVs atuais é
`202505`–`202608`; meses anteriores dos XLSX ficam fora da modelagem quando não
possuem cobertura operacional suficiente.
