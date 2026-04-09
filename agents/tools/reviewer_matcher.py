"""Score and recommend the best PR reviewer from team config."""

import logging

log = logging.getLogger("tools.reviewer_matcher")


def recommend_approver(
    changed_files: list[str],
    team_config: dict,
    pr_author: str,
) -> dict:
    """Score each reviewer and return the best candidate.

    Returns:
        dict with keys: recommended, score, reason, all_scores.
    """
    reviewers = team_config.get("reviewers", [])
    if not reviewers:
        return {"recommended": None, "reason": "No reviewers configured"}

    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for reviewer in reviewers:
        name = reviewer["github"]
        if name == pr_author:
            continue

        scores[name] = 0
        reasons[name] = []

        for pattern in reviewer.get("owns", []):
            matching = [f for f in changed_files if _matches(f, pattern)]
            if matching:
                scores[name] += len(matching) * 10
                reasons[name].append(f"owns {pattern} ({len(matching)} files)")

        for ext in _extensions(changed_files):
            if ext in reviewer.get("expertise", []):
                scores[name] += 5
                reasons[name].append(f"expertise in {ext}")

        if reviewer.get("lead"):
            scores[name] += 2
            reasons[name].append("team lead")

        workload = reviewer.get("current_prs", 0)
        if workload > 3:
            scores[name] -= 3
            reasons[name].append(f"heavy load ({workload} open PRs)")

    if not scores:
        return {"recommended": None, "reason": "No eligible reviewers (author excluded)"}

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return {
        "recommended": best,
        "score": scores[best],
        "reason": "; ".join(reasons[best]),
        "all_scores": {
            k: {"score": v, "reasons": reasons[k]}
            for k, v in sorted(scores.items(), key=lambda x: -x[1])
        },
    }


def _matches(filepath: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return filepath.startswith(pattern[:-3])
    if pattern.startswith("*."):
        return filepath.endswith(pattern[1:])
    return filepath == pattern


def _extensions(files: list[str]) -> set[str]:
    exts: set[str] = set()
    for f in files:
        if "." in f:
            exts.add("." + f.rsplit(".", 1)[-1])
    return exts
