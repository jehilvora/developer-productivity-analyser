"""
Stage 1 — Download GitHub data for the past LOOKBACK_DAYS days.

Outputs:
  data/raw/prs.json    — PRs with embedded reviews
  data/raw/issues.json — closed issues (non-PR)

Usage:
  GITHUB_REPO=owner/repo python data_downloader.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import config

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2  # seconds; doubles each attempt

GRAPHQL_URL = "https://api.github.com/graphql"

HEADERS = {
    "Authorization": f"Bearer {config.GITHUB_PAT}",
    "Content-Type": "application/json",
}

PR_QUERY = """
query GetPRs($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(
      first: 100
      after: $cursor
      states: [MERGED]
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        state
        merged
        additions
        deletions
        changedFiles
        createdAt
        author { login }
        reviews(first: 20) {
          nodes {
            state
            body
            submittedAt
            author { login }
          }
        }
      }
    }
  }
}
"""

ISSUES_QUERY = """
query GetIssues($owner: String!, $repo: String!, $cursor: String, $since: DateTime!) {
  repository(owner: $owner, name: $repo) {
    issues(
      first: 100
      after: $cursor
      states: [CLOSED]
      filterBy: {since: $since}
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        closedAt
        stateReason
        author { login }
        timelineItems(last: 1, itemTypes: [CLOSED_EVENT]) {
          nodes {
            ... on ClosedEvent {
              actor { login }
            }
          }
        }
      }
    }
  }
}
"""


def run_query(query: str, variables: dict) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                GRAPHQL_URL,
                headers=HEADERS,
                json={"query": query, "variables": variables},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            return data["data"]
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            if attempt == MAX_RETRIES:
                raise
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            print(f"\n  [retry {attempt}/{MAX_RETRIES}] {e.__class__.__name__} — waiting {delay}s...", end=" ")
            time.sleep(delay)


def fetch_prs(owner: str, repo: str, cutoff: datetime) -> list[dict]:
    prs = []
    cursor = None
    page = 0

    while True:
        page += 1
        print(f"  Fetching PRs page {page}...", end=" ", flush=True)
        data = run_query(PR_QUERY, {"owner": owner, "repo": repo, "cursor": cursor})
        page_data = data["repository"]["pullRequests"]
        nodes = page_data["nodes"]
        print(f"{len(nodes)} records")

        stop = False
        for pr in nodes:
            created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
            if created < cutoff:
                stop = True
                break
            # Clean up nested nulls from bots / deleted accounts
            if pr.get("author") is None:
                pr["author"] = {"login": "ghost"}
            for review in pr["reviews"]["nodes"]:
                if review.get("author") is None:
                    review["author"] = {"login": "ghost"}
            prs.append(pr)

        if stop or not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]
        time.sleep(5)

    return prs


def fetch_issues(owner: str, repo: str, cutoff: datetime) -> list[dict]:
    issues = []
    cursor = None
    page = 0
    since_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    while True:
        page += 1
        print(f"  Fetching issues page {page}...", end=" ", flush=True)
        data = run_query(
            ISSUES_QUERY,
            {"owner": owner, "repo": repo, "cursor": cursor, "since": since_iso},
        )
        page_data = data["repository"]["issues"]
        nodes = page_data["nodes"]
        print(f"{len(nodes)} records")

        for issue in nodes:
            if issue.get("author") is None:
                issue["author"] = {"login": "ghost"}
            # Resolve closer from ClosedEvent timeline; fall back to issue author
            timeline_nodes = issue.get("timelineItems", {}).get("nodes", [])
            closer_login = None
            if timeline_nodes:
                actor = timeline_nodes[0].get("actor")
                if actor:
                    closer_login = actor["login"]
            issue["closedBy"] = {"login": closer_login or issue["author"]["login"]}
            issues.append(issue)

        if not page_data["pageInfo"]["hasNextPage"]:
            break
        cursor = page_data["pageInfo"]["endCursor"]

    return issues


def main():
    repo = config.GITHUB_REPO
    if not repo or "/" not in repo:
        print("ERROR: Set GITHUB_REPO=owner/repo before running.")
        sys.exit(1)

    owner, repo_name = repo.split("/", 1)
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)
    print(f"Repo        : {repo}")
    print(f"Lookback    : {config.LOOKBACK_DAYS} days (since {cutoff.date()})")

    os.makedirs(config.RAW_DIR, exist_ok=True)

    print("\n[1/2] Fetching pull requests...")
    prs = fetch_prs(owner, repo_name, cutoff)
    print(f"  Total PRs fetched: {len(prs)}")

    print("\n[2/2] Fetching closed issues...")
    issues = fetch_issues(owner, repo_name, cutoff)
    print(f"  Total issues fetched: {len(issues)}")

    meta = {
        "repo": repo,
        "lookback_days": config.LOOKBACK_DAYS,
        "cutoff_date": cutoff.isoformat(),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(config.PRS_FILE, "w") as f:
        json.dump({"meta": meta, "prs": prs}, f, indent=2)
    print(f"\nSaved {len(prs)} PRs → {config.PRS_FILE}")

    with open(config.ISSUES_FILE, "w") as f:
        json.dump({"meta": meta, "issues": issues}, f, indent=2)
    print(f"Saved {len(issues)} issues → {config.ISSUES_FILE}")


if __name__ == "__main__":
    main()
