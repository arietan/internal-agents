## What Changed

<!-- Describe what this PR does and why. Link to an issue if applicable: Closes #123 -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Infrastructure change (Terraform, K8s manifests, Dockerfile)
- [ ] Documentation update

## How It Was Tested

<!-- Describe how you tested the change. Include deployment option if relevant (local, EKS, serverless, etc.) -->

- [ ] `make lint` passes
- [ ] `make test` passes (if tests exist for the changed area)
- [ ] Tested locally with `DRY_RUN=true`
- [ ] Deployed to local K8s with `make deploy-full && make verify`
- [ ] Terraform validated (`terraform validate`)

## Checklist

- [ ] My code follows the conventions in [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] I have added/updated `.env.example` if new environment variables were introduced
- [ ] I have updated documentation if behaviour changed
- [ ] No secrets, tokens, or credentials are in this diff
- [ ] Commit messages use [conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, etc.)
