# Histórico e contexto do projeto

## Da análise exploratória ao pacote

O projeto começou com o notebook `Correlacao_AMS_DF_frota.ipynb` e o PDF `Correlacoes_AMS_Indicadores.pdf`. Essa etapa calculava correlações e regressões contemporâneas (`t → t`) com arquivos pré-agregados.

As principais limitações identificadas foram:

- risco de vazamento ao relacionar manutenção e confiabilidade no mesmo mês;
- multicolinearidade de variáveis derivadas incluídas em OLS sem regularização;
- ausência de validação fora da amostra;
- dependência de aliases e mapeamentos manuais que não representavam diretamente as exportações brutas do SAP.

O pacote atual substitui essa abordagem por agregação mensal, features temporais, previsão `t → t+1`, validação cronológica, Elastic Net, Random Forest, baseline de persistência e quality gates.

## Evolução das fontes e nomes

| Nome histórico | Arquivo atual | Função |
|---|---|---|
| `INDICADORES MENSAIS POR UNIVERSO.xlsx` e variantes numeradas | `INDICADORES MENSAIS POR UNIVERSO <universo>.xlsx` | Indicadores de confiabilidade |
| `AMS_ativos_mina.csv` | `AMS_Contador.csv` / `AMS_Calendario.csv` | Contadores e calendário AMS |
| `AMC_ativos_mina.csv` | `AMC_ITABIRA.csv` | Notificações e aderência AMC |
| `APR_ativos_mina.csv` | `APR_ITABIRA.csv` | Programação de manutenção APR |
| `Backlog_imos_ativos_mina.csv` | `Backlog_mina_itabira.csv` | Carteira e horas de backlog |

## Resolução de grupo

No fluxo padrão, `GRUPO` e `EQUIPAMENTO` são derivados dos dois últimos segmentos de `TPLNR`. O parâmetro `--group-map-file` permite um mapeamento explícito quando a hierarquia não é suficiente. O pipeline valida completude, ambiguidades e cobertura antes de modelar.

Este arquivo é histórico: as regras operacionais vigentes devem ser consultadas em `pipeline_modelagem.md`, `indicadores.md` e `operacionais.md`.
