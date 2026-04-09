"""
Webhook listener for the PR Review Agent.

Listens for `pull_request.opened` and `pull_request.synchronize` events,
then spawns a K8s Job to review the PR.
"""

import hashlib
import hmac
import json
import logging
import os
import uuid

from flask import Flask, request, jsonify
from kubernetes import client as k8s_client, config as k8s_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pr-review-webhook")

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
JOB_NAMESPACE = os.environ.get("JOB_NAMESPACE", "ai-agents")
AGENT_IMAGE = os.environ.get("AGENT_IMAGE", "internal-agents/pr-review-agent:latest")
SERVICE_ACCOUNT = os.environ.get("JOB_SERVICE_ACCOUNT", "pr-review-agent-sa")
CODING_AGENT_LABEL = "ai-generated"


def verify_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        log.warning("SECURITY: No GITHUB_WEBHOOK_SECRET configured — rejecting request (MAS AIRG S1)")
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def spawn_review_job(repo: str, pr_number: int):
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()

    batch_v1 = k8s_client.BatchV1Api()
    run_id = str(uuid.uuid4())[:8]
    job_name = f"pr-review-{pr_number}-{run_id}"

    container = k8s_client.V1Container(
        name="pr-review-agent",
        image=AGENT_IMAGE,
        command=["python", "agents/pr-review-agent/pr_review_agent.py"],
        env=[
            k8s_client.V1EnvVar(name="TARGET_REPO", value=repo),
            k8s_client.V1EnvVar(name="PR_NUMBER", value=str(pr_number)),
        ],
        env_from=[
            k8s_client.V1EnvFromSource(
                secret_ref=k8s_client.V1SecretEnvSource(name="agent-secrets"),
            ),
            k8s_client.V1EnvFromSource(
                config_map_ref=k8s_client.V1ConfigMapEnvSource(name="agent-config"),
            ),
        ],
        volume_mounts=[
            k8s_client.V1VolumeMount(name="agent-config-vol", mount_path="/etc/agent", read_only=True),
        ],
        resources=k8s_client.V1ResourceRequirements(
            requests={"cpu": "250m", "memory": "256Mi"},
            limits={"cpu": "1", "memory": "1Gi"},
        ),
    )

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            namespace=JOB_NAMESPACE,
            labels={
                "app.kubernetes.io/name": "pr-review-agent",
                "app.kubernetes.io/part-of": "internal-agents",
            },
        ),
        spec=k8s_client.V1JobSpec(
            ttl_seconds_after_finished=3600,
            backoff_limit=1,
            activeDeadlineSeconds=600,
            template=k8s_client.V1PodTemplateSpec(
                spec=k8s_client.V1PodSpec(
                    service_account_name=SERVICE_ACCOUNT,
                    restart_policy="Never",
                    containers=[container],
                    volumes=[
                        k8s_client.V1Volume(
                            name="agent-config-vol",
                            config_map=k8s_client.V1ConfigMapVolumeSource(name="agent-skills-rules"),
                        ),
                    ],
                ),
            ),
        ),
    )

    batch_v1.create_namespaced_job(namespace=JOB_NAMESPACE, body=job)
    log.info("Spawned review job %s for %s PR #%d", job_name, repo, pr_number)
    return job_name


@app.route("/webhook/github", methods=["POST"])
def github_webhook():
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.data, signature):
        return jsonify({"error": "invalid signature"}), 403

    event = request.headers.get("X-GitHub-Event", "")
    payload = request.get_json(silent=True) or {}

    if event != "pull_request":
        return jsonify({"status": "ignored", "event": event}), 200

    action = payload.get("action", "")
    if action not in ("opened", "synchronize"):
        return jsonify({"status": "ignored", "action": action}), 200

    pr = payload.get("pull_request", {})
    repo = payload["repository"]["full_name"]
    pr_number = pr.get("number", 0)

    # Only auto-review PRs from the coding agent (labelled ai-generated)
    # or allow all PRs if no label filter is desired
    labels = [l.get("name", "") for l in pr.get("labels", [])]
    is_ai_pr = CODING_AGENT_LABEL in labels
    review_all = os.environ.get("REVIEW_ALL_PRS", "false").lower() == "true"

    if not is_ai_pr and not review_all:
        log.info("Skipping PR #%d (no '%s' label and REVIEW_ALL_PRS=false)", pr_number, CODING_AGENT_LABEL)
        return jsonify({"status": "skipped", "reason": "not ai-generated"}), 200

    job = spawn_review_job(repo, pr_number)
    return jsonify({"status": "job_created", "job": job, "pr": pr_number}), 201


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/readyz")
def readyz():
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    app.run(host="0.0.0.0", port=port)
