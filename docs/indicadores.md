# Arquivos de Indicadores

## Papel na Análise

As planilhas fornecem os indicadores mensais de confiabilidade por equipamento.
O notebook usa os quatro universos em conjunto para formar a tabela `df`.

## Arquivos Atuais

| Arquivo | Universo | Dados aproximados | Período |
|---|---|---:|---|
| `INDICADORES MENSAIS POR UNIVERSO caminhao.xlsx` | Caminhão | 1.204 registros | `202501`–`202608` |
| `INDICADORES MENSAIS POR UNIVERSO carga.xlsx` | Carga | 243 registros | `202501`–`202608` |
| `INDICADORES MENSAIS POR UNIVERSO perfuracao.xlsx` | Perfuração | 273 registros | `202501`–`202608` |
| `INDICADORES MENSAIS POR UNIVERSO infra.xlsx` | Infraestrutura | 1.295 registros | `202501`–`202608` |

Os quatro arquivos possuem a aba `Export` e a mesma estrutura de 26 colunas.
O arquivo de caminhão foi validado como XLSX íntegro. Ele possui 1.206 linhas
físicas: cabeçalho, registros, uma linha `Total`, uma linha em branco e uma
linha com filtros aplicados.

## Colunas

```text
ANO MÊS, EQUIPAMENTO,
DF (META), DF (REAL),
MTBF (META), MTBF (REAL),
MTBS (META), MTBS (REAL),
MTTR (META), MTTR,
NIC (META), NIC (VMINA),
UF (META), UF (REAL),
RO (META), RO (REAL),
HO (REAL),
HT (META), HT (REAL),
HM (META), HM (REAL),
HMC (META), HMC (REAL),
MPS (REAL), MPNS (REAL), HAC (REAL)
```

O notebook consome diretamente as seguintes colunas:

```text
ANO MÊS
EQUIPAMENTO
DF (REAL)
MTBF (REAL)
MTBS (REAL)
MTTR
NIC (VMINA)
```

As colunas de meta e os demais indicadores ficam disponíveis, mas não entram na
base de correlação descrita no notebook.

## Limpeza Necessária

As linhas `Total`, em branco e de filtros não devem ser tratadas como
equipamentos. O notebook original esperava arquivos com nomes genéricos, mas os
arquivos atuais são separados explicitamente por universo. A substituição dos
nomes precisa preservar a ordem ou atualizar o código de carregamento.

O arquivo de caminhão atualmente é válido e compatível estruturalmente com os
outros três XLSX. Ele não possui uma coluna `GRUPO`; essa coluna é criada depois
no notebook usando a relação entre equipamento e hierarquia operacional.
