"""AWS audit backend — hash-chained records in DynamoDB."""

import json
import logging
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from agents.core.audit import AuditRecord, AuditStore, compute_hash, compute_record_hash

log = logging.getLogger("backends.aws.audit")

CHAIN_HEAD_PK = "CHAIN#HEAD"
CHAIN_HEAD_SK = "CHAIN#HEAD"


class DynamoDBAudit(AuditStore):
    """Hash-chained audit records stored in a DynamoDB table.

    Table schema (provisioned by Terraform):
        PK (S): RUN#<run_id>
        SK (S): RECORD#<record_id>
        GSI by-timestamp: agent_name (S), timestamp (S)
        GSI by-repo: target_repo (S), timestamp (S)
        Special item: PK=CHAIN#HEAD, SK=CHAIN#HEAD stores current chain hash.
    """

    def __init__(self):
        table_name = os.environ.get("AUDIT_TABLE", "agent-audit-trail")
        region = os.environ.get("AWS_REGION", "us-east-1")
        dynamodb = boto3.resource("dynamodb", region_name=region)
        self._table = dynamodb.Table(table_name)

    def write_record(self, record: AuditRecord) -> str:
        previous = self.get_chain_head()
        record_hash = compute_record_hash(record, previous)
        record.record_hash = record_hash

        item = _sanitize(record.to_dict())
        item["PK"] = f"RUN#{record.run_id}"
        item["SK"] = f"RECORD#{record.record_id}"

        self._table.put_item(Item=item)

        self._table.put_item(Item={
            "PK": CHAIN_HEAD_PK,
            "SK": CHAIN_HEAD_SK,
            "chain_hash": record_hash,
        })

        log.info(
            "AUDIT [%s] agent=%s event=%s hash=%s…%s",
            record.record_id[:8], record.agent_name, record.event_type,
            record_hash[:8], record_hash[-8:],
        )
        return record_hash

    def get_chain_head(self) -> str:
        resp = self._table.get_item(Key={"PK": CHAIN_HEAD_PK, "SK": CHAIN_HEAD_SK})
        item = resp.get("Item")
        if item:
            return item.get("chain_hash", "0" * 64)
        return "0" * 64

    def verify_chain(self) -> dict:
        items = []
        params: dict = {"FilterExpression": Key("PK").begins_with("RUN#")}
        while True:
            resp = self._table.scan(**params)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

        if not items:
            return {"status": "no_records", "verified": 0, "broken_at": None}

        items.sort(key=lambda x: x.get("timestamp", ""))
        prev_hash = "0" * 64
        verified = 0

        for item in items:
            if item.get("previous_hash") != prev_hash:
                return {
                    "status": "chain_broken", "verified": verified,
                    "broken_at": item.get("record_id", "unknown"),
                }

            stored = item.pop("record_hash", "")
            for key in ("PK", "SK"):
                item.pop(key, None)
            chain_content = json.dumps(_to_native(item), sort_keys=True, default=str)
            computed = compute_hash(chain_content + prev_hash)
            item["record_hash"] = stored

            if stored != computed:
                return {"status": "tampered", "verified": verified, "broken_at": item.get("record_id")}

            prev_hash = stored
            verified += 1

        return {"status": "valid", "verified": verified, "broken_at": None}

    def query_by_time(self, agent_name: str, start: str, end: str) -> list[dict]:
        resp = self._table.query(
            IndexName="by-timestamp",
            KeyConditionExpression=Key("agent_name").eq(agent_name) & Key("timestamp").between(start, end),
        )
        return [_to_native(i) for i in resp.get("Items", [])]


def _sanitize(d: dict) -> dict:
    """Convert floats to Decimal for DynamoDB and drop empty strings."""
    clean = {}
    for k, v in d.items():
        if isinstance(v, float):
            clean[k] = Decimal(str(v))
        elif isinstance(v, dict):
            clean[k] = _sanitize(v)
        elif v == "":
            continue
        else:
            clean[k] = v
    return clean


def _to_native(d: dict) -> dict:
    """Convert Decimals back to int/float for JSON serialization."""
    out = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v == int(v) else float(v)
        elif isinstance(v, dict):
            out[k] = _to_native(v)
        else:
            out[k] = v
    return out
