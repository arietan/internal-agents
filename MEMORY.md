# Project Memory

## Current State
Open-source preparation complete. GitHub Pages promotion site built. Ready for `git init` and first public push.

## Recent Changes
- 2026-04-09: GitHub Pages promotion site:
  - Created `site/index.html` -- single-file landing page (Tailwind CDN, CSS-only animations, no build step)
  - Sections: hero (101s stat), three agents, deploy anywhere, compliance/trust, quick start, observability, CTA footer
  - Created `.github/workflows/deploy-pages.yml` for automatic deployment on push to `site/`
  - Created reusable `~/.cursor/skills/promote-project/SKILL.md` for promoting any future project
- 2026-04-09: Open-source preparation pass:
  - Scrubbed `your-org`/`your-repo` placeholders → `<YOUR_ORG>`/`<YOUR_REPO>` angle-bracket convention across README, Makefile, SECURITY.md, configmap, .env.example
  - Added disclaimer to `docs/self-healing-pipeline-demo.md` noting demo repo references
  - Expanded `.gitignore` with Python, Terraform, IDE, OS, and project-specific entries
  - Created `CHANGELOG.md` (Keep a Changelog format)
  - Created `.github/` directory: issue templates (bug_report, feature_request), PR template, CODEOWNERS
  - Created `.github/workflows/ci.yml` (lint + compile, terraform validate matrix, docker build matrix)
  - Created `NOTICE` file (Apache 2.0 attribution)
  - Removed `CODE_OF_CONDUCT.md` references from README.md, CONTRIBUTING.md, docs/architecture.md (skipped per user request -- gave trouble in prior session)
  - Added `NOTICE` to repo layout in docs/architecture.md

## Architecture Decisions
- Apache 2.0 license chosen for permissive open-source use
- Angle-bracket placeholders (`<YOUR_ORG>`) used instead of example org names to make them grep-able and unambiguous
- CODE_OF_CONDUCT.md intentionally omitted (gave trouble in prior session; can be added later)
- CI workflow uses matrix strategy for terraform validate (4 modules) and docker build (6 targets) for parallelism

## Known Issues & TODOs
- `.env` contains a real GitHub token (`gho_NYVoCPn6...`) -- MUST be rotated before publishing
- No git repo initialized yet; `.env` is in `.gitignore` so it won't be tracked on init
- `sk-internal-agents-local` appears as a hardcoded dev default in several agent files and K8s manifests -- acceptable for local dev but should be documented as a non-secret convention
- `docs/self-healing-pipeline-demo.md` still references `arietan/demo-fastapi-app` with real PR URLs (disclaimer added)
- No test suite exists yet (listed as top contribution area in CONTRIBUTING.md)

## Key Files & Patterns
- Community health: `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, `SECURITY.md`, `ROADMAP.md`, `CHANGELOG.md`
- GitHub: `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS`, `.github/workflows/ci.yml`
- Promotion site: `site/index.html` (GitHub Pages), `.github/workflows/deploy-pages.yml`
- Placeholders: search for `<YOUR_ORG>` to find all spots needing org-specific values

## Environment & Setup
- Python 3.12+, Docker, kubectl, gh CLI, make, Ollama
- Terraform >= 1.5 for cloud deployments
- `.env.example` is the canonical env var reference; copy to `.env` and fill in values
