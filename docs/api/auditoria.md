# `modelo_confiabilidade.auditoria`

## `audit_data_quality(sources: Mapping[str, pandas.DataFrame]) -> pandas.DataFrame`

Audita todas as fontes fornecidas. `sources` é um mapeamento nome → `DataFrame`, normalmente produzido pelos loaders de `dados`.

Retorna uma tabela com uma linha por verificação e colunas de fonte, regra, valor observado, status e mensagem (o conjunto exato de colunas é definido pelo módulo). As verificações cobrem presença/estrutura, vazios, duplicidades, datas, tipos, cobertura e consistência das fontes.

A função não corrige os dados nem grava arquivos. A gravação dos relatórios de qualidade é responsabilidade do pipeline. Falhas estruturais podem ser representadas na tabela e posteriormente bloquear a modelagem.
