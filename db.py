import os
import json
from datetime import datetime, timezone, timedelta

from supabase import create_client


def get_supabase_credentials():
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if url and key:
            return url, key
    except Exception:
        pass
    return os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")


_url, _key = get_supabase_credentials()
if not _url or not _key:
    raise RuntimeError(
        "Missing SUPABASE_URL / SUPABASE_KEY. Add them to .streamlit/secrets.toml "
        "locally, or to your app's Secrets in Streamlit Cloud settings."
    )

supabase = create_client(_url, _key)


def init_db():
    """
    No-op: Supabase tables are created once via the SQL editor, not at runtime
    (the anon/service key used here doesn't have DDL permission, and shouldn't).
    Run these once in your Supabase project's SQL editor before first use:

    create table sessions (
        id bigint generated always as identity primary key,
        name text not null,
        created_at timestamptz not null default now()
    );

    create table messages (
        id bigint generated always as identity primary key,
        session_id bigint not null references sessions(id) on delete cascade,
        role text not null,
        content text not null,
        timestamp timestamptz not null default now(),
        meta jsonb
    );

    create table search_log (
        id bigint generated always as identity primary key,
        provider text not null,
        timestamp timestamptz not null default now()
    );
    """
    pass


def create_session(name="New chat"):
    result = supabase.table("sessions").insert({
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return result.data[0]["id"]


def get_sessions():
    result = supabase.table("sessions").select("*").order("id", desc=True).execute()
    return result.data


def get_session_messages(session_id):
    result = (
        supabase.table("messages")
        .select("*")
        .eq("session_id", session_id)
        .order("id", desc=False)
        .execute()
    )
    return result.data


def save_message(session_id, role, content, meta=None):
    """
    meta: optional dict, e.g. {"status": "VERIFIED", "sources": [...], "model": "..."}
    Stored directly in the jsonb column — no manual json.dumps needed, unlike
    the old sqlite version, since Supabase handles jsonb natively.
    """
    supabase.table("messages").insert({
        "session_id": session_id,
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
    }).execute()


def get_message_meta(msg_row):
    """
    Parse the meta column back into a dict, or None.
    Supabase's client usually already returns jsonb as a parsed dict, but this
    handles the case where it comes back as a JSON string too, just in case.
    """
    meta = msg_row.get("meta")
    if meta is None:
        return None
    if isinstance(meta, dict):
        return meta
    try:
        return json.loads(meta)
    except (TypeError, ValueError):
        return None


def rename_session(session_id, new_name):
    supabase.table("sessions").update({"name": new_name}).eq("id", session_id).execute()


def delete_session(session_id):
    # messages are deleted automatically via "on delete cascade" in the schema above
    supabase.table("sessions").delete().eq("id", session_id).execute()


def update_session_name_from_first_message(session_id, content):
    """Auto-name a session using the first ~40 chars of the first user message."""
    short_name = content.strip()[:40]
    if len(content.strip()) > 40:
        short_name += "..."
    rename_session(session_id, short_name)


def log_search_usage(provider):
    """
    Records one search call for usage tracking (Exa vs Tavily, monthly totals).
    Call this once per successful search_web() call, right after you get a
    provider back (skip logging when provider is None — nothing succeeded).
    """
    if not provider:
        return
    supabase.table("search_log").insert({
        "provider": provider,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }).execute()


def get_search_usage_stats(months_back=6):
    """
    Returns:
        {
            "Exa":    {"total": int, "by_month": {"2026-07": int, ...}},
            "Tavily": {"total": int, "by_month": {"2026-07": int, ...}},
        }
    "total" is all-time, computed with a cheap count-only query (no rows
    transferred). "by_month" covers the last `months_back` months, fetched
    and aggregated in Python — fine at personal-app volume. If search_log
    grows large, swap this for a Postgres view/RPC instead.
    """
    stats = {}
    for provider in ("Exa", "Tavily"):
        count_result = (
            supabase.table("search_log")
            .select("id", count="exact")
            .eq("provider", provider)
            .execute()
        )
        stats[provider] = {"total": count_result.count or 0, "by_month": {}}

    cutoff = datetime.now(timezone.utc) - timedelta(days=31 * months_back)
    rows = (
        supabase.table("search_log")
        .select("provider, timestamp")
        .gte("timestamp", cutoff.isoformat())
        .execute()
        .data
    )
    for row in rows:
        provider = row["provider"]
        if provider not in stats:
            stats[provider] = {"total": 0, "by_month": {}}
        month_key = row["timestamp"][:7]  # "YYYY-MM"
        stats[provider]["by_month"][month_key] = stats[provider]["by_month"].get(month_key, 0) + 1

    return stats

def get_active_scheduled_queries():
    """Fetch all active digest configs to run today."""
    res = supabase.table("scheduled_queries").select("*").eq("active", True).execute()
    return res.data

def save_digest_run(scheduled_query_id, payload, delivered=False, telegram_message_id=None):
    """Log one full digest run (all sections in payload jsonb)."""
    result = supabase.table("digest_runs").insert({
        "scheduled_query_id": scheduled_query_id,
        "payload": payload,          # e.g. {"ai_news": "...", "youtube": {...}, ...}
        "delivered": delivered,
        "telegram_message_id": telegram_message_id,
    }).execute()
    return result.data[0]["id"]


def get_last_digest_run():
    """Fetch the most recent digest run's payload, for delta comparison."""
    result = (
        supabase.table("digest_runs")
        .select("payload, run_at")
        .order("run_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["payload"]
    return None


def update_last_run(scheduled_query_id, status="success"):
    """Update scheduled_queries pointer after a run."""
    supabase.table("scheduled_queries").update({
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "last_status": status,
    }).eq("id", scheduled_query_id).execute()


def get_yesterday_payload(scheduled_query_id):
    """Most recent prior run's payload, for delta comparison."""
    res = (
        supabase.table("digest_runs")
        .select("payload")
        .eq("scheduled_query_id", scheduled_query_id)
        .order("run_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["payload"] if res.data else None
    
    def get_top_queries(limit=15):
    """
    Returns the most frequently asked user queries across all sessions,
    for the sidebar quick-query panel. Fetched and aggregated in Python —
    fine at personal-app volume. If messages grows large, swap for a
    Postgres view/RPC instead (same tradeoff noted in get_search_usage_stats).
    """
    rows = (
        supabase.table("messages")
        .select("content")
        .eq("role", "user")
        .execute()
        .data
    )
    counts = {}
    for row in rows:
        text = row["content"].strip()
        if text:
            counts[text] = counts.get(text, 0) + 1

    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"query": q, "count": c} for q, c in top]
