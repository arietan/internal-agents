"""Local audit backend — hash-chained JSON files on disk."""

import json
import logging
import os
from pathlib import Path

from agents.core.audit import AuditRecord, AuditStore, compute_hash, compute_record_hash

log = logging.getLogger("backends.local.audit")


class FilesystemAudit(AuditStore):
    """Writes hash-chained audit records as JSON files to a local directory."""

    def __init__(self, audit_dir: str | None = None):
        self._dir = Path(audit_dir or os.environ.get("AUDIT_LOG_DIR", "/var/log/agent-audit"))
        self._chain_file = self._dir / ".chain_head"

    def write_record(self, record: AuditRecord) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)

        previous = self.get_chain_head()
        record_hash = compute_record_hash(record, previous)
        record.record_hash = record_hash

        filepath = self._dir / f"{record.timestamp[:10]}_{record.record_id}.json"
        filepath.write_text(json.dumps(record.to_dict(), indent=2, default=str))
        self._chain_file.write_text(record_hash)

        log.info(
            "AUDIT [%s] agent=%s event=%s hash=%s…%s",
            record.record_id[:8], record.agent_name, record.event_type,
            record_hash[:8], record_hash[-8:],
        )
        return record_hash

    def get_chain_head(self) -> str:
        if self._chain_file.exists():
            return self._chain_file.read_text().strip()
        return "0" * 64

    def verify_chain(self) -> dict:
        if not self._dir.exists():
            return {"status": "no_records", "verified": 0, "broken_at": None}

        files = sorted(self._dir.glob("*.json"))
        prev_hash = "0" * 64
        verified = 0

        for f in files:
            try:
                data = json.loads(f.read_text())
            except json.JSONDecodeError:
                return {"status": "corrupt", "verified": verified, "broken_at": str(f)}

            if data.get("previous_hash") != prev_hash:
                return {
                    "status": "chain_broken", "verified": verified,
                    "broken_at": str(f),
                    "expected_prev": prev_hash, "found_prev": data.get("previous_hash"),
                }

            stored_hash = data.pop("record_hash", "")
            chain_content = json.dumps(data, sort_keys=True, default=str)
            computed = compute_hash(chain_content + prev_hash)
            data["record_hash"] = stored_hash

            if stored_hash != computed:
                return {"status": "tampered", "verified": verified, "broken_at": str(f)}

            prev_hash = stored_hash
            verified += 1

        return {"status": "valid", "verified": verified, "broken_at": None}

    def query_by_time(self, agent_name: str, start: str, end: str) -> list[dict]:
        results = []
        if not self._dir.exists():
            return results
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue
            ts = data.get("timestamp", "")
            if data.get("agent_name") == agent_name and start <= ts <= end:
                results.append(data)
        return results
