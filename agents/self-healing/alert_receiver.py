"""
Alert Receiver — Alertmanager webhook endpoint.

Receives Alertmanager webhook POSTs (real-time path) and creates GitHub
issues labelled ``ai-agent`` for the Coding Agent to pick up.  Complements
the CronJob-based Telemetry Watcher with sub-minute reaction time.

Endpoints
─────────
  POST /webhook/alertmanager  – Alertmanager webhook receiver
  GET  /healthz               – liveness probe
  GET  /readyz                – readiness probe

Environment variables:
  GITHUB_TOKEN             – PAT with repo + issues write scope
  TARGET_REPO              – owner/repo to create issues against
  HEALING_ENABLED          – "true" to enable (default: true)
  HEALING_COOLDOWN_MINUTES – per-alert dedup window (default: 30)
"""

import hashlib
import json
import logging
import os
import subprocess
import textwrap
import time

from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("alert-receiver")

app = Flask(__name__)

def _get_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            from agents.core.factory import get_secrets
            token = get_secrets().get_secret("GITHUB_TOKEN")
        except (KeyError, ImportError):
            pass
    return token


GITHUB_TOKEN = _get_github_token()
TARGET_REPO = os.environ.get("TARGET_REPO", "")
HEALING_ENABLED = os.environ.get("HEALING_ENABLED", "true").lower() == "true"
COOLDOWN_MINUTES = int(os.environ.get("HEALING_COOLDOWN_MINUTES", "30"))

_recent_fingerprints: dict[str, float] = {}


def _gh(*args: str) -> str:
    env = {**os.environ, "GH_TOKEN": GITHUB_TOKEN}
    result = subprocess.run(["gh", *args], capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh command failed: {' '.join(args)}")
    return result.stdout.strip()


def _fingerprint(labels: dict) -> str:
    """Stable fingerprint for deduplication."""
    key = json.dumps(
        {k: v for k, v in sorted(labels.items()) if k not in ("instance", "pod")},
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _in_cooldown(fp: str) -> bool:
    """Return True if this fingerprint was seen within the cooldown window."""
    now = time.time()
    _cleanup_cooldown(now)
    if fp in _recent_fingerprints:
        return True
    return False


def _record_cooldown(fp: str):
    _recent_fingerprints[fp] = time.time()


def _cleanup_cooldown(now: float):
    cutoff = now - (COOLDOWN_MINUTES * 60)
    expired = [k for k, v in _recent_fingerprints.items() if v < cutoff]
    for k in expired:
        del _recent_fingerprints[k]


def _find_existing_issue(fp: str) -> bool:
    """Check if an open issue with this fingerprint already exists."""
    try:
        raw = _gh(
            "issue", "list",
            "--repo", TARGET_REPO,
            "--label", "ai-agent",
            "--state", "open",
            "--json", "body",
            "--limit", "50",
        )
        issues = json.loads(raw) if raw else []
        return any(f"fingerprint:{fp}" in (iss.get("body", "")) for iss in issues)
    except Exception as exc:
        log.warning("Issue dedup check failed: %s", exc)
        return False


def create_issue_from_alert(alert: dict) -> str:
    """Create a GitHub issue from an Alertmanager alert."""
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    alert_name = labels.get("alertname", "UnknownAlert")
    severity = labels.get("severity", "warning")
    summary = annotations.get("summary", "No summary")
    description = annotations.get("description", "")
    fp = _fingerprint(labels)

    title = f"[self-healing] Alert: {alert_name}"
    body = textwrap.dedent(f"""\
        ## Self-Healing Alert

        **Alert:** {alert_name}
        **Severity:** {severity}
        **Status:** {alert.get('status', 'firing')}

        ### Summary
        {summary}

        ### Description
        {description}

        ### Labels
        ```json
        {json.dumps(labels, indent=2)}
        ```

        ### Annotations
        ```json
        {json.dumps(annotations, indent=2)}
        ```

        ---
        _Created by the self-healing alert receiver. fingerprint:{fp}_
    """)

    issue_url = _gh(
        "issue", "create",
        "--repo", TARGET_REPO,
        "--title", title,
        "--body", body,
        "--label", "ai-agent",
    )
    _record_cooldown(fp)
    return issue_url


@app.route("/webhook/alertmanager", methods=["POST"])
def alertmanager_webhook():
    if not HEALING_ENABLED:
        return jsonify({"status": "disabled"}), 200

    if not GITHUB_TOKEN or not TARGET_REPO:
        log.error("GITHUB_TOKEN and TARGET_REPO must be configured")
        return jsonify({"error": "not configured"}), 500

    payload = request.get_json(silent=True) or {}
    alerts = payload.get("alerts", [])
    status = payload.get("status", "unknown")

    log.info("Received %d alerts (group status=%s)", len(alerts), status)

    created = []
    skipped = []

    for alert in alerts:
        if alert.get("status") != "firing":
            skipped.append({"alert": alert.get("labels", {}).get("alertname"), "reason": "not firing"})
            continue

        labels = alert.get("labels", {})
        fp = _fingerprint(labels)
        alert_name = labels.get("alertname", "unknown")

        if _in_cooldown(fp):
            skipped.append({"alert": alert_name, "reason": "cooldown"})
            log.info("Alert %s in cooldown — skipping", alert_name)
            continue

        if _find_existing_issue(fp):
            _record_cooldown(fp)
            skipped.append({"alert": alert_name, "reason": "issue exists"})
            log.info("Alert %s already has open issue — skipping", alert_name)
            continue

        try:
            issue_url = create_issue_from_alert(alert)
            created.append({"alert": alert_name, "issue": issue_url})
            log.info("Created issue for alert %s: %s", alert_name, issue_url)
        except Exception as exc:
            log.error("Failed to create issue for alert %s: %s", alert_name, exc)
            skipped.append({"alert": alert_name, "reason": f"error: {exc}"})

    return jsonify({
        "status": "processed",
        "created": len(created),
        "skipped": len(skipped),
        "details": {"created": created, "skipped": skipped},
    }), 201 if created else 200


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/readyz")
def readyz():
    if not GITHUB_TOKEN or not TARGET_REPO:
        return "not configured", 503
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8082"))
    app.run(host="0.0.0.0", port=port)
