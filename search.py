import os
import re
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
    "arabic": ["arabnews.com", "albawaba.com", "gulfnews.com", "thenationalnews.com"],
}


def _detect_region(query):
    q = query.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return region
    return None


def _search_exa(query, max_results, include_domains=None):
    key = get_exa_key()
    if not key:
        return None
    try:
        client = Exa(api_key=key)
        kwargs = {
            "num_results": max_results,
            "text": {"max_characters": 600},
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        response = client.search_and_contents(query, **kwargs)
        structured = []
        for r in response.results:
            structured.append({
                "title": r.title or "Untitled",
                "url": r.url or "",
                "content": (r.text or "")[:600],
            })
        return structured if structured else None
    except Exception as e:
        print(f"[search.py] Exa search failed: {e}")
        return None


def _search_tavily(query, max_results):
    key = get_tavily_key()
    if not key:
        return None
    try:
        client = TavilyClient(api_key=key)
        results = client.search(query, max_results=max_results)
        structured = []
        for r in results.get("results", []):
            structured.append({
                "title": r.get("title", "Untitled"),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:300],
            })
        return structured if structured else None
    except Exception as e:
        print(f"[search.py] Tavily search failed: {e}")
        return None


def search_web(query, max_results=4, provider="auto"):
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
    """
    provider = (provider or "auto").lower()
    max_results = extract_max_results(query, fallback=max_results)
    region = _detect_region(query)
    include_domains = REGION_DOMAINS.get(region) if region else None

    if provider == "exa":
        result = _search_exa(query, max_results, include_domains)
        return (result, "Exa") if result else (None, None)

    if provider == "tavily":
        result = _search_tavily(query, max_results)
        return (result, "Tavily") if result else (None, None)

    if provider == "youtube":
        result = youtube.search_youtube(query, max_results)
        return (result, "YouTube API") if result else (None, None)

    # auto
    if youtube.is_youtube_intent(query):
        result = youtube.search_youtube(query, max_results)
        if result:
            return result, "YouTube API"

    result = _search_exa(query, max_results, include_domains)
    if result:
        return result, "Exa"
    result = _search_tavily(query, max_results)
    if result:
        return result, "Tavily"
    return None, None