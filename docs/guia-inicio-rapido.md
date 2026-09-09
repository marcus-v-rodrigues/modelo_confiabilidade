# Guia de início rápido

## Executar

O pipeline lê as quatro planilhas de indicadores e os cinco CSVs operacionais de `./bases` e grava os resultados em `./resultados`:

```bash
python -m modelo_confiabilidade
```

Exemplo com parâmetros explícitos:

```bash
python -m modelo_confiabilidade \
  --input-dir ./bases \
  --output-dir ./resultados \
  --test-months 3 \
  --max-lag 6 \
  --random-state 42
```

Consulte todas as opções com:

```bash
python -m modelo_confiabilidade --help
```

`--device cuda` mantém Elastic Net e Random Forest e executa o XGBoost adicionalmente com CUDA. O treinamento e o pré-processamento numérico usam RAPIDS/cuML e XGBoost na GPU. Instale `requirements-gpu.txt` e tenha um driver NVIDIA compatível. A leitura, auditoria, diagnósticos estatísticos e relatórios continuam na CPU. O padrão (`cpu`) usa as implementações CPU.

## Parâmetros principais

| Opção | Padrão | Função |
|---|---:|---|
| `--test-months` | `3` | Meses finais reservados para o teste OOS |
| `--max-lag` | `6` | Histórico máximo de features, incluindo `lag_0` |
| `--min-train-rows` | `30` | Mínimo de linhas para treino |
| `--min-test-rows` | `10` | Mínimo de linhas no teste |
| `--min-feature-non-null` | `0.5` | Cobertura mínima de uma feature no treino |
| `--min-test-r2` | `0.0` | R² mínimo no teste |
| `--max-test-mape` | `100.0` | MAPE máximo permitido |
| `--min-baseline-improvement` | `0.0` | Melhoria mínima sobre persistência |
| `--max-metric-cv` | `1.0` | Instabilidade máxima entre janelas |
| `--max-vif` | `10.0` | VIF máximo tolerado |

## Interpretar o status

- `completed`: auditoria e modelagem concluídas.
- `audit_only`: erro estrutural ou insuficiência bloqueou a modelagem; o processo retorna código `1` e não fabrica previsões.
- `VALIDO`, `EXPLORATORIO` e `INVALIDO`: classificação por indicador, conforme os gates de validação.

`VALIDO` significa apenas que os critérios configurados foram atendidos no período avaliado; não é garantia de acerto operacional.

## Principais saídas

- `relatorio_final.txt`: resumo executivo.
- `auditoria_qualidade.csv` e `relatorio_qualidade_dados.csv`: qualidade das fontes.
- `base_analitica.csv`: base usada na modelagem.
- `metricas_modelos.csv` e `previsoes_fora_amostra.csv`: desempenho e previsões OOS/OOF.
- `classificacao_validade.csv`: parecer por indicador.
- `mapeamento_features.csv` e `features_excluidas.csv`: rastreabilidade das features.
- `diagnosticos_estatisticos.csv`, `importancia_variaveis.csv` e `coeficientes_elastic_net.csv`: diagnósticos e explicabilidade.
- `real_x_meta.csv` e `correlacoes_indicadores.csv`: análises descritivas.
- `graficos/`: visualizações OOS.

Para testes automatizados:

```bash
pytest -q
```
