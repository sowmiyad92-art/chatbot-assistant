DELTA_SECTIONS = ["movies", "ai_news", "ai_tool_launches", "world_trending_news"]

def _lines_to_set(text):
    if not text:
        return set()
    return {line.strip("- ").strip() for line in text.split("\n") if line.strip()}

def compute_deltas(current_payload, last_payload):
    """
    Returns current_payload with delta-sections replaced by only new items.
    Non-delta sections (youtube, gita_quote, job_questions) pass through unchanged.
    """
    if not last_payload:
        return current_payload  # first run ever, nothing to diff against

    deltas = dict(current_payload)

    for section in DELTA_SECTIONS:
        current_items = _lines_to_set(current_payload.get(section, ""))
        last_items = _lines_to_set(last_payload.get(section, ""))
        new_items = current_items - last_items

        if new_items:
            deltas[section] = "\n".join(f"- {item}" for item in sorted(new_items))
        else:
            deltas[section] = "Nothing new today."

    return deltas
