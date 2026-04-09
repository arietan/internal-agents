"""Abstract audit store interface for hash-chained compliance records."""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Optional
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone


@dataclass
class AuditRecord:
    """MAS AIRG-aligned audit record. Identical schema across all backends."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: str = ""
    agent_version: str = os.environ.get("AGENT_VERSION", "0.1.0")
    run_id: str = ""
    event_type: str = ""

    model_provider: str = ""
    model_name: str = ""
    model_version: str = ""

    input_hash: str = ""
    output_hash: str = ""
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    input_content: str = ""
    output_content: str = ""

    target_repo: str = ""
    pr_number: int = 0
    pr_url: str = ""
    files_changed: list = field(default_factory=list)
    risk_level: str = ""
    recommendation: str = ""

    dvw_facts: list = field(default_factory=list)
    dvw_assumptions: list = field(default_factory=list)
    dvw_reasoning: str = ""

    human_approver: str = ""
    human_action: str = ""
    human_action_timestamp: str = ""

    previous_hash: str = ""
    record_hash: str = ""

    trigger_event: str = ""
    data_classification: str = "internal"
    compliance_flags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def compute_hash(data: str) -> str:
    """SHA-256 hash used across all backends for chain integrity."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_record_hash(record: AuditRecord, previous_hash: str) -> str:
    """Compute the chain hash for a record. Same algorithm everywhere."""
    record.previous_hash = previous_hash
    chain_content = json.dumps(record.to_dict(), sort_keys=True, default=str)
    return compute_hash(chain_content + previous_hash)


class AuditStore(ABC):
    """Cloud-agnostic interface for hash-chained audit storage."""

    @abstractmethod
    def write_record(self, record: AuditRecord) -> str:
        """Write a hash-chained audit record. Returns record_hash."""
        ...

    @abstractmethod
    def get_chain_head(self) -> str:
        """Return the current chain head hash."""
        ...

    @abstractmethod
    def verify_chain(self) -> dict:
        """Verify full audit chain integrity.

        Returns:
            dict with keys: status (valid|chain_broken|tampered|no_records),
            verified (int), broken_at (str|None).
        """
        ...

    @abstractmethod
    def query_by_time(self, agent_name: str, start: str, end: str) -> list[dict]:
        """Query audit records by agent name and time range (ISO 8601)."""
        ...
