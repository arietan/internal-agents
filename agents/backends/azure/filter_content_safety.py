"""Azure content filter backend — AI Content Safety."""

import logging
import os

from agents.core.content_filter import ContentFilter, FilterFinding

log = logging.getLogger("backends.azure.filter")


class ContentSafetyFilter(ContentFilter):
    """Uses Azure AI Content Safety for text moderation + PII detection."""

    def __init__(self):
        self._endpoint = os.environ.get("CONTENT_SAFETY_ENDPOINT", "")
        self._key = os.environ.get("CONTENT_SAFETY_KEY", "")
        self._client = None

    def _get_client(self):
        if not self._client:
            from azure.ai.contentsafety import ContentSafetyClient
            from azure.core.credentials import AzureKeyCredential
            if os.environ.get("CONTENT_SAFETY_USE_IDENTITY", "false").lower() == "true":
                from azure.identity import DefaultAzureCredential
                self._client = ContentSafetyClient(self._endpoint, DefaultAzureCredential())
            else:
                self._client = ContentSafetyClient(self._endpoint, AzureKeyCredential(self._key))
        return self._client

    def scan(self, text: str, source: str = "prompt") -> list[FilterFinding]:
        if not self._endpoint:
            log.warning("CONTENT_SAFETY_ENDPOINT not set, skipping scan")
            return []

        from azure.ai.contentsafety.models import AnalyzeTextOptions

        client = self._get_client()
        request = AnalyzeTextOptions(text=text[:10000])

        try:
            response = client.analyze_text(request)
        except Exception as e:
            log.error("Content Safety scan failed: %s", e)
            return []

        findings: list[FilterFinding] = []
        categories = response.categories_analysis or []
        for cat in categories:
            if cat.severity and cat.severity >= 2:
                findings.append(FilterFinding(
                    pattern_type=f"content:{cat.category}",
                    severity="critical" if cat.severity >= 4 else "high",
                    action="blocked" if cat.severity >= 4 else "detected",
                    location=source,
                ))

        return findings

    def redact(self, text: str) -> str:
        findings = self.scan(text)
        if not findings:
            return text
        from agents.backends.local.filter_regex import RegexContentFilter
        return RegexContentFilter().redact(text)
