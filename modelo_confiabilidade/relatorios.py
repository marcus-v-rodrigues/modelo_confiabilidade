"""Persistência, gráficos e relatório textual."""

from ._pipeline import (
    RESULT_TABLE_FILES,
    generate_plots,
    save_results,
    write_final_report,
)

__all__ = ["RESULT_TABLE_FILES", "generate_plots", "save_results", "write_final_report"]
