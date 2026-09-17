# Referência da API Python

Esta pasta descreve os módulos, classes e funções disponíveis em `modelo_confiabilidade`. Os caminhos são relativos ao diretório do projeto.

## Módulos

- [`configuracao`](configuracao.md): configuração, argumentos CLI e logging.
- [`dados`](dados.md): leitura, normalização, hierarquia, agregação e lags.
- [`auditoria`](auditoria.md): auditoria de qualidade das fontes.
- [`modelagem`](modelagem.md): modelos, métricas e validação temporal.
- [`diagnosticos`](diagnosticos.md): diagnósticos estatísticos e validade.
- [`relatorios`](relatorios.md): CSVs, gráficos e relatório final.
- [`deploy`](deploy.md): exportação, carregamento e utilização dos modelos.
- [`__main__`](main.md): entrada programática da CLI.

## Uso mínimo

```python
from pathlib import Path
from modelo_confiabilidade.configuracao import Config
from modelo_confiabilidade.dados import load_indicator_files, load_operational_files

config = Config(input_dir=Path("./bases"))
indicators = load_indicator_files(config.input_dir)
operational = load_operational_files(config.input_dir)
```

As funções recebem e retornam principalmente `pandas.DataFrame`; os nomes e colunas esperados estão em [`../dicionario.md`](../dicionario.md). Funções iniciadas por `_` são internas e não constituem API pública estável.
