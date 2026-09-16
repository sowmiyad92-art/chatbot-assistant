# digest_sections.py — full file
# Fix: provider="tavily" (no fallback, silent) -> provider="auto" (Exa -> Tavily fallback)
# Plus: error/empty logging instead of silent "Nothing found today"
# Plus: build_youtube uses transcript, falls back to description

from datetime import date
import llm
import search
import youtube as yt_search  # existing module, has search_youtube()

# ---------------------------------------------------------------------
# Static config
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
# 1. Job-prep questions (Groq via llm.get_response)
# ---------------------------------------------------------------------

def build_job_questions(config, scheduled_query_id):
    prompt = (
        "Generate 5 realistic interview questions for an AI Automation "
        "Specialist role — mix of technical (LLM APIs, pipelines, "
        "automation tooling) and scenario-based. For each question, give "
        "a concise model answer (3-4 sentences) right after it. "
        "Format: numbered question, then 'A:' on the next line. No preamble."
    )
    result = llm.get_response([{"role": "user", "content": prompt}])
    return result["text"]


# ---------------------------------------------------------------------
# 2 & 3 & 5. Search-based sections (AI news / tool launches / world news)
# ---------------------------------------------------------------------

def _search_and_format(query, max_results=5):
    try:
        # FIX: was provider="tavily" — forced Tavily with zero fallback,
        # so a missing/bad TAVILY_API_KEY silently returned nothing even
        # when Exa was configured and working. "auto" tries Exa first,
        # then Tavily, matching how the chat assistant already searches.
        results, provider = search.search_web(query, max_results=max_results, provider="auto")
    except Exception as e:
        print(f"[digest_sections.py] search_web raised for {query!r}: {e}")
        return "Nothing found today."
    if not results:
        print(f"[digest_sections.py] search_web returned empty for {query!r} (provider={provider})")
        return "Nothing found today."
    return "\n".join(f"- {r['title']}" for r in results)

def build_ai_news(config, scheduled_query_id):
    return _search_and_format("AI news today")

def build_ai_tool_launches(config, scheduled_query_id):
    return _search_and_format("new AI tool or model launch today")

def build_world_trending_news(config, scheduled_query_id):
    return _search_and_format("world trending news today stock market climate")


# ---------------------------------------------------------------------
# 4. Movies releasing today
# ---------------------------------------------------------------------

def build_movies(config, scheduled_query_id):
    today_str = date.today().strftime("%B %d, %Y")

    try:
        # FIX: same provider="tavily" -> "auto" issue as _search_and_format
        results, provider = search.search_web(
            f"movies releasing {today_str} theatrical OTT streaming",
            max_results=8,
            provider="auto"
        )
    except Exception as e:
        print(f"[digest_sections.py] search_web raised for movies query: {e}")
        return "Nothing found today."

    if not results:
        print(f"[digest_sections.py] search_web returned empty for movies query (provider={provider})")
        return "Nothing found today."

    raw_titles = "\n".join(f"- {r['title']}" for r in results)

    prompt = f"""From these search results about movies releasing on {today_str}, 
extract only actual feature film releases (skip trailers, re-releases, TV episodes).
Group into "Theatrical" and "Streaming/OTT" sections. If a detail (genre, language, 
platform) isn't available, omit it rather than guessing.

Search results:
{raw_titles}"""

    result = llm.get_response([{"role": "user", "content": prompt}])
    return result["text"]


# ---------------------------------------------------------------------
# 6. YouTube — latest upload from the 4 tracked channels + transcript summary
# ---------------------------------------------------------------------

def build_youtube(config, scheduled_query_id):
    from youtube import get_latest_upload, get_transcript

    candidates = []
    for name, channel_id in YOUTUBE_CHANNELS.items():
        video = get_latest_upload(channel_id)
        if video:
            candidates.append({**video, "channel": name})

    if not candidates:
        return "No video found today."

    pick = max(candidates, key=lambda v: v["published_at"])
    video_id = pick["url"].split("v=")[-1]

    transcript_text = get_transcript(video_id)
    source_text = transcript_text or pick.get("description", "")[:500]

    if not source_text:
        summary = "(no transcript or description available)"
    else:
        summary_prompt = (
            f"Title: {pick['title']}\nContent: {source_text}\n\n"
            "Summarize this video in 2 short sentences."
        )
        summary = llm.get_response([{"role": "user", "content": summary_prompt}])["text"]

    return f"{pick['title']} ({pick['channel']})\n{summary}\n{pick['url']}"


# ---------------------------------------------------------------------
# 7. Gita quote of the day (static, rotates)
# ---------------------------------------------------------------------

def build_gita_quote(config, scheduled_query_id):
    day_index = date.today().timetuple().tm_yday
    q = GITA_QUOTES[day_index % len(GITA_QUOTES)]
    return f'"{q["text"]}" — Bhagavad Gita {q["ref"]}'
