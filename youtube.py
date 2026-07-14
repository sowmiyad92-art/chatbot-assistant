import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()


def get_youtube_key():
    try:
        import streamlit as st
        if "YOUTUBE_API_KEY" in st.secrets:
            return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        pass
    return os.environ.get("YOUTUBE_API_KEY")


YOUTUBE_KEYWORDS = [
    "view", "views", "trending", "most viewed", "top video", "top videos",
    "youtube", "subscriber", "subscribers",
]


def is_youtube_intent(query):
    """
    Heuristic: route to YouTube API if query mentions a channel handle (@name),
    or YouTube-specific keywords (views, trending, subscribers, youtube).
    """
    q = query.lower()
    if "@" in query:
        return True
    return any(kw in q for kw in YOUTUBE_KEYWORDS)


def _extract_handle(query):
    match = re.search(r"@([A-Za-z0-9_\-\.]+)", query)
    return match.group(1) if match else None


def _dedupe_by_video_id(videos):
    seen = set()
    unique = []
    for v in videos:
        vid = v.get("_video_id")
        if vid and vid in seen:
            continue
        if vid:
            seen.add(vid)
        unique.append(v)
    return unique


def _channel_id_from_handle(handle, key):
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "id", "forHandle": handle, "key": key},
            timeout=10,
        )
        items = resp.json().get("items", [])
        return items[0]["id"] if items else None
    except Exception:
        return None


def search_youtube(query, max_results=5):
    """
    Returns structured results: [{"title","url","content"}] where content
    includes the EXACT view count/publish date from YouTube's own API
    (not scraped text), or None if key missing / call fails / no results.
    """
    key = get_youtube_key()
    if not key:
        return None

    try:
        handle = _extract_handle(query)
        channel_id = _channel_id_from_handle(handle, key) if handle else None

        clean_query = re.sub(r"@\S+", "", query).strip()
        search_params = {
            "part": "snippet",
            "type": "video",
            "maxResults": max_results,
            "order": "viewCount",
            "key": key,
        }
        if clean_query:
            search_params["q"] = clean_query
        if channel_id:
            search_params["channelId"] = channel_id

        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=search_params,
            timeout=10,
        )
        items = resp.json().get("items", [])
        video_ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
        if not video_ids:
            return None

        stats_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(video_ids), "key": key},
            timeout=10,
        )
        video_items = stats_resp.json().get("items", [])

        structured = []
        for v in video_items:
            vid = v["id"]
            snippet = v.get("snippet", {})
            stats = v.get("statistics", {})
            view_count = stats.get("viewCount")
            title = snippet.get("title", "Untitled")
            channel_title = snippet.get("channelTitle", "")
            published = snippet.get("publishedAt", "")[:10]
            content = (
                f"Exact view count: {view_count if view_count else 'unavailable'}. "
                f"Channel: {channel_title}. Published: {published}."
            )
            structured.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "content": content,
                "_video_id": vid,
            })

        structured = _dedupe_by_video_id(structured)
        for s in structured:
            s.pop("_video_id", None)

        return structured if structured else None
    except Exception:
        return None