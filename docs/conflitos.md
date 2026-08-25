# Conflitos entre Notebook e Arquivos Atuais

Este documento separa conflitos técnicos, que podem ser resolvidos por leitura
ou renomeação, de conflitos semânticos, que exigem validação das regras de
negócio.

## Nomes de Arquivos

O notebook referencia quatro XLSX genéricos e quatro CSVs com nomes que não
existem no diretório atual. Os arquivos atuais são separados por universo e por
fonte operacional. O arquivo de caminhão agora está válido, mas ainda tem nome
e posição diferentes dos esperados pelo notebook.

| Esperado pelo notebook | Atual |
|---|---|
| `INDICADORES MENSAIS POR UNIVERSO.xlsx` e variantes numeradas | quatro XLSX nomeados por universo |
| `AMS_ativos_mina.csv` | `AMS_Contador.csv` ou `AMS_Calendario.csv` |
| `AMC_ativos_mina.csv` | `AMC_ITABIRA.csv` |
| `APR_ativos_mina.csv` | `APR_ITABIRA.csv` |
| `Backlog_imos_ativos_mina.csv` | `Backlog_mina_itabira.csv` |

## Leitura dos CSVs

Os arquivos atuais usam `;`, enquanto o notebook chama `pd.read_csv()` sem
informar `sep=";"`. Sem essa alteração, as colunas podem ser lidas como um
único campo. A presença de BOM também deve ser considerada na leitura do
primeiro nome de coluna.

## Chaves e Hierarquia

O notebook exige `TPLNR05` e `CALMONTH-Calendar_year_month`. Os arquivos atuais
fornecem principalmente `TPLNR`, `YEAR` e `CALMONTH`.

Além disso, o notebook obtém o grupo com o penúltimo segmento da chave:

```python
TPLNR05.str.split("-").str[-2]
```

Essa regra não está confirmada para os `TPLNR` atuais. Há estruturas em que o
penúltimo segmento representa status ou outra parte da hierarquia, e não o
universo ou grupo operacional desejado.

## Colunas AMS

O notebook espera `AMS_00H` e colunas agregadas com nomes `Soma de ...`. O
`AMS_Contador.csv` fornece `IMAINDI383` e `IMAINDI384`, mas não os aliases nem
`AMS_00H`. É necessário definir se `AMS_00H` é um campo bruto, um cálculo ou
uma agregação de outro campo.

## Colunas AMC

O notebook espera `AMC_00I` e uma coluna agregada de notificações planejadas. O
`AMC_ITABIRA.csv` possui `IMAINDI189_ACTUAL_NA` e outros indicadores relacionados,
mas não possui `AMC_00I` com esse nome. A equivalência precisa ser validada.

## Colunas APR

O notebook espera `.APR` e `Soma de IMAINDI64_TOT`. O arquivo atual possui
`IMAINDI64`, `IMAINDI63` e `IMAINDI65`, mas não possui os campos esperados. Não é
seguro inferir a fórmula de `.APR` apenas pelo nome parecido.

## Colunas de Backlog

O notebook espera colunas semânticas como `HH_EM CARTEIRA`,
`hh_em_ordens_vencidas`, YPM, YCM, corretiva e prioridades. O arquivo atual
possui indicadores brutos `IMAINDI37`, `IMAINDI38`, `IMAINDI266`, `IMAINDI354`,
`IMAINDI381`, `IMAINDI389`, `IMAINDI390` e `IMAINDI401`.

Ainda não há equivalência confirmada entre esses indicadores e os conceitos
usados pelo notebook. Esse é um conflito de regra de negócio, não apenas de
nome de coluna.

## Períodos

| Fonte | Período |
|---|---|
| XLSX atuais | `202501`–`202608` |
| CSVs operacionais | `202505`–`202608` |
| Saídas gravadas no notebook | até `202606` |

Os meses de janeiro a abril de 2025 possuem indicadores de confiabilidade, mas
não possuem dados operacionais correspondentes nos CSVs atuais. Os resultados
do notebook também não representam os dados mais recentes até agosto de 2026.

## Nível de Detalhe

Os XLSX têm indicadores mensais por equipamento. Os CSVs têm registros
detalhados de ordens, notificações, operações e planos. O notebook espera fontes
com colunas já tratadas e agregáveis por mês e grupo. Portanto, é necessária uma
camada de transformação antes do merge.

## Consequência

O conjunto atual contém todos os arquivos principais, mas não é executável com o
notebook apenas por troca de nomes. É necessário atualizar a leitura, criar as
chaves, definir as regras de grupo e validar os mapeamentos semânticos.
