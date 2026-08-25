"""Entry point for ``python -m modelo_confiabilidade``."""

from __future__ import annotations

from typing import Sequence

from ._pipeline import main as _run_pipeline


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validated pipeline through the package namespace."""
    return _run_pipeline(argv)


if __name__ == "__main__":
    raise SystemExit(main())
