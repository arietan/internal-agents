"""AWS content filter backend — Bedrock Guardrails."""

import logging
import os

import boto3

from agents.core.content_filter import ContentFilter, FilterFinding

log = logging.getLogger("backends.aws.filter")


class GuardrailsFilter(ContentFilter):
    """Uses Bedrock Guardrails ApplyGuardrail API for PII + content filtering."""

    def __init__(self):
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._guardrail_id = os.environ.get("BEDROCK_GUARDRAIL_ID", "")
        self._guardrail_version = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

    def scan(self, text: str, source: str = "prompt") -> list[FilterFinding]:
        if not self._guardrail_id:
            log.warning("BEDROCK_GUARDRAIL_ID not set, skipping guardrail scan")
            return []

        resp = self._client.apply_guardrail(
            guardrailIdentifier=self._guardrail_id,
            guardrailVersion=self._guardrail_version,
            source="INPUT" if source in ("prompt", "llm_prompt") else "OUTPUT",
            content=[{"text": {"text": text}}],
        )

        findings: list[FilterFinding] = []
        action = resp.get("action", "NONE")

        for assessment in resp.get("assessments", []):
            for policy in assessment.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
                findings.append(FilterFinding(
                    pattern_type=policy.get("type", "PII"),
                    severity="critical" if policy.get("action") == "BLOCKED" else "high",
                    action=policy.get("action", "detected").lower(),
                    location=source,
                ))
            for regex_match in assessment.get("sensitiveInformationPolicy", {}).get("regexes", []):
                findings.append(FilterFinding(
                    pattern_type=regex_match.get("name", "regex"),
                    severity="critical",
                    action=regex_match.get("action", "detected").lower(),
                    location=source,
                ))
            for topic in assessment.get("topicPolicy", {}).get("topics", []):
                findings.append(FilterFinding(
                    pattern_type=f"topic:{topic.get('name', '')}",
                    severity="high",
                    action=topic.get("action", "detected").lower(),
                    location=source,
                ))

        if action == "GUARDRAIL_INTERVENED" and not findings:
            findings.append(FilterFinding(
                pattern_type="guardrail_intervention",
                severity="critical",
                action="blocked",
                location=source,
            ))

        return findings

    def redact(self, text: str) -> str:
        if not self._guardrail_id:
            return text
        resp = self._client.apply_guardrail(
            guardrailIdentifier=self._guardrail_id,
            guardrailVersion=self._guardrail_version,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
        for output in resp.get("outputs", []):
            if "text" in output:
                return output["text"]
        return text
