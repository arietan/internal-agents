"""Portable audit writing — delegates to the active AuditStore backend."""

import logging

from agents.core.audit import AuditRecord, compute_hash
from agents.core.factory import get_audit

log = logging.getLogger("tools.audit_writer")


def write_record(record: AuditRecord) -> str:
    """Write a hash-chained audit record via the configured backend.

    Returns the record hash.
    """
    return get_audit().write_record(record)


def hash_content(content: str) -> str:
    """SHA-256 hash helper (re-exported for convenience)."""
    return compute_hash(content)
