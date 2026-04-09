"""Fetch GitHub issues labelled for the agent."""

import json
import logging
import os
import subprocess

log = logging.getLogger("tools.github_issues")


def _gh(token: str, *args: str) -> str:
    env = {**os.environ, "GH_TOKEN": token}
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh command failed: {' '.join(args)}")
    return result.stdout.strip()


def fetch_issues(
    token: str,
    repo: str,
    label: str = "ai-agent",
    limit: int = 5,
) -> list[dict]:
    """Return open issues matching *label* from *repo*."""
    raw = _gh(
        token,
        "issue", "list",
        "--repo", repo,
        "--label", label,
        "--state", "open",
        "--json", "number,title,body,labels",
        "--limit", str(limit),
    )
    issues = json.loads(raw) if raw else []
    log.info("Found %d issues labelled '%s' in %s", len(issues), label, repo)
    return issues
