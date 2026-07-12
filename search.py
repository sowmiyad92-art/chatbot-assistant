import os
from tavily import TavilyClient
from exa_py import Exa
from dotenv import load_dotenv

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


def _search_exa(query, max_results):
    key = get_exa_key()
    if not key:
        return None
    try:
        client = Exa(api_key=key)
        response = client.search_and_contents(
            query,
            num_results=max_results,
            text={"max_characters": 300},
        )
        structured = []
        for r in response.results:
            structured.append({
                "title": r.title or "Untitled",
                "url": r.url or "",
                "content": (r.text or "")[:300],
            })
        return structured if structured else None
    except Exception:
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
    except Exception:
        return None


def search_web(query, max_results=4):
    """
    Returns a tuple: (results, provider)
    - results: list of dicts [{"title", "url", "content"}, ...] or None
    - provider: "Exa", "Tavily", or None (if both failed / no keys configured)
    Tries Exa first (primary), falls back to Tavily if Exa fails or
    returns no results.
    Kept structured (not pre-formatted) so the UI can render a separate
    sources panel instead of inline URLs in the answer text.
    """
    result = _search_exa(query, max_results)
    if result:
        return result, "Exa"
    result = _search_tavily(query, max_results)
    if result:
        return result, "Tavily"
    return None, None