# Diferenças entre as Bases

Este documento registra a diferença entre os arquivos históricos que estavam em `old_bases/` e as bases atuais em `bases/`. O fluxo atual deve utilizar somente `bases/`. A pasta `old_bases/` foi removida; os dados descritos neste documento são referência histórica e não fazem parte da entrada do modelo.

## Indicadores de Confiabilidade

Os arquivos antigos e novos possuem a mesma estrutura de 26 colunas e a mesma
aba `Export`. As bases novas, porém, foram atualizadas até agosto de 2026 e os
valores dos períodos comuns também foram recalculados.

| Universo   | Arquivo antigo                                | Registros antigos | Arquivo novo                                         | Registros novos | Equipamentos antigos | Equipamentos novos |
| ---------- | --------------------------------------------- | ----------------: | ---------------------------------------------------- | --------------: | -------------------: | -----------------: |
| Caminhão   | `INDICADORES MENSAIS POR UNIVERSO.xlsx`     |             1.085 | `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx`   |           1.202 |                   69 |                 69 |
| Carga      | `INDICADORES MENSAIS POR UNIVERSO (2).xlsx` |               219 | `INDICADORES MENSAIS POR UNIVERSO carga.xlsx`      |             241 |                   15 |                 15 |
| Infra      | `INDICADORES MENSAIS POR UNIVERSO (3).xlsx` |               550 | `INDICADORES MENSAIS POR UNIVERSO infra.xlsx`      |           1.293 |                   40 |                 74 |
| Perfuração | `INDICADORES MENSAIS POR UNIVERSO (4).xlsx` |               244 | `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` |             271 |                   17 |                 19 |

Período dos XLSX antigos: `202501` a `202606`.

Período dos XLSX novos: `202501` a `202608`.

Comparação dos registros que existem nos dois arquivos:

- Caminhão: 996 dos 1.085 registros comuns foram alterados.
- Carga: 190 dos 219 registros comuns foram alterados.
- Infra: 468 dos 548 registros comuns foram alterados.
- Perfuração: 238 dos 244 registros comuns foram alterados.

Portanto, as bases novas não são apenas uma extensão mensal das antigas. Elas devem ser tratadas como uma nova fotografia dos indicadores.

## Fontes Operacionais

As fontes antigas eram tabelas agregadas por mês e equipamento, com nomes de colunas já alinhados aos conceitos usados no estudo.

| Fonte   | Base antiga                                                    | Base nova                                                                                                    |
| ------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| AMS     | `AMS_ativos_mina.csv`: 11.582 registros e 7 colunas          | `AMS_Contador.csv`: 70.786 registros e 157 colunas; `AMS_Calendario.csv`: 63.476 registros e 134 colunas |
| AMC     | `AMC_ativos_mina.csv`: 3.307 registros e 4 colunas           | `AMC_ITABIRA.csv`: 101.519 registros e 117 colunas                                                         |
| APR     | `APR_ativos_mina.csv`: 5.745 registros e 4 colunas           | `APR_ITABIRA.csv`: 135.729 registros e 109 colunas                                                         |
| Backlog | `Backlog_imos_ativos_mina.csv`: 7.001 registros e 14 colunas | `Backlog_mina_itabira.csv`: 306.004 registros e 129 colunas                                                |

Período das fontes antigas: `202503` a `202606`.

Período das fontes novas: `202505` a `202608`.

As fontes novas são extrações detalhadas de ordens, notificações, operações, planos, status, equipamentos e indicadores brutos. Elas não devem ser juntadas diretamente entre si, pois podem produzir multiplicação de registros. Cada fonte precisa ser agregada antes da integração com os indicadores de
confiabilidade.

## Mudanças de Esquema

Nas bases antigas, os conceitos analíticos estavam disponíveis diretamente ou
com nomes proximos aos usados no estudo:

- `AMS_00H`, ordens AMS previstas e fechadas;
- `AMC_00I` e notificações planejadas;
- `.APR` e total APR planejado;
- horas de backlog total, vencido, YPM, YCM, corretiva e prioridades.

Nas bases novas, esses conceitos não estão prontos com os mesmos nomes. Existem campos candidatos, mas a equivalência ainda precisa ser investigada:

- AMS: `IMAINDI383`, `IMAINDI384`, `IMAINDI385` e campos de calendario;
- AMC: `IMAINDI189`, `IMAINDI189_ACTUAL`, `IMAINDI189_ACTUAL_NA` e relacionados;
- APR: `IMAINDI63`, `IMAINDI64`, `IMAINDI65` e relacionados;
- backlog: `IMAINDI37`, `IMAINDI38`, `IMAINDI266`, `IMAINDI354`, `IMAINDI381`,
  `IMAINDI389`, `IMAINDI390` e `IMAINDI401`.

Esses campos devem ser tratados como candidatos a variáveis explicativas na fase de descoberta. O modelo pode indicar quais apresentam sinal preditivo, mas o significado de negócio deve ser confirmado posteriormente.

## Chaves e Períodos

As bases novas utilizam principalmente `YEAR`, `CALMONTH`, `TPLNR`, `EQUNR` e
chaves SAP detalhadas. Os XLSX utilizam `ANO MÊS` e `EQUIPAMENTO`.

Não existe equivalência automática garantida entre:

- `EQUIPAMENTO` e `TPLNR`;
- `EQUIPAMENTO` e `EQUNR`;
- `TPLNR` e `GRUPO`.

A interseção temporal entre indicadores e fontes operacionais novas é
`202505`-`202608`. Os meses `202501`-`202504` possuem indicadores de
confiabilidade, mas não possuem fontes operacionais novas correspondentes.

## Consequências para a Descoberta de Features

O objetivo com as bases novas não é reproduzir os aliases das bases antigas.
O objetivo é testar quais campos, agregações e defasagens possuem capacidade
preditiva sobre `DF (REAL)`, `MTBF (REAL)`, `MTBS (REAL)`, `MTTR` e
`NIC (VMINA)`.

O processo deve:

1. Preservar os nomes originais dos campos candidatos.
2. Agregar cada fonte antes dos joins.
3. Gerar soma, média, contagem e outras transformações documentadas.
4. Criar defasagens temporais sem usar informação futura.
5. Registrar a importância, estabilidade e risco de vazamento de cada campo.
6. Produzir uma lista dos dados que devem ser investigados ou obtidos depois.

Os resultados da descoberta não devem ser interpretados como confirmação
semântica de que um campo é AMS, AMC, APR ou backlog. Essa confirmação pertence
a uma etapa posterior.

## Referencias

- [Fontes operacionais](operacionais.md)
- [Dicionário de correspondência](dicionario.md)
- [Conflitos e limitações](conflitos.md)
- [Prompt de validação do modelo](agentsmith/prompt-validacao-modelo.md)
