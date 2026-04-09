"""GCP audit backend — hash-chained records in Firestore."""

import json
import logging
import os

from agents.core.audit import AuditRecord, AuditStore, compute_hash, compute_record_hash

log = logging.getLogger("backends.gcp.audit")

CHAIN_HEAD_DOC = "__chain_head__"


class FirestoreAudit(AuditStore):
    """Hash-chained audit records stored in Firestore."""

    def __init__(self):
        from google.cloud import firestore
        self._db = firestore.Client(
            project=os.environ.get("GCP_PROJECT", ""),
            database=os.environ.get("FIRESTORE_DATABASE", "(default)"),
        )
        self._collection = os.environ.get("FIRESTORE_COLLECTION", "agent-audit-trail")

    def write_record(self, record: AuditRecord) -> str:
        previous = self.get_chain_head()
        record_hash = compute_record_hash(record, previous)
        record.record_hash = record_hash

        col = self._db.collection(self._collection)
        col.document(record.record_id).set(record.to_dict())
        col.document(CHAIN_HEAD_DOC).set({"chain_hash": record_hash})

        log.info(
            "AUDIT [%s] agent=%s event=%s hash=%s…%s",
            record.record_id[:8], record.agent_name, record.event_type,
            record_hash[:8], record_hash[-8:],
        )
        return record_hash

    def get_chain_head(self) -> str:
        doc = self._db.collection(self._collection).document(CHAIN_HEAD_DOC).get()
        if doc.exists:
            return doc.to_dict().get("chain_hash", "0" * 64)
        return "0" * 64

    def verify_chain(self) -> dict:
        docs = (
            self._db.collection(self._collection)
            .order_by("timestamp")
            .stream()
        )

        items = [d.to_dict() for d in docs if d.id != CHAIN_HEAD_DOC]
        if not items:
            return {"status": "no_records", "verified": 0, "broken_at": None}

        prev_hash = "0" * 64
        verified = 0

        for item in items:
            if item.get("previous_hash") != prev_hash:
                return {"status": "chain_broken", "verified": verified, "broken_at": item.get("record_id")}

            stored = item.pop("record_hash", "")
            chain_content = json.dumps(item, sort_keys=True, default=str)
            computed = compute_hash(chain_content + prev_hash)

            if stored != computed:
                return {"status": "tampered", "verified": verified, "broken_at": item.get("record_id")}

            prev_hash = stored
            verified += 1

        return {"status": "valid", "verified": verified, "broken_at": None}

    def query_by_time(self, agent_name: str, start: str, end: str) -> list[dict]:
        docs = (
            self._db.collection(self._collection)
            .where("agent_name", "==", agent_name)
            .where("timestamp", ">=", start)
            .where("timestamp", "<=", end)
            .order_by("timestamp")
            .stream()
        )
        return [d.to_dict() for d in docs]
