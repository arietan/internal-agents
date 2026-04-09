FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ agents/

RUN useradd --create-home agent
USER agent

ENV PYTHONPATH=/app

# ─── Coding agent (batch job) ───────────────────────────────
FROM base AS coding-agent
ENTRYPOINT ["python", "agents/coding-agent/coding_agent.py"]

# ─── Coding agent webhook ───────────────────────────────────
FROM base AS coding-agent-webhook
EXPOSE 8080
ENTRYPOINT ["python", "agents/coding-agent/webhook_listener.py"]

# ─── PR review agent (batch job) ────────────────────────────
FROM base AS pr-review-agent
ENTRYPOINT ["python", "agents/pr-review-agent/pr_review_agent.py"]

# ─── PR review agent webhook ────────────────────────────────
FROM base AS pr-review-webhook
EXPOSE 8081
ENTRYPOINT ["python", "agents/pr-review-agent/webhook_listener.py"]

# ─── Self-healing: telemetry watcher (CronJob) ─────────────
FROM base AS telemetry-watcher
ENTRYPOINT ["python", "agents/self-healing/telemetry_watcher.py"]

# ─── Self-healing: alert receiver (webhook) ─────────────────
FROM base AS alert-receiver
EXPOSE 8082
ENTRYPOINT ["python", "agents/self-healing/alert_receiver.py"]
