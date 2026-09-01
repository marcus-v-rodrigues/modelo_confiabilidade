# `modelo_confiabilidade.configuracao`

## `Config`

`@dataclass(frozen=True)` com a configuração validada em tempo de execução.

| Campo | Tipo | Padrão |
|---|---|---|
| `input_dir` | `Path` | `Path("./bases")` |
| `output_dir` | `Path` | `Path("./resultados")` |
| `test_months` | `int` | `3` |
| `max_lag` | `int` | `6` |
| `random_state` | `int` | `42` |
| `device` | `str` | `"cpu"` (`"cuda"` também aceito) |
| `group_map_file` | `Path \| None` | `None` |
| `min_train_rows` / `min_test_rows` | `int` | `30` / `10` |
| `min_feature_non_null` | `float` | `0.5` |
| `min_test_r2` / `max_test_mape` | `float` | `0.0` / `100.0` |
| `min_baseline_improvement` / `max_metric_cv` | `float` | `0.0` / `1.0` |
| `max_vif` | `float` | `10.0` |

Retorno: instância imutável de `Config`.

## `DataValidationError`

Exceção usada quando uma fonte obrigatória não pode ser carregada, está ausente ou falha em uma validação. Pode expor `source`, `path` e `correction`.

## Funções

### `parse_args(argv: Sequence[str] | None = None) -> Config`

Converte argumentos da CLI em `Config`. `argv=None` usa `sys.argv`; uma sequência permite uso programático/testes. Argumentos inválidos encerram com o comportamento padrão do `argparse`.

### `configure_logging(output_dir: Path) -> logging.Logger`

Cria o diretório de saída, configura log no console e em `output_dir/validar_modelo.log`, e retorna o logger `validar_modelo`. Reconfigura handlers existentes.

## Constantes

`INDICATOR_FILES` mapeia os quatro universos aos XLSX esperados. `OPERATIONAL_FILES` mapeia as cinco fontes aos CSVs esperados.
