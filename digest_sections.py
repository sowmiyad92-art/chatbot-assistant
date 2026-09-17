# digest_sections.py — full file

from datetime import date
import requests
from bs4 import BeautifulSoup

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

def _search_and_format(query, max_results=5, recency_days=1):
    try:
        results, provider = search.search_web(
            query, max_results=max_results, provider="auto", recency_days=recency_days
        )
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
    topics = ["world trending news today", "stock market today", "climate news today"]
    seen = set()
    lines = []
    for topic in topics:
        try:
            results, provider = search.search_web(topic, max_results=3, provider="auto", recency_days=1)
        except Exception as e:
            print(f"[digest_sections.py] search_web raised for {topic!r}: {e}")
            continue
        if not results:
            continue
        for r in results:
            if r["title"] not in seen:
                seen.add(r["title"])
                lines.append(f"- {r['title']}")
        if len(lines) >= 5:
            break
    return "\n".join(lines[:5]) if lines else "Nothing found today."


# ---------------------------------------------------------------------
# 4. Movies releasing today & Netflix OTT
# ---------------------------------------------------------------------

def build_movies(config, scheduled_query_id):
    today = date.today()
    today_str = today.strftime("%B %d, %Y")
    calendar_url = f"https://www.boxofficemojo.com/calendar/{today.strftime('%Y-%m-%d')}/"
    try:
        resp = requests.get(
            calendar_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[digest_sections.py] Box Office Mojo fetch failed: {e}")
        return "Nothing found today."

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        print(f"[digest_sections.py] No table found on {calendar_url}")
        return "Nothing found today."

    titles = []
    for row in table.find_all("tr")[1:]:  # skip header row
        cells = row.find_all("td")
        if not cells:
            continue
        h3 = cells[0].find("h3")
        title = h3.get_text(strip=True) if h3 else cells[0].get_text(strip=True)
        if title:
            titles.append(title)

    if not titles:
        print(f"[digest_sections.py] Table found but no titles parsed for {calendar_url}")
        return "Nothing found today."

    formatted = "\n".join(f"- {t}" for t in titles[:8])
    return f"**Theatrical (week of {today_str}):**\n{formatted}"

def build_netflix_ott(config, scheduled_query_id):
    url = "https://www.whats-on-netflix.com/new-titles-this-week/"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[digest_sections.py] Netflix fetch failed: {e}")
        return "Nothing found today."

    soup = BeautifulSoup(resp.text, "html.parser")
    headings = soup.find_all(["h2", "h3"], limit=20)
    titles = [h.get_text(strip=True) for h in headings if h.get_text(strip=True)]
    titles = [t for t in titles if len(t) < 80][:8]  # drop long boilerplate headings

    if not titles:
        print(f"[digest_sections.py] No titles parsed for {url}")
        return "Nothing found today."

    return "\n".join(f"- {t}" for t in titles)


# ---------------------------------------------------------------------
# 6. YouTube — latest upload from the 4 tracked channels + transcript summary
# ---------------------------------------------------------------------

def build_youtube(config, scheduled_query_id):
    from youtube import get_latest_upload  # get_transcript import removed

    candidates = []
    for name, channel_id in YOUTUBE_CHANNELS.items():
        video = get_latest_upload(channel_id)
        if video:
            candidates.append({**video, "channel": name})

    if not candidates:
        return "No video found today."

    pick = max(candidates, key=lambda v: v["published_at"])

    # Transcript fetch removed — youtube-transcript-api is reliably IP-blocked
    # on GitHub Actions runners (cloud provider IP). Description is the
    # only reliable source in CI.
    source_text = pick.get("description", "")[:500]

    if not source_text:
        summary = f"{pick['title']} ({pick['channel']})"
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
