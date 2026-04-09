"""GCP Cloud Functions (2nd gen) handlers wrapping agent entry points.

Each function is an HTTP-triggered Cloud Function that receives
a JSON payload from Cloud Workflows.
"""

import json
import logging
import os

import functions_framework

os.environ.setdefault("CLOUD_PROVIDER", "gcp")

log = logging.getLogger("cloud-functions")


@functions_framework.http
def coding_agent_handler(request):
    """HTTP Cloud Function for the coding agent."""
    from agents.coding_agent_entrypoint import run_coding_agent

    try:
        body = request.get_json(silent=True) or {}
        target_repo = body.get("target_repo") or os.environ.get("TARGET_REPO", "")
        pr_url = run_coding_agent(target_repo=target_repo, issue_number=body.get("issue_number"))
        return json.dumps({"pr_url": pr_url, "target_repo": target_repo}), 200
    except Exception as e:
        log.exception("Coding agent failed")
        return json.dumps({"error": str(e)}), 500


@functions_framework.http
def review_agent_handler(request):
    """HTTP Cloud Function for the PR review agent."""
    from agents.review_agent_entrypoint import run_review_agent

    try:
        body = request.get_json(silent=True) or {}
        target_repo = body.get("target_repo") or os.environ.get("TARGET_REPO", "")
        pr_number = body.get("pr_number") or int(os.environ.get("PR_NUMBER", "0"))
        result = run_review_agent(target_repo=target_repo, pr_number=pr_number)
        return json.dumps(result), 200
    except Exception as e:
        log.exception("Review agent failed")
        return json.dumps({"error": str(e)}), 500


@functions_framework.http
def watcher_handler(request):
    """HTTP Cloud Function for the telemetry watcher."""
    from agents.watcher_entrypoint import run_watcher

    try:
        result = run_watcher()
        return json.dumps(result), 200
    except Exception as e:
        log.exception("Telemetry watcher failed")
        return json.dumps({"error": str(e)}), 500
