# Documentação do `modelo_confiabilidade`

Documentação técnica do pacote de auditoria, preparação de dados e previsão mensal de indicadores de confiabilidade.

## Comece aqui

- [Guia de início rápido](guia-inicio-rapido.md): instalação, execução, parâmetros e saídas.
- [Pipeline de modelagem](pipeline_modelagem.md): fluxo de dados, lags, validação temporal e modelos.
- [Indicadores de confiabilidade](indicadores.md): definições, metas, unidades e regras de validação.
- [Fontes operacionais](operacionais.md): arquivos SAP, campos e agregações.
- [Dicionário de dados](dicionario.md): features, metadados e chaves.
- [Diagnósticos e validação](diagnosticos_e_validacao.md): métricas, testes e classificação dos resultados.
- [Histórico e contexto](historico.md): notebook exploratório, migração e nomes históricos das fontes.
- [Referência da API Python](api/README.md): módulos, classes, funções, parâmetros e retornos.

## Estrutura do pacote

```text
modelo_confiabilidade/
├── __init__.py
├── __main__.py           # Entrada CLI e orquestração
├── configuracao.py       # Configuração e argumentos
├── dados.py              # Leitura, normalização, TPLNR, lags e features
├── auditoria.py          # Quality gates e auditoria
├── modelagem.py          # Elastic Net, Random Forest, baseline e validação temporal
├── diagnosticos.py       # VIF, resíduos, importância e classificação
└── relatorios.py         # CSVs, gráficos e relatório TXT
```
