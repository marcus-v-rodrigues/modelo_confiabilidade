# `modelo_confiabilidade.__main__`

## `main(argv: Sequence[str] | None = None) -> int`

Ponto de entrada programático da aplicação. Lê os argumentos com `parse_args`, configura logging, carrega e audita as fontes, constrói features/lags, executa a validação para as respostas, calcula diagnósticos e grava relatórios.

- `argv=None`: usa os argumentos do processo (`sys.argv`).
- `argv`: sequência de strings para execução embutida ou testes.
- Retorno `0`: execução concluída.
- Retorno diferente de zero: execução interrompida por erro ou quality gate; detalhes ficam no log e nos relatórios disponíveis.

A forma equivalente pela linha de comando é:

```bash
python -m modelo_confiabilidade --help
python -m modelo_confiabilidade --input-dir ./bases --output-dir ./resultados
```
