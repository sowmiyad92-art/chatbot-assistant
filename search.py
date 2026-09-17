# search.py — full file

import os
import re
from datetime import datetime, timedelta
from tavily import TavilyClient
from exa_py import Exa
from dotenv import load_dotenv

import youtube

load_dotenv()


def _get_key(name):
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name)


def get_tavily_key():
    return _get_key("TAVILY_API_KEY")


def get_exa_key():
    return _get_key("EXA_API_KEY")


# --- top-N parsing -----------------------------------------------------

_TOPN_PATTERNS = [
    re.compile(r"\btop\s*(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,2})\s*(?:movies|videos|shows|series|dramas|titles|stories|articles)\b", re.I),
]


def extract_max_results(query, fallback=4, cap=15):
    """
    Look for an explicit count in the query text ("top 5", "10 movies", etc.)
    and use that instead of the hardcoded default. Capped at `cap` to keep
    API usage/quota sane. Falls back to `fallback` if nothing found.
    """
    for pattern in _TOPN_PATTERNS:
        match = pattern.search(query)
        if match:
            n = int(match.group(1))
            if n > 0:
                return min(n, cap)
    return fallback


# --- region-aware domain scoping ----------------------------------------
# Exa/Tavily are English-web-centric by default and won't reliably surface
# region-specific entertainment trade press. When a query signals a region,
# scope the search to known trade sources for that region instead of a
# separate regional API.

REGION_KEYWORDS = {
    "chinese": ["chinese", "china", "mandarin", "cdrama", "c-drama", "weibo"],
    "korean": ["korean", "korea", "kdrama", "k-drama", "hallyu", "seoul"],
    "arabic": ["arabic", "arab", "middle east", "gulf", "mena", "saudi", "egypt"],
}

REGION_DOMAINS = {
    "chinese": ["variety.com", "hollywoodreporter.com", "mtime.com", "ent.sina.com.cn", "yicai.com"],
    "korean": ["soompi.com", "koreaherald.com", "koreatimes.co.kr", "hancinema.net", "newsen.com"],
    "arabic": [
        "arabnews.com", "albawaba.com", "gulfnews.com", "thenationalnews.com",
        "broadcastprome.com", "see.news",
    ],
}


def _detect_region(query):
    q = query.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return region
    return None


def _search_exa(query, max_results, include_domains=None, start_published_date=None, max_characters=400):
    key = get_exa_key()
    if not key:
        return None
    try:
        client = Exa(api_key=key)
        kwargs = {
            "num_results": max_results,
            "text": {"max_characters": max_characters},
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if start_published_date:
            kwargs["start_published_date"] = start_published_date
        response = client.search_and_contents(query, **kwargs)
        structured = []
        for r in response.results:
            structured.append({
                "title": r.title or "Untitled",
                "url": r.url or "",
                "content": (r.text or "")[:max_characters],
            })
        return structured if structured else None
    except Exception as e:
        print(f"[search.py] Exa search failed: {e}")
        return None


def _search_tavily(query, max_results, topic=None, days=None, include_domains=None, content_chars=300):
    key = get_tavily_key()
    if not key:
        return None
    try:
        client = TavilyClient(api_key=key)
        kwargs = {"max_results": max_results}
        if topic:
            kwargs["topic"] = topic  # "news" enables recency filtering below
        if days:
            kwargs["days"] = days    # only honored by Tavily when topic="news"
        if include_domains:
            kwargs["include_domains"] = include_domains
        results = client.search(query, **kwargs)
        structured = []
        for r in results.get("results", []):
            structured.append({
                "title": r.get("title", "Untitled"),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:content_chars],
            })
        return structured if structured else None
    except Exception as e:
        print(f"[search.py] Tavily search failed: {e}")
        return None


def search_web(query, max_results=4, provider="auto", recency_days=None, extra_domains=None, content_chars=None):
    """
    Returns a tuple: (results, provider_used)
    - results: list of dicts [{"title", "url", "content"}, ...] or None
    - provider_used: "YouTube API", "Exa", "Tavily", or None

    provider controls routing:
    - "auto" (default): if the query looks YouTube-related (channel handle,
      "views", "trending", "subscribers", etc.), try YouTube API first, then
      fall back to Exa, then Tavily. Otherwise Exa first, Tavily fallback.
      Region-specific entertainment queries (Chinese/Korean/Arabic) scope
      Exa to known trade-press domains for that region.
    - "exa": Exa only, no fallback.
    - "tavily": Tavily only, no fallback.
    - "youtube": YouTube API only, no fallback.

    max_results is overridden if the query itself specifies a count
    ("top 5", "top 10", "5 movies", etc.) — capped at 15.

    recency_days: optional int. When set, scopes results to roughly the
    last N days instead of Exa/Tavily's default broad web index, and on
    Tavily also switches to topic="news" (news-article index only) — use
    for "today"/"latest" NEWS-style queries. Do NOT use for queries whose
    answer lives on non-news sites (e.g. movie listings/calendars) — use
    extra_domains for those instead. Leave None (default) for existing
    callers — behavior is unchanged.

    extra_domains: optional list of domains to scope the search to,
    independent of the auto region detection — e.g. movie-calendar sites
    for the digest's movies section. Merged with any region-detected
    domains if both apply. Works with both Exa and Tavily.

    content_chars: optional int, overrides the default content-snippet
    length (400 for Exa, 300 for Tavily). Long listing/calendar pages
    need a much bigger slice than a typical news article to reach the
    relevant part of the page — pass a higher value (e.g. 2000) for
    those queries. Leave None (default) for existing callers.
    """
    provider = (provider or "auto").lower()
    max_results = extract_max_results(query, fallback=max_results)
    region = _detect_region(query)
    include_domains = REGION_DOMAINS.get(region) if region else None
    if extra_domains:
        include_domains = list(set((include_domains or []) + extra_domains))

    start_published_date = None
    if recency_days:
        start_published_date = (
            datetime.utcnow() - timedelta(days=recency_days)
        ).strftime("%Y-%m-%dT00:00:00.000Z")

    exa_chars = content_chars if content_chars else 400
    tavily_chars = content_chars if content_chars else 300

    if provider == "exa":
        result = _search_exa(query, max_results, include_domains, start_published_date, max_characters=exa_chars)
        return (result, "Exa") if result else (None, None)

    if provider == "tavily":
        topic = "news" if recency_days else None
        result = _search_tavily(query, max_results, topic=topic, days=recency_days, include_domains=include_domains, content_chars=tavily_chars)
        return (result, "Tavily") if result else (None, None)

    if provider == "youtube":
        result = youtube.search_youtube(query, max_results)
        return (result, "YouTube API") if result else (None, None)

    # auto
    if youtube.is_youtube_intent(query):
        result = youtube.search_youtube(query, max_results)
        if result:
            return result, "YouTube API"

    result = _search_exa(query, max_results, include_domains, start_published_date, max_characters=exa_chars)
    if result:
        return result, "Exa"
    topic = "news" if recency_days else None
    result = _search_tavily(query, max_results, topic=topic, days=recency_days, include_domains=include_domains, content_chars=tavily_chars)
    if result:
        return result, "Tavily"
    return None, None
