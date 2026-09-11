# digest_sections.py — section builders for the daily digest

from datetime import date
import random

# ---------------------------------------------------------------------
# Static config (no live scraping — set once, rotate/reuse daily)
# ---------------------------------------------------------------------

YOUTUBE_CHANNELS = {
    "anthropic": "UCrDwWp7EBBv4NwvScIpBDOA",
    "claude": "UCV03SRZXJEz-hchIAogeJOg",
    "openai": "UCXZCJLdBC09xxGZ6gcdrc6A",
    "google_deepmind": "UCP7jMXSY2xbc3KCAE0MHQ-A",
}

GITA_QUOTES = [
    {"ref": "2.47", "text": "You have the right to your actions, never to the results. Don't work for reward, and don't refuse to work either."},
    {"ref": "2.20", "text": "The soul is never born and never dies. It is unborn, eternal, and remains even after the body is gone."},
    {"ref": "2.22", "text": "As a person sheds worn-out clothes for new ones, the soul leaves an old body and takes on a new one."},
    {"ref": "2.48", "text": "Do your work steadily, without attachment, treating success and failure the same way — that balance is what yoga means."},
    {"ref": "2.40", "text": "No sincere effort on this path is ever wasted; even a little progress protects you from great fear."},
    {"ref": "3.8", "text": "Do the work that's set before you — action itself is better than inaction. Even your body can't survive without effort."},
    {"ref": "3.9", "text": "Work done selflessly doesn't bind you. Work done for yourself alone does."},
    {"ref": "3.19", "text": "Always perform your duty without attachment — that's how a person reaches their highest good."},
    {"ref": "3.35", "text": "It's better to do your own work imperfectly than to master someone else's perfectly."},
    {"ref": "4.7", "text": "Whenever goodness weakens and wrong grows strong, balance returns to restore it."},
    {"ref": "4.18", "text": "The wise see stillness within action and action within stillness — that is true understanding."},
    {"ref": "4.38", "text": "Nothing purifies like true understanding — in time, it reveals itself within."},
    {"ref": "6.5", "text": "Lift yourself by your own effort — you are your own best friend, and your own worst enemy."},
    {"ref": "6.19", "text": "A steady mind in meditation is like a lamp that doesn't flicker in a windless place."},
    {"ref": "18.66", "text": "Let go of every other refuge and surrender fully — you will be freed from all that holds you back."},
]

# ---------------------------------------------------------------------
# 1. Job-prep questions (Groq-generated, AI Automation Specialist angle)
# ---------------------------------------------------------------------

def build_job_questions(config: dict, scheduled_query_id: str) -> str:
    """5 AI Automation Specialist interview-prep questions, LLM-generated."""
    from llm import ask_groq  # existing Aadsia helper

    prompt = (
        "Generate 5 realistic interview questions for an AI Automation "
        "Specialist role — mix of technical (LLM APIs, pipelines, "
        "automation tooling) and scenario-based. One line each, numbered."
    )
    return ask_groq(prompt)


# ---------------------------------------------------------------------
# 2. AI news (search-based, delta-checked against yesterday)
# ---------------------------------------------------------------------

def build_ai_news(config: dict, scheduled_query_id: str) -> str:
    from search import tavily_search
    from db import get_yesterday_payload

    results = tavily_search("AI news today", max_results=8)
    yesterday = get_yesterday_payload(scheduled_query_id, "ai_news")
    fresh = _dedupe_against_yesterday(results, yesterday)
    top5 = fresh[:5]
    return _format_bullets(top5)


# ---------------------------------------------------------------------
# 3. New AI tool/model launches (same pattern, narrower query)
# ---------------------------------------------------------------------

def build_ai_tool_launches(config: dict, scheduled_query_id: str) -> str:
    from search import tavily_search
    from db import get_yesterday_payload

    results = tavily_search("new AI tool OR model launch today", max_results=8)
    yesterday = get_yesterday_payload(scheduled_query_id, "ai_tool_launches")
    fresh = _dedupe_against_yesterday(results, yesterday)
    return _format_bullets(fresh[:5])


# ---------------------------------------------------------------------
# 4. Movies releasing today (theatres/OTT)
# ---------------------------------------------------------------------

def build_movies(config: dict, scheduled_query_id: str) -> str:
    from search import tavily_search

    today_str = date.today().strftime("%B %d, %Y")
    query = f"movies releasing today {today_str} theatres OTT"
    results = tavily_search(query, max_results=5)
    return _format_bullets(results)


# ---------------------------------------------------------------------
# 5. World trending news (top 5 — stock market, climate, etc.)
# ---------------------------------------------------------------------

def build_world_trending_news(config: dict, scheduled_query_id: str) -> str:
    from search import tavily_search
    from db import get_yesterday_payload

    results = tavily_search("world trending news today stock market climate", max_results=8)
    yesterday = get_yesterday_payload(scheduled_query_id, "world_trending_news")
    fresh = _dedupe_against_yesterday(results, yesterday)
    return _format_bullets(fresh[:5])


# ---------------------------------------------------------------------
# 6. YouTube video + short summary (title+description only, no transcript)
# ---------------------------------------------------------------------

def build_youtube(config: dict, scheduled_query_id: str) -> str:
    from youtube import get_latest_video_per_channel  # wraps YouTube Data API
    from llm import ask_groq
    from db import get_yesterday_payload

    candidates = []
    for name, channel_id in YOUTUBE_CHANNELS.items():
        video = get_latest_video_per_channel(channel_id)
        if video:
            candidates.append({**video, "channel": name})

    yesterday = get_yesterday_payload(scheduled_query_id, "youtube")
    fresh = [v for v in candidates if v["video_id"] != yesterday.get("video_id")]

    if not fresh:
        return "No new video today from the tracked channels."

    # simple pick: most recently published
    pick = max(fresh, key=lambda v: v["published_at"])

    summary_prompt = (
        f"Title: {pick['title']}\nDescription: {pick['description'][:500]}\n\n"
        "Summarize this video in 2 short sentences."
    )
    summary = ask_groq(summary_prompt)

    return f"{pick['title']} ({pick['channel']})\n{summary}\n{pick['url']}"


# ---------------------------------------------------------------------
# 7. Gita quote of the day (static list, rotates by day-of-year)
# ---------------------------------------------------------------------

def build_gita_quote(config: dict, scheduled_query_id: str) -> str:
    day_index = date.today().timetuple().tm_yday
    quote = GITA_QUOTES[day_index % len(GITA_QUOTES)]
    return f'"{quote["text"]}" — Bhagavad Gita {quote["ref"]}'


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

def _dedupe_against_yesterday(results: list, yesterday_payload) -> list:
    yesterday_titles = set()
    if isinstance(yesterday_payload, str):
        yesterday_titles = {line.strip() for line in yesterday_payload.split("\n")}
    return [r for r in results if r.get("title") not in yesterday_titles]


def _format_bullets(results: list) -> str:
    if not results:
        return "Nothing new since yesterday."
    return "\n".join(f"- {r['title']}" for r in results)
