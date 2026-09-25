DELTA_SECTIONS = ["movies", "ai_news", "ai_tool_launches", "world_trending_news"]

def _lines_to_set(text):
    if not text:
        return set()
    return {line.strip("- ").strip() for line in text.split("\n") if line.strip()}

def compute_deltas(current_payload, last_payload):
    if not last_payload:
        return current_payload

    deltas = dict(current_payload)

    for section in DELTA_SECTIONS:
        current_text = current_payload.get(section, "") or ""
        last_text = last_payload.get(section, "") or ""

        # Movies has a header line before the list — skip it when diffing
        current_header = ""
        if section == "movies" and "\n" in current_text:
            current_header, current_text = current_text.split("\n", 1)

        current_items = _lines_to_set(current_text)
        last_items = _lines_to_set(last_text.split("\n", 1)[-1] if section == "movies" else last_text)
        new_items = current_items - last_items

        if new_items:
            body = "\n".join(f"- {item}" for item in sorted(new_items))
            deltas[section] = f"{current_header}\n{body}" if current_header else body
        else:
            deltas[section] = "Nothing new today."

    return deltas
