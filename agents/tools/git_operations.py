"""Apply file changes to a repo and create a PR."""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger("tools.git_operations")


def _git(cwd: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", cwd, *args], capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        log.error("git failed: %s", result.stderr.strip())
        raise RuntimeError(f"git command failed: {' '.join(args)}")
    return result.stdout.strip()


def _gh(token: str, *args: str) -> str:
    env = {**os.environ, "GH_TOKEN": token}
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh command failed: {' '.join(args)}")
    return result.stdout.strip()


def apply_changes(repo_dir: str, files: list[dict]) -> int:
    """Write file changes to the working tree.

    Each entry in *files* has keys: path, action (create|modify|delete), content.
    Returns the number of files modified.
    """
    count = 0
    for f in files:
        target = Path(repo_dir) / f["path"]
        action = f.get("action", "create")

        if action == "delete":
            if target.exists():
                target.unlink()
                log.info("Deleted %s", f["path"])
                count += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"])
        log.info("%s %s", "Created" if action == "create" else "Modified", f["path"])
        count += 1
    return count


def create_pr(
    token: str,
    repo: str,
    repo_dir: str,
    branch: str,
    base: str,
    commit_message: str,
    pr_title: str,
    pr_body: str,
    issue_ref: Optional[str] = None,
) -> str:
    """Commit, push, and open a pull request. Returns the PR URL."""
    _git(repo_dir, "checkout", "-b", branch)
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", commit_message)
    _git(repo_dir, "push", "origin", branch)

    body = pr_body
    if issue_ref:
        body += f"\n\nCloses {issue_ref}"
    body += "\n\n---\n*Raised by internal coding agent. Human review required before merge.*"

    pr_url = _gh(
        token,
        "pr", "create",
        "--repo", repo,
        "--base", base,
        "--head", branch,
        "--title", pr_title,
        "--body", body,
        "--label", "ai-generated",
    )
    log.info("PR created: %s", pr_url)
    return pr_url


def parse_plan(raw: str) -> dict:
    """Parse the LLM JSON plan, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines[1:] if line.strip() != "```"]
        text = "\n".join(lines)
    return json.loads(text)
