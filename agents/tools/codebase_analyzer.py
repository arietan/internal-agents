"""Build a compact summary of a repository's structure and key files."""

import logging
from pathlib import Path

log = logging.getLogger("tools.codebase_analyzer")

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox"}

_KEY_FILES = [
    "README.md", "CONTRIBUTING.md", "CODEOWNERS", ".cursorrules",
    "pyproject.toml", "package.json", "Makefile", "Dockerfile",
    "go.mod", "Cargo.toml",
]


def analyze(repo_dir: str, max_tree_lines: int = 200, max_file_chars: int = 2000) -> str:
    """Return a markdown summary of *repo_dir* suitable for an LLM prompt."""
    repo = Path(repo_dir)
    tree_lines: list[str] = []

    for p in sorted(repo.rglob("*")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        rel = p.relative_to(repo)
        if p.is_file() and len(rel.parts) <= 4:
            tree_lines.append(str(rel))

    tree = "\n".join(tree_lines[:max_tree_lines])

    key_files: dict[str, str] = {}
    for name in _KEY_FILES:
        fp = repo / name
        if fp.exists():
            key_files[name] = fp.read_text(errors="replace")[:max_file_chars]

    summary = f"## Repository structure\n```\n{tree}\n```\n\n"
    for fname, content in key_files.items():
        summary += f"## {fname}\n```\n{content}\n```\n\n"

    log.info("Codebase analysis: %d tree lines, %d key files", len(tree_lines), len(key_files))
    return summary
