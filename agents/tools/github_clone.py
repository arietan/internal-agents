"""Clone a GitHub repository."""

import logging
import os
import subprocess

log = logging.getLogger("tools.github_clone")


def clone(token: str, repo: str, dest: str, branch: str = "main", depth: int = 50) -> str:
    """Clone *repo* into *dest* using the given PAT.

    Returns:
        The absolute path to the cloned working tree.
    """
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    cmd = ["git", "clone", "--depth", str(depth), "--branch", branch, url, dest]
    log.info("Cloning %s (depth=%d) → %s", repo, depth, dest)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return os.path.abspath(dest)
