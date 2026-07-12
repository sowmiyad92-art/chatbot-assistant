import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


def get_tavily_key():
    try:
        import streamlit as st
        if "TAVILY_API_KEY" in st.secrets:
            return st.secrets["TAVILY_API_KEY"]
    except Exception:
        pass
    return os.environ.get("TAVILY_API_KEY")


def search_web(query, max_results=4):
    """
    Returns a list of dicts: [{"title": ..., "url": ..., "content": ...}, ...]
    or None if search fails / no key configured.
    Kept structured (not pre-formatted) so the UI can render a separate
    sources panel instead of inline URLs in the answer text.
    """
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