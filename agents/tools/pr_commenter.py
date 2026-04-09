"""Post review comments and assign reviewers on GitHub PRs."""

import logging
import os
import subprocess

log = logging.getLogger("tools.pr_commenter")


def _gh(token: str, *args: str) -> str:
    env = {**os.environ, "GH_TOKEN": token}
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode != 0:
        log.error("gh failed: %s", result.stderr.strip())
        raise RuntimeError(f"gh failed: {' '.join(args)}")
    return result.stdout.strip()


def post_comment(token: str, repo: str, pr_number: int, body: str) -> None:
    """Post a comment on a PR."""
    _gh(token, "pr", "comment", str(pr_number), "--repo", repo, "--body", body)
    log.info("Posted review comment on %s#%d", repo, pr_number)


def assign_reviewer(token: str, repo: str, pr_number: int, reviewer: str) -> None:
    """Request a review from *reviewer* on a PR."""
    _gh(token, "pr", "edit", str(pr_number), "--repo", repo, "--add-reviewer", reviewer)
    log.info("Assigned @%s as reviewer on %s#%d", reviewer, repo, pr_number)
