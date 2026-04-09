"""Azure Functions handlers wrapping agent entry points.

Uses the Azure Functions Python v2 programming model.
Designed for Durable Functions orchestration.
"""

import json
import logging
import os

import azure.functions as func

os.environ.setdefault("CLOUD_PROVIDER", "azure")

app = func.FunctionApp()
log = logging.getLogger("azure-functions")


@app.function_name("coding-agent")
@app.route(route="coding-agent", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def coding_agent_handler(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP-triggered handler for the coding agent."""
    from agents.coding_agent_entrypoint import run_coding_agent

    try:
        body = req.get_json() if req.get_body() else {}
        target_repo = body.get("target_repo") or os.environ.get("TARGET_REPO", "")
        pr_url = run_coding_agent(target_repo=target_repo, issue_number=body.get("issue_number"))
        return func.HttpResponse(
            json.dumps({"pr_url": pr_url, "target_repo": target_repo}),
            status_code=200, mimetype="application/json",
        )
    except Exception as e:
        log.exception("Coding agent failed")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


@app.function_name("review-agent")
@app.route(route="review-agent", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def review_agent_handler(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP-triggered handler for the PR review agent."""
    from agents.review_agent_entrypoint import run_review_agent

    try:
        body = req.get_json() if req.get_body() else {}
        target_repo = body.get("target_repo") or os.environ.get("TARGET_REPO", "")
        pr_number = body.get("pr_number") or int(os.environ.get("PR_NUMBER", "0"))
        result = run_review_agent(target_repo=target_repo, pr_number=pr_number)
        return func.HttpResponse(json.dumps(result), status_code=200, mimetype="application/json")
    except Exception as e:
        log.exception("Review agent failed")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)


@app.function_name("telemetry-watcher")
@app.timer_trigger(schedule="0 */15 * * * *", arg_name="timer", run_on_startup=False)
def watcher_handler(timer: func.TimerRequest) -> None:
    """Timer-triggered handler for the telemetry watcher."""
    from agents.watcher_entrypoint import run_watcher

    try:
        result = run_watcher()
        log.info("Watcher result: %s", result)
    except Exception:
        log.exception("Telemetry watcher failed")
