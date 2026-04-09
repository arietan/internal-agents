.PHONY: help build build-local push deploy deploy-local destroy test lint \
       run-coding-agent run-review-agent \
       models-deploy models-destroy models-status model-pull \
       healing-deploy healing-destroy healing-status healing-logs healing-test

REGISTRY    ?= ghcr.io/<YOUR_ORG>
TAG         ?= latest
CONTEXT     ?= $(shell kubectl config current-context)
OVERLAY     ?= local
MODEL       ?= qwen2.5-coder:32b

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-28s\033[0m %s\n", $$1, $$2}'

# ── Build ───────────────────────────────────────────────────────

build: ## Build all agent images
	docker build --target coding-agent         -t $(REGISTRY)/coding-agent:$(TAG)         .
	docker build --target coding-agent-webhook -t $(REGISTRY)/coding-agent-webhook:$(TAG) .
	docker build --target pr-review-agent      -t $(REGISTRY)/pr-review-agent:$(TAG)      .
	docker build --target pr-review-webhook    -t $(REGISTRY)/pr-review-webhook:$(TAG)    .
	docker build --target telemetry-watcher    -t $(REGISTRY)/telemetry-watcher:$(TAG)    .
	docker build --target alert-receiver       -t $(REGISTRY)/alert-receiver:$(TAG)       .

build-local: ## Build images for local K8s (kind / minikube / Docker Desktop)
	docker build --target coding-agent         -t internal-agents/coding-agent:local         .
	docker build --target coding-agent-webhook -t internal-agents/coding-agent-webhook:local .
	docker build --target pr-review-agent      -t internal-agents/pr-review-agent:local      .
	docker build --target pr-review-webhook    -t internal-agents/pr-review-webhook:local    .
	docker build --target telemetry-watcher    -t internal-agents/telemetry-watcher:local    .
	docker build --target alert-receiver       -t internal-agents/alert-receiver:local       .
	@echo ""
	@echo "For kind:     kind load docker-image internal-agents/coding-agent:local ..."
	@echo "For minikube: eval \$$(minikube docker-env) && make build-local"

push: build ## Push images to registry
	docker push $(REGISTRY)/coding-agent:$(TAG)
	docker push $(REGISTRY)/coding-agent-webhook:$(TAG)
	docker push $(REGISTRY)/pr-review-agent:$(TAG)
	docker push $(REGISTRY)/pr-review-webhook:$(TAG)
	docker push $(REGISTRY)/telemetry-watcher:$(TAG)
	docker push $(REGISTRY)/alert-receiver:$(TAG)

# ── Deploy ──────────────────────────────────────────────────────

deploy: ## Deploy to cluster (OVERLAY=local|staging|prod)
	kubectl apply -k k8s/overlays/$(OVERLAY)

deploy-local: build-local deploy ## Build locally and deploy to local cluster
	@echo "==> Deployed to local cluster."

destroy: ## Remove all agent resources
	kubectl delete -k k8s/overlays/$(OVERLAY) --ignore-not-found

# ── Secrets (local dev) ────────────────────────────────────────

secrets-create: ## Create secrets from .env file (local dev only)
	@test -f .env || (echo "Create a .env file first (see k8s/base/secrets.yaml for keys)" && exit 1)
	kubectl create secret generic agent-secrets \
		--namespace ai-agents \
		--from-env-file=.env \
		--dry-run=client -o yaml | kubectl apply -f -

# ── Run locally (outside K8s) ──────────────────────────────────

run-coding-agent: ## Run coding agent locally (reads .env)
	@test -f .env && export $$(cat .env | xargs) || true; \
	python -m agents.coding-agent.coding_agent

run-review-agent: ## Run PR review agent locally (reads .env)
	@test -f .env && export $$(cat .env | xargs) || true; \
	python -m agents.pr-review-agent.pr_review_agent

run-coding-webhook: ## Run coding agent webhook server locally
	@test -f .env && export $$(cat .env | xargs) || true; \
	python -m agents.coding-agent.webhook_listener

run-review-webhook: ## Run PR review webhook server locally
	@test -f .env && export $$(cat .env | xargs) || true; \
	python -m agents.pr-review-agent.webhook_listener

run-telemetry-watcher: ## Run telemetry watcher locally (one-shot)
	@test -f .env && export $$(cat .env | xargs) || true; \
	python agents/self-healing/telemetry_watcher.py

run-alert-receiver: ## Run alert receiver webhook server locally
	@test -f .env && export $$(cat .env | xargs) || true; \
	python agents/self-healing/alert_receiver.py

# ── Test & Lint ────────────────────────────────────────────────

test: ## Run agent tests
	python -m pytest tests/ -v --tb=short

lint: ## Validate YAML manifests and Python code
	@echo "==> Validating YAML..."
	@find k8s/ agents/ -name '*.yaml' | xargs -I{} sh -c \
		'python -c "import yaml; yaml.safe_load(open(\"{}\"))" 2>&1 || echo "FAIL: {}"'
	@echo "==> Checking Python..."
	@python -m py_compile agents/coding-agent/coding_agent.py
	@python -m py_compile agents/coding-agent/webhook_listener.py
	@python -m py_compile agents/pr-review-agent/pr_review_agent.py
	@python -m py_compile agents/pr-review-agent/webhook_listener.py
	@python -m py_compile agents/self-healing/telemetry_watcher.py
	@python -m py_compile agents/self-healing/alert_receiver.py
	@echo "==> All checks passed."

# ── Models (self-hosted LLM) ───────────────────────────────────

models-deploy: ## Deploy Ollama + LiteLLM gateway to cluster
	@echo "==> Creating ai-models namespace..."
	kubectl apply -f k8s/base/models/ollama/deployment.yaml
	@echo "==> Deploying LiteLLM proxy..."
	kubectl apply -f k8s/base/models/litellm/deployment.yaml
	@echo "==> Waiting for Ollama to be ready..."
	kubectl -n ai-models rollout status deployment/ollama --timeout=120s || true
	@echo "==> Models stack deployed. Run 'make model-pull' to download models."

models-deploy-vllm: ## Deploy vLLM (requires GPU node) + LiteLLM gateway
	kubectl apply -f k8s/base/models/ollama/deployment.yaml  # namespace
	kubectl apply -f k8s/base/models/vllm/deployment.yaml
	kubectl apply -f k8s/base/models/litellm/deployment.yaml

models-destroy: ## Remove all model infrastructure
	kubectl delete -f k8s/base/models/litellm/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/models/vllm/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/models/ollama/deployment.yaml --ignore-not-found

model-pull: ## Pull a model into Ollama (MODEL=qwen2.5-coder:32b)
	@echo "==> Pulling $(MODEL) into Ollama..."
	kubectl -n ai-models exec deploy/ollama -- ollama pull $(MODEL)
	@echo "==> Done. Loaded models:"
	kubectl -n ai-models exec deploy/ollama -- ollama list

model-list: ## List models loaded in Ollama
	kubectl -n ai-models exec deploy/ollama -- ollama list

models-status: ## Check model infrastructure pods
	@echo "==> ai-models namespace"
	kubectl -n ai-models get pods -o wide
	@echo "==> Services"
	kubectl -n ai-models get svc
	@echo "==> PVCs"
	kubectl -n ai-models get pvc

models-logs: ## Tail Ollama logs
	kubectl -n ai-models logs deploy/ollama --tail=50 -f

litellm-logs: ## Tail LiteLLM proxy logs
	kubectl -n ai-models logs deploy/litellm --tail=50 -f

litellm-test: ## Smoke-test the LiteLLM gateway
	@echo "==> Testing LiteLLM /v1/models endpoint..."
	kubectl -n ai-models exec deploy/litellm -- \
		curl -s http://localhost:4000/v1/models \
		-H "Authorization: Bearer sk-internal-agents-local" | head -c 500
	@echo ""

# ── Observability ──────────────────────────────────────────────

obs-deploy: ## Deploy observability stack (OTel, Prometheus, Alertmanager, Langfuse, Loki, Tempo, Grafana)
	@echo "==> Deploying observability namespace..."
	kubectl apply -f k8s/base/observability/namespace.yaml
	@echo "==> Deploying Loki + Tempo..."
	kubectl apply -f k8s/base/observability/loki-tempo.yaml
	@echo "==> Deploying Prometheus..."
	kubectl apply -f k8s/base/observability/prometheus/deployment.yaml
	@echo "==> Deploying Alertmanager..."
	kubectl apply -f k8s/base/observability/alertmanager/deployment.yaml
	@echo "==> Deploying Langfuse..."
	kubectl apply -f k8s/base/observability/langfuse/deployment.yaml
	@echo "==> Deploying OTel Collector..."
	kubectl apply -f k8s/base/observability/otel-collector/deployment.yaml
	@echo "==> Deploying Grafana..."
	kubectl apply -f k8s/base/observability/grafana/dashboards-configmap.yaml
	kubectl apply -f k8s/base/observability/grafana/deployment.yaml
	@echo "==> Observability stack deployed."
	@echo "    Grafana:      kubectl -n ai-observability port-forward svc/grafana 3000:3000"
	@echo "    Langfuse:     kubectl -n ai-observability port-forward svc/langfuse 3001:3000"
	@echo "    Prometheus:   kubectl -n ai-observability port-forward svc/prometheus 9090:9090"
	@echo "    Alertmanager: kubectl -n ai-observability port-forward svc/alertmanager 9093:9093"

obs-destroy: ## Remove observability stack
	kubectl delete -f k8s/base/observability/grafana/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/grafana/dashboards-configmap.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/otel-collector/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/langfuse/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/alertmanager/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/prometheus/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/loki-tempo.yaml --ignore-not-found
	kubectl delete -f k8s/base/observability/namespace.yaml --ignore-not-found

obs-status: ## Check observability stack pods
	@echo "==> ai-observability namespace"
	kubectl -n ai-observability get pods -o wide
	@echo "==> Services"
	kubectl -n ai-observability get svc
	@echo "==> PVCs"
	kubectl -n ai-observability get pvc

obs-port-forward: ## Port-forward Grafana (3000), Langfuse (3001), Prometheus (9090)
	@echo "==> Starting port-forwards (Ctrl+C to stop)..."
	@echo "    Grafana:    http://localhost:3000  (admin / agent-admin)"
	@echo "    Langfuse:   http://localhost:3001"
	@echo "    Prometheus: http://localhost:9090"
	kubectl -n ai-observability port-forward svc/grafana 3000:3000 &
	kubectl -n ai-observability port-forward svc/langfuse 3001:3000 &
	kubectl -n ai-observability port-forward svc/prometheus 9090:9090 &
	@wait

# ── Self-Healing Pipeline ──────────────────────────────────────

healing-deploy: ## Deploy self-healing pipeline (telemetry watcher CronJob + alert receiver)
	@echo "==> Deploying self-healing components..."
	kubectl apply -f k8s/base/self-healing/deployment.yaml
	@echo "==> Self-healing pipeline deployed."
	@echo "    CronJob:        telemetry-watcher (every 15 min)"
	@echo "    Alert Receiver: alert-receiver.ai-agents.svc.cluster.local:8082"

healing-destroy: ## Remove self-healing pipeline
	kubectl delete -f k8s/base/self-healing/deployment.yaml --ignore-not-found

healing-status: ## Check self-healing pods and jobs
	@echo "==> Self-healing CronJob"
	kubectl -n ai-agents get cronjobs telemetry-watcher 2>/dev/null || echo "(not deployed)"
	@echo "==> Alert Receiver"
	kubectl -n ai-agents get deploy alert-receiver 2>/dev/null || echo "(not deployed)"
	@echo "==> Recent telemetry-watcher jobs"
	kubectl -n ai-agents get jobs -l app.kubernetes.io/name=telemetry-watcher \
		--sort-by='.metadata.creationTimestamp' 2>/dev/null | tail -5 || true
	@echo "==> Alert Receiver pods"
	kubectl -n ai-agents get pods -l app.kubernetes.io/name=alert-receiver 2>/dev/null || true

healing-logs: ## Tail self-healing component logs
	@echo "==> Alert Receiver logs:"
	kubectl -n ai-agents logs deploy/alert-receiver --tail=30 2>/dev/null || echo "(not running)"
	@echo ""
	@echo "==> Latest telemetry-watcher job logs:"
	@JOB=$$(kubectl -n ai-agents get jobs -l app.kubernetes.io/name=telemetry-watcher \
		--sort-by='.metadata.creationTimestamp' -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null); \
	if [ -n "$$JOB" ]; then kubectl -n ai-agents logs job/$$JOB --tail=30; \
	else echo "(no jobs found)"; fi

healing-test: ## Manually trigger the telemetry watcher (creates a one-off Job)
	kubectl -n ai-agents create job telemetry-watcher-manual-$$(date +%s) \
		--from=cronjob/telemetry-watcher
	@echo "==> Manual job created. Check with: make healing-logs"

# ── Full Stack (models + agents + observability + self-healing) ──

deploy-full: obs-deploy models-deploy deploy healing-deploy ## Deploy everything
	@echo "==> Full stack deployed."
	@echo "    Run 'make model-pull MODEL=qwen2.5-coder:32b' to load a model."
	@echo "    Run 'make obs-port-forward' to access dashboards."

destroy-full: healing-destroy destroy models-destroy obs-destroy ## Tear down everything

# ── Verify ─────────────────────────────────────────────────────

verify: ## Check agent pods and jobs in the cluster
	@echo "==> ai-agents namespace"
	kubectl get ns ai-agents
	@echo "==> Agent pods"
	kubectl -n ai-agents get pods
	@echo "==> CronJobs"
	kubectl -n ai-agents get cronjobs
	@echo "==> Jobs (recent)"
	kubectl -n ai-agents get jobs --sort-by='.metadata.creationTimestamp' | tail -10
	@echo "==> Agent services"
	kubectl -n ai-agents get svc
	@echo ""
	@echo "==> ai-models namespace"
	kubectl -n ai-models get pods
	kubectl -n ai-models get svc

# ── Terraform (Cloud Deployments) ─────────────────────────────
# Usage:
#   make tf-init   CLOUD=aws-native       — initialise AWS-native Terraform
#   make tf-plan   CLOUD=azure-native     — plan Azure-native changes
#   make tf-apply  CLOUD=gcp-native       — apply GCP-native infra
#   make tf-plan   CLOUD=cloud-agnostic   — plan cloud-agnostic K8s cluster
#
CLOUD ?= aws-native
TF_DIR = infra/terraform/$(CLOUD)
TF_VARS ?=

tf-init: ## Initialise Terraform for CLOUD (aws-native | azure-native | gcp-native | cloud-agnostic)
	cd $(TF_DIR) && terraform init

tf-plan: ## Plan Terraform changes for CLOUD
	cd $(TF_DIR) && terraform plan $(TF_VARS)

tf-apply: ## Apply Terraform changes for CLOUD
	cd $(TF_DIR) && terraform apply $(TF_VARS)

tf-destroy: ## Destroy Terraform-managed infra for CLOUD
	cd $(TF_DIR) && terraform destroy $(TF_VARS)

tf-output: ## Show Terraform outputs for CLOUD
	cd $(TF_DIR) && terraform output

# ── Cloud-Agnostic K8s Deploy ──────────────────────────────────
# After provisioning the cluster with Terraform, apply the K8s overlay:
#   make deploy-eks  / deploy-aks / deploy-gke

deploy-eks: ## Deploy agents to EKS (cloud-agnostic K8s)
	kubectl apply -k k8s/overlays/eks

deploy-aks: ## Deploy agents to AKS (cloud-agnostic K8s)
	kubectl apply -k k8s/overlays/aks

deploy-gke: ## Deploy agents to GKE (cloud-agnostic K8s)
	kubectl apply -k k8s/overlays/gke

# ── Install Dependencies ───────────────────────────────────────

install: ## Install core dependencies
	pip install -r requirements.txt

install-aws: ## Install AWS-native dependencies
	pip install -r requirements-aws.txt

install-azure: ## Install Azure-native dependencies
	pip install -r requirements-azure.txt

install-gcp: ## Install GCP-native dependencies
	pip install -r requirements-gcp.txt
