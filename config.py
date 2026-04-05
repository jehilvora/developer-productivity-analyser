import os

from dotenv import load_dotenv

load_dotenv()

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_PAT = os.getenv("GITHUB_PAT", "",)
# Set GITHUB_REPO to "owner/repo", e.g. "torvalds/linux"
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

# How many days back to look (default 90)
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "90"))

# ── Scoring ───────────────────────────────────────────────────────────────────
TOP_N_USERS = int(os.getenv("TOP_N_USERS", "10"))

SCORE_WEIGHTS = {
    "prs": 2.0,
    "issues_closed": 3.0,
    "reviews_given": 1.5,
}

# Logins to always exclude (bots)
BOT_LOGINS = {"dependabot", "github-actions", "copilot-pull-request-reviewer"}
BOT_SUBSTRING = ["[bot]", "copilot", "-app"]

# ── LLM ───────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_MODEL = "gemini-2.5-flash-lite"

MAX_PRS_FOR_LLM = 20
MAX_REVIEWS_FOR_LLM = 15

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = "data"
RAW_DIR = f"{DATA_DIR}/raw"
PRS_FILE = f"{RAW_DIR}/prs.json"
ISSUES_FILE = f"{RAW_DIR}/issues.json"
ACTIVE_USERS_FILE = f"{DATA_DIR}/active_users.json"
IMPACT_PROFILES_FILE = f"{DATA_DIR}/impact_profiles.json"
