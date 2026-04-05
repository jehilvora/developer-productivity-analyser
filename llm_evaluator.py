"""
Stage 3 — LLM-as-a-Judge: produce an ImpactProfile for each top contributor.

Reads:
  data/active_users.json
  data/raw/prs.json
  data/raw/issues.json

Outputs:
  data/impact_profiles.json

Usage:
  GEMINI_API_KEY=... python llm_evaluator.py
"""

import json
import sys
import time
from datetime import datetime, timezone

import instructor
from google import genai
from pydantic import BaseModel, Field

import config

# ── Pydantic model ─────────────────────────────────────────────────────────────

class ImpactProfile(BaseModel):
    technical_complexity: int = Field(
        ge=1, le=10, description="1–10: depth and difficulty of technical work"
    )
    mentorship_signal: int = Field(
        ge=1, le=10, description="1–10: quality and depth of code reviews given"
    )
    is_refactor_heavy: bool = Field(
        description="True if the developer primarily simplified or restructured existing code"
    )
    impact_persona: str = Field(
        description='Short archetype label, e.g. "The Closer", "The Optimizer", "The Architect"'
    )
    summary_justification: str = Field(
        description=(
            "5 lines max. Justify the scores with references to specific PRs or review activity. "
            "Be concrete, not generic."
        )
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {path} not found. Run prior pipeline stages first.")
        sys.exit(1)


def build_user_context(username: str, user_stats: dict, prs: list[dict]) -> str:
    """Build a concise text summary of a user's activity for the LLM."""
    authored_prs = [p for p in prs if p["author"]["login"] == username]
    reviews_given = [
        review
        for p in prs
        for review in p["reviews"]["nodes"]
        if review["author"]["login"] == username and review["author"]["login"] != p["author"]["login"]
    ]

    lines = [
        f"Developer: @{username}",
        f"Activity window: last {config.LOOKBACK_DAYS} days",
        f"Stats: {user_stats['prs']} PRs authored | "
        f"{user_stats['issues_closed']} issues closed | "
        f"{user_stats['reviews_given']} reviews given | "
        f"Weighted score: {user_stats['score']}",
        "",
    ]

    # PRs authored
    sample_prs = authored_prs[: config.MAX_PRS_FOR_LLM]
    if sample_prs:
        lines.append(f"=== PRs Authored ({len(authored_prs)} total, showing {len(sample_prs)}) ===")
        for pr in sample_prs:
            body_preview = (pr.get("body") or "").strip()[:300].replace("\n", " ")
            lines.append(
                f"- [{pr['state']}] #{pr['number']} \"{pr['title']}\" "
                f"(+{pr['additions']}/-{pr['deletions']}, {pr['changedFiles']} files changed)"
            )
            if body_preview:
                lines.append(f"  Description: {body_preview}")
        lines.append("")

    # Reviews given
    sample_reviews = reviews_given[: config.MAX_REVIEWS_FOR_LLM]
    if sample_reviews:
        lines.append(f"=== Reviews Given ({len(reviews_given)} total, showing {len(sample_reviews)}) ===")
        for review in sample_reviews:
            body_preview = (review.get("body") or "").strip()[:200].replace("\n", " ")
            lines.append(f"- [{review['state']}] {body_preview or '(no comment body)'}")
        lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not config.GEMINI_API_KEY:
        print("ERROR: Set GEMINI_API_KEY before running.")
        sys.exit(1)

    active_data = load_json(config.ACTIVE_USERS_FILE)
    prs_data = load_json(config.PRS_FILE)
    prs = prs_data["prs"]

    client = instructor.from_genai(
        genai.Client(api_key=config.GEMINI_API_KEY),
        model=config.LLM_MODEL,
    )

    profiles: dict[str, dict] = {}
    users = active_data["users"]

    print(f"Evaluating {len(users)} contributors with {config.LLM_MODEL}...\n")

    for i, user in enumerate(users, 1):
        username = user["username"]
        print(f"[{i}/{len(users)}] @{username}...", end=" ", flush=True)

        context = build_user_context(username, user, prs)

        profile: ImpactProfile = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are an engineering impact analyst. "
                        "Based on the GitHub activity below, evaluate this developer and return a structured ImpactProfile.\n\n"
                        "Guidelines:\n"
                        "- technical_complexity: judge by PR size, breadth of files changed, and sophistication of changes\n"
                        "- mentorship_signal: judge by review depth, constructiveness, and frequency\n"
                        "- is_refactor_heavy: True only if most PRs are deletions/restructuring rather than new features\n"
                        "- impact_persona: a vivid 2-3 word archetype\n"
                        "- summary_justification: ≤5 lines, reference specific PR numbers or review patterns\n\n"
                        f"{context}"
                    ),
                }
            ],
            response_model=ImpactProfile,
        )

        profiles[username] = profile.model_dump()
        print(f"persona={profile.impact_persona!r}  complexity={profile.technical_complexity}  mentorship={profile.mentorship_signal}")
        time.sleep(20)  # Rate limit pause

    output = {
        "meta": {
            "model": config.LLM_MODEL,
            "repo": active_data["meta"]["repo"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "profiles": profiles,
    }

    with open(config.IMPACT_PROFILES_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(profiles)} profiles → {config.IMPACT_PROFILES_FILE}")


if __name__ == "__main__":
    main()
