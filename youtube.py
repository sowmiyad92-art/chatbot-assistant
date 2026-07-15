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
        if resp.status_code != 200:
            print(f"[youtube.py] channels.forHandle failed: {resp.status_code} {resp.text[:300]}")
            return None
        items = resp.json().get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"[youtube.py] channels.forHandle exception: {e}")
        return None


def _channel_id_from_name(name, key):
    """
    Resolve a plain channel name (e.g. 'DramaBox', no @) to a channelId
    via search.list?type=channel. This covers queries that mention a
    channel/brand by name without an explicit @handle.
    """
    if not name:
        return None
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "channel",
                "q": name,
                "maxResults": 1,
                "key": key,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[youtube.py] search.list(type=channel) failed: {resp.status_code} {resp.text[:300]}")
            return None
        items = resp.json().get("items", [])
        if not items:
            return None
        return items[0]["snippet"]["channelId"]
    except Exception as e:
        print(f"[youtube.py] search.list(type=channel) exception: {e}")
        return None


def search_youtube(query, max_results=5):
    """
    Returns structured results: [{"title","url","content"}] where content
    includes the EXACT view count/publish date from YouTube's own API
    (not scraped text), or None if key missing / call fails / no results.
    """
    key = get_youtube_key()
    if not key:
        print("[youtube.py] no YOUTUBE_API_KEY configured")
        return None

    try:
        handle = _extract_handle(query)
        clean_query = re.sub(r"@\S+", "", query).strip()

        channel_id = _channel_id_from_handle(handle, key) if handle else None
        if not channel_id:
            # No @handle given (or it didn't resolve) — try resolving a
            # channel by name from the free-text query instead of giving up.
            channel_id = _channel_id_from_name(clean_query, key)

        search_params = {
            "part": "snippet",
            "type": "video",
            "maxResults": max_results,
            "order": "viewCount",
            "key": key,
        }
        if channel_id:
            # Scoped to the resolved channel — no need for "q" noise here,
            # order=viewCount alone surfaces that channel's top videos.
            search_params["channelId"] = channel_id
        elif clean_query:
            # Last resort: unscoped keyword search across all of YouTube.
            search_params["q"] = clean_query

        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=search_params,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[youtube.py] search.list(type=video) failed: {resp.status_code} {resp.text[:300]}")
            return None

        items = resp.json().get("items", [])
        video_ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
        if not video_ids:
            print(f"[youtube.py] no video ids for query={query!r} channel_id={channel_id!r}")
            return None

        stats_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(video_ids), "key": key},
            timeout=10,
        )
        if stats_resp.status_code != 200:
            print(f"[youtube.py] videos.list failed: {stats_resp.status_code} {stats_resp.text[:300]}")
            return None

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
    except Exception as e:
        print(f"[youtube.py] search_youtube unexpected exception: {e}")
        return None