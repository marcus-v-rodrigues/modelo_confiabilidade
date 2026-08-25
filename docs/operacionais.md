# Fontes Operacionais

Os CSVs são exportações detalhadas de fontes SAP e contêm registros de ordens, planos, notificações, atividades e backlog. Eles não estão no mesmo nível agregado das tabelas que o notebook espera.

## Características Comuns

- Separador: `;`.
- Codificação: UTF-8 com BOM.
- Datas e identificadores frequentemente aparecem como texto.
- Chaves SAP, hierarquias, ordens e indicadores brutos ocupam muitas colunas.
- O período operacional principal é `202505`–`202608`.

## AMS

### `AMS_Contador.csv`

- Aproximadamente 70.786 registros.
- 157 colunas.
- Contém contadores, leituras, tolerâncias, planos e ordens AMS.
- Campos relevantes incluem `IMAINDI383`, `IMAINDI384`, `IMAINDI385`,
  `INTERVECAO`, `READG`, `POINT`, `PYEAR` e `IDATE`.

Este arquivo é a fonte mais próxima dos contadores AMS usados no notebook, mas
não possui diretamente os aliases agregados `AMS_00H` e `Soma de ...`.

### `AMS_Calendario.csv`

- Aproximadamente 63.476 registros.
- 134 colunas.
- Contém calendário de planos, datas previstas e realizadas, ciclos e status.
- Campos relevantes incluem `AMSYEAR`, `AMSMON`, `AMSWEEK`, `AMSDAY_DATE`,
  `AMSCALC`, `ITOSMPT`, `ITEOSMPT`, `IMAINDI265`, `IMAINDI292`, `IMAINDI370`,
  `IMAINDI378` e `IMAINDI382`.

O calendário é uma fonte operacional diferente do contador. Não deve ser
tratado automaticamente como substituto do `AMS_Contador.csv`.

## AMC: `AMC_ITABIRA.csv`

- Aproximadamente 101.519 registros.
- 117 colunas.
- Contém notificações, ordens, estados, datas de prazo, tolerâncias e
  indicadores de aderência AMC.
- Campos relevantes incluem `QMNUM`, `STRMN`, `LTRMN`, `AMCYEAR`, `AMCMON`,
  `AMCCALC`, `IMAINDI189`, `IMAINDI189_ACTUAL`,
  `IMAINDI189_ACTUAL_NA`, `IMAINDI190` e `AMCCALC_NA`.

## APR: `APR_ITABIRA.csv`

- Aproximadamente 135.729 registros.
- 109 colunas.
- Contém operações, atividades, datas programadas e executadas, status e
  indicadores APR.
- Campos relevantes incluem `VORNR`, `AUFPL`, `APLZL`, `FSAVD`, `WWSDT`,
  `WWFDT`, `IMAINDI63`, `IMAINDI64`, `IMAINDI65` e `UNID_MED`.

## Backlog: `Backlog_mina_itabira.csv`

- Aproximadamente 306.004 registros.
- 129 colunas.
- Contém status, operações, prioridades, datas de vencimento, ordens líderes,
  capacidade e indicadores de backlog.
- Campos relevantes incluem `PRIOK`, `LTRMN`, `IMAINDI37`, `IMAINDI38`,
  `IMAINDI266`, `IMAINDI354`, `IMAINDI381`, `IMAINDI389`, `IMAINDI390`,
  `IMAINDI401`, `DATA_VENCIMENTO_NEW`, `DIAS_PARA_VENC_NEW` e `VENC_NEW`.

O notebook espera conceitos já nomeados como backlog total, vencido, YPM, YCM,
corretiva e prioridades. Os CSVs atuais fornecem indicadores-base, mas a
correspondência de negócio ainda precisa ser confirmada.
