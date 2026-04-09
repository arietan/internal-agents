"""GCP content filter backend — Cloud DLP API."""

import logging
import os

from agents.core.content_filter import ContentFilter, FilterFinding

log = logging.getLogger("backends.gcp.filter")


class DlpFilter(ContentFilter):
    """Uses Cloud DLP API (200+ info types) for content inspection and redaction."""

    def __init__(self):
        self._project = os.environ.get("GCP_PROJECT", "")
        self._client = None

    def _get_client(self):
        if not self._client:
            from google.cloud import dlp_v2
            self._client = dlp_v2.DlpServiceClient()
        return self._client

    def scan(self, text: str, source: str = "prompt") -> list[FilterFinding]:
        if not self._project:
            log.warning("GCP_PROJECT not set, skipping DLP scan")
            return []

        client = self._get_client()
        parent = f"projects/{self._project}"

        inspect_config = {
            "info_types": [
                {"name": "CREDIT_CARD_NUMBER"},
                {"name": "EMAIL_ADDRESS"},
                {"name": "PHONE_NUMBER"},
                {"name": "US_SOCIAL_SECURITY_NUMBER"},
                {"name": "AWS_CREDENTIALS"},
                {"name": "GCP_API_KEY"},
                {"name": "ENCRYPTION_KEY"},
                {"name": "PASSWORD"},
            ],
            "min_likelihood": "LIKELY",
            "include_quote": False,
        }

        try:
            response = client.inspect_content(
                request={
                    "parent": parent,
                    "inspect_config": inspect_config,
                    "item": {"value": text[:500000]},
                }
            )
        except Exception as e:
            log.error("DLP scan failed: %s", e)
            return []

        findings: list[FilterFinding] = []
        for finding in response.result.findings:
            likelihood = finding.likelihood.name
            findings.append(FilterFinding(
                pattern_type=finding.info_type.name,
                severity="critical" if likelihood in ("VERY_LIKELY", "POSSIBLE") else "high",
                action="detected",
                location=source,
            ))

        return findings

    def redact(self, text: str) -> str:
        if not self._project:
            return text

        client = self._get_client()
        parent = f"projects/{self._project}"

        deidentify_config = {
            "info_type_transformations": {
                "transformations": [{
                    "primitive_transformation": {
                        "replace_config": {
                            "new_value": {"string_value": "[REDACTED]"},
                        },
                    },
                }],
            },
        }

        try:
            response = client.deidentify_content(
                request={
                    "parent": parent,
                    "deidentify_config": deidentify_config,
                    "item": {"value": text},
                }
            )
            return response.item.value
        except Exception as e:
            log.error("DLP redaction failed: %s", e)
            return text
