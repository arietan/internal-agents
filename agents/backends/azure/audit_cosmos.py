"""Azure audit backend — hash-chained records in Cosmos DB."""

import json
import logging
import os

from agents.core.audit import AuditRecord, AuditStore, compute_hash, compute_record_hash

log = logging.getLogger("backends.azure.audit")

CHAIN_HEAD_ID = "__chain_head__"


class CosmosAudit(AuditStore):
    """Hash-chained audit records in Cosmos DB (serverless, NoSQL API)."""

    def __init__(self):
        from azure.cosmos import CosmosClient
        endpoint = os.environ.get("COSMOS_ENDPOINT", "")
        key = os.environ.get("COSMOS_KEY", "")
        db_name = os.environ.get("COSMOS_DATABASE", "internal-agents")
        container_name = os.environ.get("COSMOS_CONTAINER", "audit-trail")

        if os.environ.get("COSMOS_USE_IDENTITY", "false").lower() == "true":
            from azure.identity import DefaultAzureCredential
            client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        else:
            client = CosmosClient(endpoint, credential=key)

        db = client.get_database_client(db_name)
        self._container = db.get_container_client(container_name)

    def write_record(self, record: AuditRecord) -> str:
        previous = self.get_chain_head()
        record_hash = compute_record_hash(record, previous)
        record.record_hash = record_hash

        item = record.to_dict()
        item["id"] = record.record_id
        item["partitionKey"] = record.run_id

        self._container.upsert_item(item)
        self._container.upsert_item({
            "id": CHAIN_HEAD_ID,
            "partitionKey": CHAIN_HEAD_ID,
            "chain_hash": record_hash,
        })

        log.info(
            "AUDIT [%s] agent=%s event=%s hash=%s…%s",
            record.record_id[:8], record.agent_name, record.event_type,
            record_hash[:8], record_hash[-8:],
        )
        return record_hash

    def get_chain_head(self) -> str:
        try:
            item = self._container.read_item(item=CHAIN_HEAD_ID, partition_key=CHAIN_HEAD_ID)
            return item.get("chain_hash", "0" * 64)
        except Exception:
            return "0" * 64

    def verify_chain(self) -> dict:
        query = "SELECT * FROM c WHERE c.id != @head ORDER BY c.timestamp"
        items = list(self._container.query_items(
            query=query,
            parameters=[{"name": "@head", "value": CHAIN_HEAD_ID}],
            enable_cross_partition_query=True,
        ))

        if not items:
            return {"status": "no_records", "verified": 0, "broken_at": None}

        prev_hash = "0" * 64
        verified = 0

        for item in items:
            if item.get("previous_hash") != prev_hash:
                return {"status": "chain_broken", "verified": verified, "broken_at": item.get("id")}

            stored = item.pop("record_hash", "")
            for key in ("id", "partitionKey", "_rid", "_self", "_etag", "_attachments", "_ts"):
                item.pop(key, None)
            chain_content = json.dumps(item, sort_keys=True, default=str)
            computed = compute_hash(chain_content + prev_hash)

            if stored != computed:
                return {"status": "tampered", "verified": verified, "broken_at": item.get("record_id")}

            prev_hash = stored
            verified += 1

        return {"status": "valid", "verified": verified, "broken_at": None}

    def query_by_time(self, agent_name: str, start: str, end: str) -> list[dict]:
        query = (
            "SELECT * FROM c WHERE c.agent_name = @agent "
            "AND c.timestamp >= @start AND c.timestamp <= @end"
        )
        return list(self._container.query_items(
            query=query,
            parameters=[
                {"name": "@agent", "value": agent_name},
                {"name": "@start", "value": start},
                {"name": "@end", "value": end},
            ],
            enable_cross_partition_query=True,
        ))
