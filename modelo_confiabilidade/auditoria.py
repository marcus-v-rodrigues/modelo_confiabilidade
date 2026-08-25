"""Auditoria estrutural e quality gate das fontes."""

from ._pipeline import AUDIT_COLUMNS, audit_data_quality

__all__ = ["AUDIT_COLUMNS", "audit_data_quality"]
