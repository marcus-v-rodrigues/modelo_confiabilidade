# `modelo_confiabilidade.relatorios`

- `save_results(results: Mapping[str, Any], output_dir: Path) -> None`: grava os frames/tabelas conhecidos do dicionário `results` nos CSVs padronizados e cria o diretório de saída.
- `generate_plots(results: Mapping[str, Any], output_dir: Path) -> list[Path]`: gera PNGs de previsões, resíduos, dispersões, importâncias e comparações disponíveis. Retorna os caminhos criados.
- `compute_real_vs_meta(frame: DataFrame) -> DataFrame`: calcula a comparação entre valores reais e metas dos indicadores. Retorna uma tabela analítica; não grava arquivo.
- `compute_indicator_correlations(analytic_frame: DataFrame, feature_columns: Sequence[str] | None = None, response_columns: Sequence[str] | None = None) -> DataFrame`: calcula correlações Pearson e Spearman entre features e respostas, priorizando MTBF e DF. Se as listas forem `None`, seleciona colunas elegíveis automaticamente. Retorna ranking tabular.
- `write_final_report(results: Mapping[str, Any], output_dir: Path) -> Path`: escreve `relatorio_final.txt` a partir dos resultados e retorna seu `Path`.

## Exemplo

```python
from pathlib import Path
from modelo_confiabilidade.relatorios import save_results, generate_plots, write_final_report

save_results(results, Path("resultados"))
generate_plots(results, Path("resultados"))
report = write_final_report(results, Path("resultados"))
```

As chaves esperadas em `results` correspondem aos nomes documentados em [`../guia-inicio-rapido.md`](../guia-inicio-rapido.md). Funções internas iniciadas por `_` não devem ser chamadas diretamente.
