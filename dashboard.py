"""
Stage 4 — Interactive Engineering Impact Dashboard.

Usage:
  streamlit run dashboard.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Engineering Impact Dashboard",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
/* Global */
[data-testid="stAppViewContainer"] { background: #0d1117; color: #e6edf3; }
[data-testid="stHeader"] { background: transparent; }

/* Metric cards */
div[data-testid="metric-container"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px 20px;
}
div[data-testid="metric-container"] label { color: #8b949e; font-size: 13px; }
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #58a6ff; font-size: 28px; font-weight: 700;
}

/* Section headers */
h2 { color: #e6edf3; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
h3 { color: #cdd9e5; }

/* Persona badge */
.persona-badge {
    display: inline-block;
    background: linear-gradient(135deg, #1f6feb, #388bfd);
    color: white;
    padding: 6px 16px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 15px;
    margin-bottom: 12px;
}

/* Stat pill */
.stat-pill {
    display: inline-block;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 14px;
    margin: 4px;
    font-size: 13px;
}
.stat-number { font-weight: 700; color: #58a6ff; font-size: 18px; }

/* Refactor badge */
.refactor-badge {
    display: inline-block;
    background: #1a3a2a;
    border: 1px solid #2ea043;
    color: #3fb950;
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
}

/* Justification card */
.justification-box {
    background: #161b22;
    border-left: 3px solid #388bfd;
    border-radius: 0 8px 8px 0;
    padding: 14px 18px;
    margin-top: 10px;
    font-size: 14px;
    line-height: 1.6;
    color: #cdd9e5;
}

/* Developer card wrapper */
.dev-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px;
}

/* Score bar */
.score-rank { font-size: 22px; font-weight: 800; color: #f0883e; }
</style>
""",
    unsafe_allow_html=True,
)


# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_data() -> tuple[dict, dict]:
    missing = []
    for path in (config.ACTIVE_USERS_FILE, config.IMPACT_PROFILES_FILE):
        if not Path(path).exists():
            missing.append(path)
    if missing:
        return {}, {}

    with open(config.ACTIVE_USERS_FILE) as f:
        active = json.load(f)
    with open(config.IMPACT_PROFILES_FILE) as f:
        profiles = json.load(f)
    return active, profiles


active_data, profiles_data = load_data()

# ── Guard: data not yet generated ─────────────────────────────────────────────

if not active_data:
    st.title("🏆 Engineering Impact Dashboard")
    st.warning(
        "No data found. Run the pipeline first:\n\n"
        "```bash\n"
        "GITHUB_REPO=owner/repo python data_downloader.py\n"
        "python calculate_active_users.py\n"
        "ANTHROPIC_API_KEY=sk-ant-... python llm_evaluator.py\n"
        "```"
    )
    st.stop()


# ── Header ─────────────────────────────────────────────────────────────────────

meta = active_data["meta"]
repo = meta.get("repo", "")
generated_at = meta.get("generated_at", "")[:10]
lookback = meta.get("lookback_days", config.LOOKBACK_DAYS)
users = active_data["users"]
profiles = profiles_data.get("profiles", {})

st.markdown(
    f"<h1 style='color:#e6edf3;margin-bottom:0'>🏆 Engineering Impact Dashboard</h1>"
    f"<p style='color:#8b949e;margin-top:4px'>"
    f"<b style='color:#58a6ff'>{repo}</b> &nbsp;·&nbsp; "
    f"Last {lookback} days &nbsp;·&nbsp; Generated {generated_at}"
    f"</p>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div style="
    background: #161b22;
    border: 1px solid #30363d;
    border-left: 4px solid #f0883e;
    border-radius: 8px;
    padding: 12px 18px;
    margin: 12px 0 20px 0;
    display: flex;
    align-items: baseline;
    gap: 10px;
">
    <span style="font-size:16px">⚠️</span>
    <span style="color:#8b949e;font-size:13px">
        <b style="color:#f0883e">Goodhart's Law:</b>
        &ldquo;When a measure becomes a target, it ceases to be a good measure.&rdquo;
        These metrics are a <em>signal</em>, not a scoreboard &mdash;
        use them to start conversations, not end them.
    </span>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("---")

# ── Summary metrics ────────────────────────────────────────────────────────────

total_prs = sum(u["prs"] for u in users)
total_issues = sum(u["issues_closed"] for u in users)
total_reviews = sum(u["reviews_given"] for u in users)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Contributors analyzed", len(users))
c2.metric("Pull requests", total_prs)
c3.metric("Issues closed", total_issues)
c4.metric("Reviews given", total_reviews)

st.markdown("<br>", unsafe_allow_html=True)

# ── Leaderboard ────────────────────────────────────────────────────────────────

st.markdown("## Leaderboard")

df = pd.DataFrame(users)
df.index = range(1, len(df) + 1)

# Add persona and complexity from LLM profiles
df["persona"] = df["username"].map(
    lambda u: profiles.get(u, {}).get("impact_persona", "—")
)
df["complexity"] = df["username"].map(
    lambda u: profiles.get(u, {}).get("technical_complexity", "—")
)
df["mentorship"] = df["username"].map(
    lambda u: profiles.get(u, {}).get("mentorship_signal", "—")
)
df["refactor"] = df["username"].map(
    lambda u: "✅" if profiles.get(u, {}).get("is_refactor_heavy") else ""
)

display_df = df[["username", "score", "prs", "issues_closed", "reviews_given", "persona", "complexity", "mentorship", "refactor"]].copy()
display_df.columns = ["Developer", "Score", "PRs", "Issues Closed", "Reviews Given", "Persona", "Complexity (1-10)", "Mentorship (1-10)", "Refactor?"]

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=False,
    column_config={
        "Score": st.column_config.NumberColumn(format="%.1f"),
        "Complexity (1-10)": st.column_config.NumberColumn(format="%d"),
        "Mentorship (1-10)": st.column_config.NumberColumn(format="%d"),
    },
)

# ── Bar chart — scores ─────────────────────────────────────────────────────────

st.markdown("## Score Breakdown")

fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(
    name="PRs",
    x=df["username"],
    y=df["prs"] * config.SCORE_WEIGHTS["prs"],
    marker_color="#388bfd",
    hovertemplate="%{x}<br>PRs contribution: %{y:.1f}<extra></extra>",
))
fig_bar.add_trace(go.Bar(
    name="Issues Closed",
    x=df["username"],
    y=df["issues_closed"] * config.SCORE_WEIGHTS["issues_closed"],
    marker_color="#3fb950",
    hovertemplate="%{x}<br>Issues contribution: %{y:.1f}<extra></extra>",
))
fig_bar.add_trace(go.Bar(
    name="Reviews Given",
    x=df["username"],
    y=df["reviews_given"] * config.SCORE_WEIGHTS["reviews_given"],
    marker_color="#f0883e",
    hovertemplate="%{x}<br>Reviews contribution: %{y:.1f}<extra></extra>",
))
fig_bar.update_layout(
    barmode="stack",
    plot_bgcolor="#0d1117",
    paper_bgcolor="#0d1117",
    font=dict(color="#e6edf3"),
    legend=dict(bgcolor="#161b22", bordercolor="#30363d", borderwidth=1),
    xaxis=dict(gridcolor="#21262d"),
    yaxis=dict(gridcolor="#21262d", title="Weighted Score"),
    margin=dict(t=20, b=40),
    height=360,
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Individual developer profile ───────────────────────────────────────────────

st.markdown("## Developer Profile")

usernames = [u["username"] for u in users]
selected = st.selectbox(
    "Select a developer",
    usernames,
    format_func=lambda u: f"@{u}",
)

if selected:
    user_stats = next(u for u in users if u["username"] == selected)
    profile = profiles.get(selected, {})

    rank = usernames.index(selected) + 1

    left, right = st.columns([1, 1.4])

    with left:
        # Radar chart
        categories = ["Technical\nComplexity", "Mentorship\nSignal", "Score\n(normalized)"]
        max_score = users[0]["score"] if users else 1
        values = [
            profile.get("technical_complexity", 5),
            profile.get("mentorship_signal", 5),
            round(user_stats["score"] / max_score * 10, 1),
        ]
        # Close the shape
        categories_closed = categories + [categories[0]]
        values_closed = values + [values[0]]

        fig_radar = go.Figure(go.Scatterpolar(
            r=values_closed,
            theta=categories_closed,
            fill="toself",
            fillcolor="rgba(56, 139, 253, 0.2)",
            line=dict(color="#388bfd", width=2),
            marker=dict(color="#388bfd", size=6),
            hovertemplate="%{theta}: %{r}<extra></extra>",
        ))
        fig_radar.update_layout(
            polar=dict(
                bgcolor="#161b22",
                radialaxis=dict(
                    visible=True,
                    range=[0, 10],
                    gridcolor="#30363d",
                    linecolor="#30363d",
                    tickcolor="#8b949e",
                    tickfont=dict(color="#8b949e", size=10),
                ),
                angularaxis=dict(
                    gridcolor="#30363d",
                    linecolor="#30363d",
                    tickfont=dict(color="#cdd9e5", size=12),
                ),
            ),
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            font=dict(color="#e6edf3"),
            margin=dict(t=30, b=30, l=60, r=60),
            height=320,
            showlegend=False,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with right:
        st.markdown("<br>", unsafe_allow_html=True)

        # Rank + persona
        persona = profile.get("impact_persona", "—")
        st.markdown(
            f"<div style='margin-bottom:8px'>"
            f"<span class='score-rank'>#{rank}</span> &nbsp; "
            f"<span class='persona-badge'>{persona}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Refactor badge
        if profile.get("is_refactor_heavy"):
            st.markdown(
                "<span class='refactor-badge'>♻ Refactor-heavy</span>&nbsp;",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # Stat pills
        st.markdown(
            f"""
            <div>
              <div class='stat-pill'>
                <div class='stat-number'>{user_stats['prs']}</div>
                <div style='color:#8b949e;font-size:11px'>Pull Requests</div>
              </div>
              <div class='stat-pill'>
                <div class='stat-number'>{user_stats['issues_closed']}</div>
                <div style='color:#8b949e;font-size:11px'>Issues Closed</div>
              </div>
              <div class='stat-pill'>
                <div class='stat-number'>{user_stats['reviews_given']}</div>
                <div style='color:#8b949e;font-size:11px'>Reviews Given</div>
              </div>
              <div class='stat-pill'>
                <div class='stat-number'>{user_stats['score']:.1f}</div>
                <div style='color:#8b949e;font-size:11px'>Weighted Score</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # LLM score pills
        tc = profile.get("technical_complexity", "—")
        ms = profile.get("mentorship_signal", "—")
        st.markdown(
            f"""
            <div>
              <div class='stat-pill'>
                <div class='stat-number'>{tc}<span style='font-size:13px;color:#8b949e'>/10</span></div>
                <div style='color:#8b949e;font-size:11px'>Technical Complexity</div>
              </div>
              <div class='stat-pill'>
                <div class='stat-number'>{ms}<span style='font-size:13px;color:#8b949e'>/10</span></div>
                <div style='color:#8b949e;font-size:11px'>Mentorship Signal</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Justification
        justification = profile.get("summary_justification", "No justification available.")
        st.markdown(
            f"<div class='justification-box'>{justification}</div>",
            unsafe_allow_html=True,
        )

# ── Methodology & trade-offs ───────────────────────────────────────────────────

with st.expander("Methodology & known trade-offs", expanded=False):
    st.markdown(
        """
<div style="color:#cdd9e5;font-size:13px;line-height:1.75">

<b style="color:#e6edf3">How scores are calculated</b><br>
Each contributor is ranked by a weighted formula:
<code style="background:#21262d;padding:2px 6px;border-radius:4px">score = 2×PRs + 3×issues closed + 1.5×reviews given</code>
applied over the past 90 days. The top contributors are then evaluated qualitatively
by an LLM that reads PR titles, descriptions, and review bodies to produce the
<em>ImpactProfile</em> fields.

<br><br>
<b style="color:#e6edf3">Known limitations of the hard-metric stage</b>

<ul style="margin-top:6px;padding-left:18px">
  <li><b>Quantity over quality.</b> PR count is the dominant term but says nothing about scope.
  A typo fix and a week-long refactor each add 2 points.</li>

  <li><b>All reviews are equal.</b> A one-word "LGTM" and a thorough architectural critique
  both increment <em>reviews given</em> by 1. Review depth is invisible until the LLM stage.</li>

  <li><b>No tenure normalisation.</b> A contributor active for 2 weeks is ranked against
  one active for the full 90-day window without adjustment.</li>

  <li><b>Arbitrary weights.</b> The 2 / 3 / 1.5 coefficients are personal heuristics and have no empirical basis.
  Shifting them changes the leaderboard order non-trivially.</li>
</ul>

<b style="color:#e6edf3">What the LLM stage adds</b><br>
The qualitative evaluation reads actual content and partially compensates for the quality-blindness
above — but it only runs on candidates who already made the top-N cut, so contributors
gamed out of the list never receive a second look.

</div>
""",
        unsafe_allow_html=True,
    )

# ── Footer ─────────────────────────────────────────────────────────────────────

st.markdown("---")
llm_model = profiles_data.get("meta", {}).get("model", config.LLM_MODEL)
st.markdown(
    f"<p style='color:#8b949e;font-size:12px;text-align:center'>"
    f"LLM evaluation powered by <b>{llm_model}</b> via instructor &nbsp;·&nbsp; "
    f"Score = 2×PRs + 3×Issues Closed + 1.5×Reviews"
    f"</p>",
    unsafe_allow_html=True,
)
