"""
Webhook listener for the Coding Agent.

Runs as a long-lived K8s Deployment.  Accepts GitHub webhook events
(push / pull_request merged) and spawns a K8s Job for the coding agent.

Endpoints
─────────
  POST /webhook/github  – GitHub webhook receiver
  GET  /healthz         – liveness probe
  GET  /readyz          – readiness probe
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
log = logging.getLogger("webhook-listener")

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
JOB_NAMESPACE = os.environ.get("JOB_NAMESPACE", "ai-agents")
AGENT_IMAGE = os.environ.get("AGENT_IMAGE", "internal-agents/coding-agent:latest")
SERVICE_ACCOUNT = os.environ.get("JOB_SERVICE_ACCOUNT", "coding-agent-sa")


def verify_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        log.warning("SECURITY: No GITHUB_WEBHOOK_SECRET configured — rejecting request (MAS AIRG S1)")
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def spawn_coding_job(repo_full_name: str, trigger_event: str, ref: str = ""):
    """Create a K8s Job that runs the coding agent for the given repo."""
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()

    batch_v1 = k8s_client.BatchV1Api()
    run_id = str(uuid.uuid4())[:8]
    job_name = f"coding-agent-{run_id}"

    env_from = [
        k8s_client.V1EnvFromSource(
            secret_ref=k8s_client.V1SecretEnvSource(name="agent-secrets")
        ),
        k8s_client.V1EnvFromSource(
            config_map_ref=k8s_client.V1ConfigMapEnvSource(name="agent-config")
        ),
    ]

    container = k8s_client.V1Container(
        name="coding-agent",
        image=AGENT_IMAGE,
        command=["python", "agents/coding-agent/coding_agent.py"],
        env=[
            k8s_client.V1EnvVar(name="TARGET_REPO", value=repo_full_name),
            k8s_client.V1EnvVar(name="TRIGGER_EVENT", value=trigger_event),
        ],
        env_from=env_from,
        volume_mounts=[
            k8s_client.V1VolumeMount(name="agent-config-vol", mount_path="/etc/agent", read_only=True),
        ],
        resources=k8s_client.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "512Mi"},
            limits={"cpu": "2", "memory": "2Gi"},
        ),
    )

    volumes = [
        k8s_client.V1Volume(
            name="agent-config-vol",
            config_map=k8s_client.V1ConfigMapVolumeSource(name="agent-skills-rules"),
        ),
    ]

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=job_name,
            namespace=JOB_NAMESPACE,
            labels={
                "app.kubernetes.io/name": "coding-agent",
                "app.kubernetes.io/part-of": "internal-agents",
                "agent-run-id": run_id,
            },
        ),
        spec=k8s_client.V1JobSpec(
            ttl_seconds_after_finished=3600,
            backoff_limit=1,
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels={"app.kubernetes.io/name": "coding-agent"}),
                spec=k8s_client.V1PodSpec(
                    service_account_name=SERVICE_ACCOUNT,
                    restart_policy="Never",
                    containers=[container],
                    volumes=volumes,
                ),
            ),
        ),
    )

    batch_v1.create_namespaced_job(namespace=JOB_NAMESPACE, body=job)
    log.info("Spawned job %s for repo=%s trigger=%s", job_name, repo_full_name, trigger_event)
    return job_name


@app.route("/webhook/github", methods=["POST"])
def github_webhook():
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.data, signature):
        return jsonify({"error": "invalid signature"}), 403

    event = request.headers.get("X-GitHub-Event", "")
    payload = request.get_json(silent=True) or {}

    if event == "pull_request" and payload.get("action") == "closed":
        pr = payload.get("pull_request", {})
        if pr.get("merged"):
            repo = payload["repository"]["full_name"]
            ref = pr.get("merge_commit_sha", "")
            job = spawn_coding_job(repo, "pr_merged", ref)
            return jsonify({"status": "job_created", "job": job}), 201

    if event == "push":
        repo = payload["repository"]["full_name"]
        ref = payload.get("ref", "")
        job = spawn_coding_job(repo, "push", ref)
        return jsonify({"status": "job_created", "job": job}), 201

    return jsonify({"status": "ignored", "event": event}), 200


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/readyz")
def readyz():
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
