# digest_runner.py

import os
import requests

import db
import digest_sections as sections

SECTION_BUILDERS = {
    "job_questions": sections.build_job_questions,
    "ai_news": sections.build_ai_news,
    "ai_tool_launches": sections.build_ai_tool_launches,
    "movies": sections.build_movies,
    "youtube": sections.build_youtube,
    "gita_quote": sections.build_gita_quote,
    "world_trending_news": sections.build_world_trending_news,
}

SECTION_HEADERS = {
    "job_questions": "💼 Job Prep",
    "ai_news": "🤖 AI News",
    "ai_tool_launches": "🚀 New AI Tools",
    "movies": "🎬 Movies Today",
    "youtube": "📺 YouTube Pick",
    "gita_quote": "🕉️ Gita Quote",
    "world_trending_news": "🌍 World Trending",
}

# Sections where we run a "skip if unchanged from yesterday" delta check.
# The literal failure string below must never be treated as "unchanged" —
# otherwise a broken search on day 1 poisons yesterday's payload and
# silently suppresses the section (header included) on day 2 even once
# the search is fixed and returning real content.
DELTA_CHECKED_SECTIONS = ("ai_news", "ai_tool_launches", "world_trending_news", "youtube")
FAILURE_STRING = "Nothing found today."


# digest_runner.py

TELEGRAM_MAX_LEN = 4096

def send_telegram_message(chat_id, text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram rejects messages over 4096 chars outright (400 Bad Request).
    # Split on paragraph boundaries so we send multiple messages instead
    # of silently failing the whole digest.
    chunks = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > TELEGRAM_MAX_LEN:
            if current:
                chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)

    last_message_id = None
    for chunk in chunks:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if resp.status_code != 200:
            print(f"[digest_runner] telegram send failed: {resp.status_code} {resp.text}")
        resp.raise_for_status()
        last_message_id = resp.json()["result"]["message_id"]

    return last_message_id


def run_digest():
    configs = db.get_active_scheduled_queries()
    if not configs:
        print("[digest_runner] no active scheduled_queries")
        return

    for config in configs:
        config_id = config["id"]
        chat_id = config["telegram_chat_id"]
        enabled_sections = config.get("sections", {})
        yesterday = db.get_yesterday_payload(config_id) or {}

        payload = {}
        failures = []

        for key, enabled in enabled_sections.items():
            if not enabled or key not in SECTION_BUILDERS:
                continue
            try:
                result = SECTION_BUILDERS[key](config, config_id)

                # simple delta check: skip if identical to yesterday's content
                if key in DELTA_CHECKED_SECTIONS:
                    if result == FAILURE_STRING:
                        pass  # always show a failed/empty search, never suppress as "duplicate"
                    elif result == yesterday.get(key):
                        result = None  # genuinely unchanged content — skip

                payload[key] = result
            except Exception as e:
                print(f"[digest_runner] section '{key}' failed: {e}")
                failures.append(key)
                payload[key] = None

        # format message
        lines = []
        for key, header in SECTION_HEADERS.items():
            if key not in payload or not payload[key]:
                continue
            lines.append(f"<b>{header}</b>\n{payload[key]}")
        message_text = "\n\n".join(lines) if lines else "No updates today."

        status = "success"
        delivered = False
        message_id = None
        try:
            message_id = send_telegram_message(chat_id, message_text)
            delivered = True
        except Exception as e:
            print(f"[digest_runner] telegram send failed: {e}")
            status = "failed"

        if failures and status == "success":
            status = "partial"

        db.save_digest_run(config_id, payload, delivered=delivered, telegram_message_id=message_id)
        db.update_last_run(config_id, status=status)


if __name__ == "__main__":
    run_digest()
