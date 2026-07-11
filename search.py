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
    """Returns a formatted string of search results, or None if it fails."""
    key = get_tavily_key()
    if not key:
        return None
    try:
        client = TavilyClient(api_key=key)
        results = client.search(query, max_results=max_results)
        formatted = []
        for r in results.get("results", []):
            formatted.append(f"- {r['title']}: {r['content'][:300]} (source: {r['url']})")
        return "\n".join(formatted) if formatted else None
    except Exception:
        return None