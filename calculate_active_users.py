"""
Stage 2 — Score contributors and select the top-N most active users.

Reads:
  data/raw/prs.json
  data/raw/issues.json

Outputs:
  data/active_users.json

Usage:
  python calculate_active_users.py
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

import config


def is_bot(login: str) -> bool:
    login_lower = login.lower()
    return login_lower in config.BOT_LOGINS or any([bot_substring in login_lower for bot_substring in config.BOT_SUBSTRING])


def load_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {path} not found. Run data_downloader.py first.")
        sys.exit(1)


def main():
    prs_data = load_json(config.PRS_FILE)
    issues_data = load_json(config.ISSUES_FILE)

    prs = prs_data["prs"]
    issues = issues_data["issues"]
    repo = prs_data["meta"]["repo"]

    counts: dict[str, dict] = defaultdict(
        lambda: {"prs": 0, "issues_closed": 0, "reviews_given": 0}
    )

    # PRs authored (query already filters to MERGED state)
    for pr in prs:
        author = pr["author"]["login"]
        if is_bot(author):
            continue
        counts[author]["prs"] += 1

        # Reviews given (exclude self-reviews)
        for review in pr["reviews"]["nodes"]:
            reviewer = review["author"]["login"]
            if is_bot(reviewer) or reviewer == author:
                continue
            counts[reviewer]["reviews_given"] += 1

    # Issues closed as COMPLETED (excludes won't fix, duplicate, stale)
    for issue in issues:
        if issue.get("stateReason") != "COMPLETED":
            continue
        closer = issue["closedBy"]["login"]
        if is_bot(closer):
            continue
        counts[closer]["issues_closed"] += 1

    # Score and rank
    w = config.SCORE_WEIGHTS
    scored = []
    for username, stats in counts.items():
        score = (
            w["prs"] * stats["prs"]
            + w["issues_closed"] * stats["issues_closed"]
            + w["reviews_given"] * stats["reviews_given"]
        )
        scored.append(
            {
                "username": username,
                "score": round(score, 2),
                "prs": stats["prs"],
                "issues_closed": stats["issues_closed"],
                "reviews_given": stats["reviews_given"],
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    top_users = scored[: config.TOP_N_USERS]

    output = {
        "meta": {
            "repo": repo,
            "top_n": config.TOP_N_USERS,
            "lookback_days": prs_data["meta"]["lookback_days"],
            "score_weights": config.SCORE_WEIGHTS,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "users": top_users,
    }

    with open(config.ACTIVE_USERS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Repo: {repo}")
    print(f"Total unique contributors (non-bot): {len(scored)}")
    print(f"Top {len(top_users)} by score:\n")
    print(f"  {'#':<4} {'Username':<25} {'Score':>7}  {'PRs':>5}  {'Issues':>7}  {'Reviews':>8}")
    print(f"  {'-'*4} {'-'*25} {'-'*7}  {'-'*5}  {'-'*7}  {'-'*8}")
    for i, u in enumerate(top_users, 1):
        print(
            f"  {i:<4} {u['username']:<25} {u['score']:>7.1f}  "
            f"{u['prs']:>5}  {u['issues_closed']:>7}  {u['reviews_given']:>8}"
        )

    print(f"\nSaved → {config.ACTIVE_USERS_FILE}")


if __name__ == "__main__":
    main()
