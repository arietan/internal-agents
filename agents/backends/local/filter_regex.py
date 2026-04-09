"""Local content filter backend — Python regex DLP scanner."""

import os
import re

from agents.core.content_filter import ContentFilter, FilterFinding

_PATTERNS = [
    (r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']+', "credential"),
    (r'(?i)(api[_-]?key|apikey|secret[_-]?key)\s*[:=]\s*["\']?[^\s"\']+', "api_key"),
    (r'(?i)(access[_-]?token|auth[_-]?token|bearer)\s*[:=]\s*["\']?[^\s"\']+', "token"),
    (r'(?i)-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', "private_key"),
    (r'(?i)(aws_access_key_id|aws_secret_access_key)\s*[:=]', "aws_credential"),
    (r'ghp_[A-Za-z0-9_]{36}', "github_pat"),
    (r'sk-[A-Za-z0-9]{48}', "openai_key"),
    (r'\b\d{3}-\d{2}-\d{4}\b', "ssn"),
    (r'\b[A-Z]\d{4}[A-Z]\b', "sg_nric_partial"),
    (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', "credit_card"),
]

_CRITICAL = {"private_key", "aws_credential", "credit_card"}


class RegexContentFilter(ContentFilter):
    """Scans text with regex patterns for credentials, PII, and secrets."""

    def __init__(self):
        self.enabled = os.environ.get("DLP_ENABLED", "true").lower() == "true"

    def scan(self, text: str, source: str = "prompt") -> list[FilterFinding]:
        if not self.enabled:
            return []
        findings: list[FilterFinding] = []
        for pattern, ptype in _PATTERNS:
            for match in re.finditer(pattern, text):
                snippet = match.group()
                if len(snippet) > 20:
                    snippet = snippet[:10] + "…" + snippet[-5:]
                findings.append(FilterFinding(
                    pattern_type=ptype,
                    severity="critical" if ptype in _CRITICAL else "high",
                    action="detected",
                    location=source,
                    snippet=snippet,
                ))
        return findings

    def redact(self, text: str) -> str:
        result = text
        for pattern, ptype in _PATTERNS:
            result = re.sub(pattern, f"[REDACTED:{ptype}]", result)
        return result
