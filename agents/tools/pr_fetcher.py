"""Fetch PR metadata and diff from GitHub."""

import json
import logging
import os
import subprocess

log = logging.getLogger("tools.pr_fetcher")


def _gh(token: str, *args: str) -> str:
    env = {**os.environ, "GH_TOKEN": token}
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh failed: {' '.join(args)}")
    return result.stdout.strip()


def fetch_metadata(token: str, repo: str, pr_number: int) -> dict:
    """Return PR metadata (title, body, author, files, stats, refs)."""
    raw = _gh(
        token,
        "pr", "view", str(pr_number),
        "--repo", repo,
        "--json", "title,body,author,labels,files,additions,deletions,baseRefName,headRefName",
    )
    return json.loads(raw)


def fetch_diff(token: str, repo: str, pr_number: int) -> str:
    """Return the unified diff for a PR."""
    return _gh(token, "pr", "diff", str(pr_number), "--repo", repo)


def fetch_changed_files(token: str, repo: str, pr_number: int) -> list[str]:
    """Return a list of file paths changed in a PR."""
    raw = _gh(
        token,
        "pr", "view", str(pr_number),
        "--repo", repo,
        "--json", "files",
    )
    data = json.loads(raw)
    return [f["path"] for f in data.get("files", [])]
