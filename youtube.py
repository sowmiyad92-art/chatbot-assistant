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


_FILLER_WORDS_RE = re.compile(
    r"\b(search|show me|on youtube|their|most[- ]watched|most watched|"
    r"videos?|with exact|exact|view counts?|views?|upload dates?|uploaded|"
    r"published|find|please|can you|i want|show|me|and|for|dates?|channel|top)\b",
    re.IGNORECASE,
)


def _probable_channel_name(query):
    """
    Strip common request-scaffolding words from a free-text query to isolate
    the likely channel name, e.g. 'Search Reelshort on YouTube and show me
    their 3 most-watched videos with exact view counts' -> 'Reelshort'.
    Generic on purpose — works for any channel name, not just known ones.
    """
    text = re.sub(r"@\S+", "", query)
    text = _FILLER_WORDS_RE.sub("", text)
    text = re.sub(r"\d+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .,!?")
    return text or None


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


def _uploads_playlist_id(channel_id, key):
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "contentDetails", "id": channel_id, "key": key},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[youtube.py] channels.contentDetails failed: {resp.status_code} {resp.text[:300]}")
            return None
        items = resp.json().get("items", [])
        if not items:
            return None
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"[youtube.py] channels.contentDetails exception: {e}")
        return None


def _playlist_video_ids(playlist_id, key, max_pages=10, page_size=50):
    """
    Paginate a channel's uploads playlist to collect video IDs. Scans up to
    max_pages * page_size videos (default 500) in upload order (newest
    first). NOTE: for channels with a very large back catalog, a much
    older viral video beyond this scan window could still be missed —
    raise max_pages if that matters more than quota usage.
    """
    ids = []
    page_token = None
    for _ in range(max_pages):
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": page_size,
            "key": key,
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params=params,
                timeout=10,
            )
        except Exception as e:
            print(f"[youtube.py] playlistItems exception: {e}")
            break
        if resp.status_code != 200:
            print(f"[youtube.py] playlistItems failed: {resp.status_code} {resp.text[:300]}")
            break
        data = resp.json()
        ids.extend(
            i["contentDetails"]["videoId"]
            for i in data.get("items", [])
            if i.get("contentDetails", {}).get("videoId")
        )
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


def _videos_with_stats(video_ids, key):
    """Batch-fetch snippet+statistics for video_ids, 50 at a time."""
    all_items = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "snippet,statistics", "id": ",".join(batch), "key": key},
                timeout=10,
            )
        except Exception as e:
            print(f"[youtube.py] videos.list exception: {e}")
            continue
        if resp.status_code != 200:
            print(f"[youtube.py] videos.list failed: {resp.status_code} {resp.text[:300]}")
            continue
        all_items.extend(resp.json().get("items", []))
    return all_items


def _to_structured(video_items):
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
            "_view_count": int(view_count) if view_count and view_count.isdigit() else -1,
        })
    return structured


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
            # No @handle (or it didn't resolve) — try a cleaned probable
            # channel name first (works for any channel, not hardcoded),
            # falling back to the raw clean_query as a last resort.
            channel_id = _channel_id_from_name(_probable_channel_name(query), key)
            if not channel_id:
                channel_id = _channel_id_from_name(clean_query, key)

        if channel_id:
            # Reliable path: pull the channel's actual uploads and rank by
            # viewCount ourselves — search.list's order=viewCount only sorts
            # within whatever subset it indexed, not the full channel history.
            playlist_id = _uploads_playlist_id(channel_id, key)
            if not playlist_id:
                print(f"[youtube.py] no uploads playlist for channel_id={channel_id!r}")
                return None
            video_ids = _playlist_video_ids(playlist_id, key)
            if not video_ids:
                print(f"[youtube.py] no videos in uploads playlist={playlist_id!r}")
                return None
            video_items = _videos_with_stats(video_ids, key)
            structured = _to_structured(video_items)
            structured.sort(key=lambda s: s["_view_count"], reverse=True)
            structured = structured[:max_results]
        else:
            # No channel identified at all — best-effort unscoped keyword search.
            search_params = {
                "part": "snippet",
                "type": "video",
                "maxResults": max_results,
                "order": "viewCount",
                "key": key,
            }
            if clean_query:
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
                print(f"[youtube.py] no video ids for query={query!r}")
                return None
            video_items = _videos_with_stats(video_ids, key)
            structured = _to_structured(video_items)

        structured = _dedupe_by_video_id(structured)
        for idx, s in enumerate(structured, start=1):
            # Make the ranking explicit in the content text itself — otherwise
            # the model has no way to know these were already sorted/filtered
            # to the top N by view count, and hedges unnecessarily even when
            # the data is correct and complete.
            s["content"] = f"Rank {idx} of {len(structured)} by view count. " + s["content"]
            s.pop("_video_id", None)
            s.pop("_view_count", None)

        return structured if structured else None
    except Exception as e:
        print(f"[youtube.py] search_youtube unexpected exception: {e}")
        return None