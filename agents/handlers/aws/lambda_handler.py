"""AWS Lambda handlers wrapping agent entry points.

Each function receives a Step Functions event payload and returns
a result dict for the next state in the pipeline.
"""

import json
import logging
import os
import sys

os.environ.setdefault("CLOUD_PROVIDER", "aws")

log = logging.getLogger("lambda-handler")
log.setLevel(logging.INFO)


def coding_agent_handler(event, context):
    """Lambda handler for the coding agent."""
    from agents.coding_agent_entrypoint import run_coding_agent

    try:
        target_repo = event.get("target_repo") or os.environ.get("TARGET_REPO", "")
        issue_number = event.get("issue_number")
        pr_url = run_coding_agent(target_repo=target_repo, issue_number=issue_number)
        return {
            "statusCode": 200,
            "pr_url": pr_url,
            "target_repo": target_repo,
        }
    except Exception as e:
        log.exception("Coding agent failed")
        return {"statusCode": 500, "error": str(e)}


def review_agent_handler(event, context):
    """Lambda handler for the PR review agent."""
    from agents.review_agent_entrypoint import run_review_agent

    try:
        target_repo = event.get("target_repo") or os.environ.get("TARGET_REPO", "")
        pr_number = event.get("pr_number") or int(os.environ.get("PR_NUMBER", "0"))
        result = run_review_agent(target_repo=target_repo, pr_number=pr_number)
        return {
            "statusCode": 200,
            "recommendation": result.get("recommendation"),
            "issues_found": result.get("issues_found", 0),
        }
    except Exception as e:
        log.exception("Review agent failed")
        return {"statusCode": 500, "error": str(e)}


def watcher_handler(event, context):
    """Lambda handler for the telemetry watcher."""
    from agents.watcher_entrypoint import run_watcher

    try:
        result = run_watcher()
        return {
            "statusCode": 200,
            "issue_created": result.get("issue_created", False),
            "issue_url": result.get("issue_url", ""),
        }
    except Exception as e:
        log.exception("Telemetry watcher failed")
        return {"statusCode": 500, "error": str(e)}
