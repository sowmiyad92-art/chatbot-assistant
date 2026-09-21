import calendar
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def get_api_key():
    try:
        import streamlit as st

        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


client = Groq(api_key=get_api_key())

DEFAULT_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = (
    "You are Aadsia, a personal AI assistant built by Sowmiya. Your name comes "
    "from 'Aadi' (Sanskrit/Tamil for primordial, first, the source) and 'sia' "
    "(a soft, flowing suffix) — together meaning roughly 'the primordial flow "
    "of intelligence.' You initiate and sustain the flow of information, the "
    "way Sowmiya's automation pipelines initiate and sustain data. Only "
    "mention this origin/meaning if the user directly asks about your name — "
    "don't bring it up unprompted. "
    "You are a helpful, friendly assistant. Give clear, concise answers. "
    "If you don't know something, say so honestly. "
    "Never include raw URLs or link text inline in your answer — sources are "
    "shown separately to the user, so just write the answer in plain prose. "
    "Only claim to have searched, looked up, or found something live on the "
    "web if real search results were actually provided to you this turn "
    "(see below) — if none were provided, answer from your own general "
    "knowledge and don't imply you performed a live lookup you didn't do."
)


CLASSIFIER_MODEL = (
    "openai/gpt-oss-20b"  # cheapest/fastest — this call should cost almost nothing
)

CLASSIFIER_PROMPT = (
    "You decide if a user question needs a live web search to answer well, or if "
    "it can be answered from general knowledge alone.\n\n"
    "Answer YES if the question is about: current events, recent news, today's/this "
    "week's/this month's data, live prices or scores, current weather, who currently "
    "holds a role or position, anything time-sensitive, or anything explicitly about "
    "'latest', 'current', 'recent', 'today', 'now'.\n\n"
    "Also answer YES if the user is asking for a real link, URL, video, or specific "
    "resource — e.g. 'give me a YouTube link', 'find a video', 'send me the article', "
    "'search for', 'look up' — since these require real search results, not "
    "general knowledge.\n\n"
    "Answer NO if the question is: general knowledge, how-to/coding help, creative "
    "writing, math, casual conversation, explanations of stable concepts, or anything "
    "not tied to real-time information or a real link/resource request.\n\n"
    "Respond with exactly one word: YES or NO. Nothing else."
)


def needs_search(query):
    """
    Cheap classifier call to decide if a query needs live web search.
    Returns True/False. Defaults to False (no search) if the call fails,
    since that's the safer/cheaper failure mode for your Tavily quota.
    """
    try:
        completion = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=50,
            reasoning_effort="low",
        )
        answer = completion.choices[0].message.content.strip().upper()
        return answer.startswith("YES")
    except Exception:
        return False


def _build_search_context(search_results, max_chars=None):
    """Turn structured search results into a text block for the model prompt.
    max_chars, if set, further truncates each result's content — used for
    the trimmed retry when a request comes back too large for the TPM limit.
    """
    lines = []
    for r in search_results:
        content = r["content"][:max_chars] if max_chars else r["content"]
        lines.append(f"- {r['title']}: {content}")
    return "\n".join(lines)


def _timeframe_range(query, today):
    q = query.lower()
    if "today" in q:
        return "today", today, today
    if "next month" in q:
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        start = today.replace(year=year, month=month, day=1)
        end = start.replace(day=calendar.monthrange(year, month)[1])
        return "next month", start, end
    if "this month" in q:
        start = today.replace(day=1)
        end = today.replace(
            day=calendar.monthrange(today.year, today.month)[1]
        )
        return "this month", start, end
    if "this week" in q:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return "this week", start, end
    if "this year" in q:
        return (
            "this year",
            today.replace(month=1, day=1),
            today.replace(month=12, day=31),
        )
    return None


def _build_system_content(
    search_results, max_chars=None, search_attempted=False, latest_query=None
):
    system_content = SYSTEM_PROMPT
    if search_results:
        today = datetime.now(timezone.utc).date()
        today_str = today.isoformat()
        timeframe_note = ""
        tf = _timeframe_range(latest_query, today) if latest_query else None
        if tf:
            label, start, end = tf
            timeframe_note = (
                f" The user's question is scoped to '{label}', which for "
                f"today's date is exactly the range {start.isoformat()} to "
                f"{end.isoformat()} — use these two dates directly, don't "
                f"re-derive what '{label}' means yourself. For each search "
                f"result, compare its date to this range: is it on or after "
                f"{start.isoformat()} AND on or before {end.isoformat()}? If "
                f"not, exclude that result or clearly say it falls outside "
                f"the requested {label}."
            )
        system_content += (
            f"\n\nToday's actual date is {today_str}.{timeframe_note} When the "
            "user's question is scoped to any timeframe not covered by an "
            "exact range above, check each search result's publish/event date "
            "against that timeframe before including it. If a result's date "
            "clearly falls outside the window the user asked about, do not "
            "present it as if it fits — either leave it out or say plainly "
            "that it's from a different period than requested. "
            "\n\nYou have been given the following up-to-date web search results. "
            "Use them to answer the user's latest question if relevant, and mention "
            "that this reflects current web information. Do not quote URLs — just "
            "use the information. Do not say you are unable to provide links or "
            "URLs, and do not tell the user to search for the title themselves — "
            "the actual source links are already shown to the user separately "
            "below your answer, so present each result directly and naturally "
            "(e.g. 'Here's a video: [title] by [channel/author]') as if you are "
            "handing them the resource, not suggesting they go look it up. "
            "CRITICAL: only reference titles, names, view counts, and facts that "
            "literally appear in the search results below — "
            "Search results may contain non-English text (Chinese, Korean, "
            "etc.) — this is normal and expected. Read and extract facts "
            "from them the same as English text: dates, titles, and "
            "announcements in Chinese or Korean are just as valid a source "
            "as English ones. Do not skip or discount a result just because "
            "it's not in English — translate the relevant fact into your "
            "answer. "
            "never invent, "
            "paraphrase-into-a-new-title, or guess a plausible-sounding "
            "alternative that isn't actually there. If the search results don't "
            "contain something the user asked for, say so honestly instead of "
            "making up a substitute. "
            "Before concluding a result doesn't contain what's asked, read "
            "the ENTIRE title and content of each result carefully — the "
            "answer is often in the title itself (e.g. a listicle title "
            "naming a few examples), not spelled out sentence by sentence. "
            "If a result's title or content mentions specific names, titles, "
            "or items relevant to the question, extract and use them even "
            "if the rest of that result's content is generic or repetitive. "
            "Only say nothing was found if you have genuinely checked every "
            "result's title and content and none of them name anything "
            "relevant. "
            "If a search result contains an exact "
            "number (view count, subscriber count, date, etc.), state that "
            "exact number directly — never say it's 'high', 'unable to "
            "determine', or 'not mentioned' when the number is actually "
            "present in the result. "
            "present the result directly and confidently, but state once, briefly, "
            "that the ranking is among the videos retrieved, not the channel's "
            "full catalog. If a result's content includes text like "
            "'Rank N of M by view count', that ranking was already computed "
            "and verified before reaching you — present it as-is, with "
            "confidence, and do not undercut it with unnecessary caveats. "
            "If the search results contain more than one distinct ranked list "
            "for the same topic (e.g. different sources ranking by different "
            "criteria), do not merge them into one list. Pick the single most "
            "specific and directly relevant list (prefer one with explicit "
            "numeric rankings/scores over a vague 'buzzworthy' or 'notable' "
            "mention) and present only that one, noting which ranking it's "
            "from if useful. "
            "If any single item's exact position is ambiguous or contradicted "
            "across sources, write that one item as 'position unclear from "
            "available sources' and move on immediately — do not attempt to "
            "re-derive, debate, or re-explain that item's ranking. Write each "
            "list item exactly once, in one sentence, then stop. Never repeat "
            "a list item, a phrase, or a sentence — if you notice yourself "
            "about to restate something you already wrote, stop the answer "
            "there instead. "
            "If the user asked for a specific number of items (top 5, top 10, "
            "etc.) but the search results only actually support fewer distinct, "
            "verifiable items, list only the ones truly supported and say "
            "plainly that fewer were found than requested. NEVER invent an "
            "additional item — a title, cast member, date, or anything else — "
            "just to pad the list up to the requested count:\n\n"
            + _build_search_context(search_results, max_chars)
        )
    elif search_attempted:
        system_content += (
            "\n\n[Internal note, not for the user: a live search was "
            "attempted but returned no usable results.] You do NOT have any "
            "real search data for this turn — none at all. Do not say 'I "
            "found', 'I've searched and found', or invent any titles, "
            "channels, view counts, or other facts. Tell the user naturally "
            "that no results were found for that query and suggest they "
            "check the spelling/name or try rephrasing — but do NOT quote or "
            "paraphrase this note itself or reference 'this turn' as a phrase."
        )
    else:
        system_content += (
            "\n\n[Internal note, not for the user: no live search ran this "
            "turn.] If the user's question requires specific, verifiable "
            "real-time data (exact view counts, current rankings, today's "
            "news, precise statistics, etc.) that you cannot actually know "
            "from training, tell them naturally that you don't have that "
            "specific number/detail on hand and it would need a live search "
            "— do not invent precise-sounding numbers, titles, or facts to "
            "sound authoritative. Do NOT quote, paraphrase, or reference "
            "this note itself, the phrase 'this turn', or the fact that a "
            "search was or wasn't performed — that's internal bookkeeping, "
            "not something to say out loud."
        )
    return system_content


_STOP = {
    "Here",
    "The",
    "This",
    "That",
    "Their",
    "There",
    "These",
    "Those",
    "However",
    "Note",
    "Sorry",
}


def _norm(s):
    for ch in "\u2010\u2011\u2012\u2013\u2014":
        s = s.replace(ch, "-")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _match_facts(text, search_results, latest_query=None):
    """Check numbers and names in the answer against the source text.
    Returns {"matched": n, "total": m} or None if there is nothing to check.
    """
    if not search_results:
        return None
    today = datetime.now(timezone.utc).date()
    text = _norm(text).replace(today.isoformat(), "")

    tf = _timeframe_range(latest_query, today) if latest_query else None
    if tf:
        for d in (tf[1], tf[2]):
            text = text.replace(d.isoformat(), "")

    facts = set()
    for m in re.findall(r"\d{4}-\d{2}-\d{2}", text):
        facts.add(m)
    for m in re.findall(r"\b\d[\d,]*(?:\.\d+)?%?", text):
        n = m.replace(",", "")
        if len(n.rstrip("%")) >= 3 or "%" in n or "." in n:
            facts.add(n)
    for n, u in re.findall(
        r"\b(\d{1,2})\s+(years?|days?|episodes?|seasons?|weeks?|months?)\b", text
    ):
        facts.add(f"{n} {u.rstrip('s')}")
    for m in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text):
        words = m.split()
        while words and words[0] in _STOP:
            words.pop(0)
        if len(words) >= 2:
            facts.add(" ".join(words).lower())
    if not facts:
        return None
    src = (
        _norm(" ".join(f"{r['title']} {r['content']}" for r in search_results))
        .lower()
        .replace(",", "")
    )
    matched = sum(1 for f in facts if f in src)
    return {"matched": matched, "total": len(facts)}


_QSTOP = {
    "search",
    "youtube",
    "video",
    "videos",
    "show",
    "find",
    "give",
    "tell",
    "about",
    "what",
    "which",
    "best",
    "top",
    "most",
    "that",
    "this",
    "with",
    "from",
    "your",
    "their",
    "how",
    "make",
    "latest",
    "today",
    "week",
    "month",
    "viewed",
    "watched",
    "views",
}


def _relevant(query, search_results):
    if not query or not search_results:
        return True
    words = {
        w
        for w in re.findall(r"[a-z]{4,}", _norm(query).lower())
        if w not in _QSTOP
    }
    if not words:
        return True
    src = _norm(
        " ".join(f"{r['title']} {r['content']}" for r in search_results)
    ).lower()
    return sum(1 for w in words if w in src) / len(words) >= 0.5


def get_response(
    messages,
    model=DEFAULT_MODEL,
    search_results=None,
    search_attempted=False,
):
    latest_query = None
    for m in reversed(messages):
        if m.get("role") == "user":
            latest_query = m.get("content")
            break

    system_content = _build_system_content(
        search_results,
        search_attempted=search_attempted,
        latest_query=latest_query,
    )
    chat_messages = [{"role": "system", "content": system_content}] + messages

    temperature = 0.3 if search_results else 0.7

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=2000,
            reasoning_effort="low",
            frequency_penalty=0.4,
        )
    except Exception as e:
        err = str(e)
        if "Tool choice is none, but model called a tool" in err:
            return {
                "text": (
                    "I don't have access to any customer data, so I can't "
                    "answer that. I can help with general knowledge and web questions."
                ),
                "sources": None,
                "status": "NONE",
                "model": model,
            }
        too_large = (
            "413" in err
            or "rate_limit_exceeded" in err
            or "tokens per minute" in err.lower()
            or "request too large" in err.lower()
        )
        if not too_large:
            raise
        print(
            f"[llm.py] request too large, retrying with trimmed context: {err[:200]}"
        )
        trimmed_system = _build_system_content(
            search_results, max_chars=150, latest_query=latest_query
        )
        chat_messages = [
            {"role": "system", "content": trimmed_system}
        ] + messages[-4:]
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=chat_messages,
                temperature=temperature,
                max_tokens=500,
                frequency_penalty=0.4,
            )
        except Exception as retry_err:
            print(
                f"[llm.py] trimmed retry also failed: {str(retry_err)[:200]}"
            )
            return {
                "text": "I hit an API limit and couldn't recover even after trimming context — please try again with a narrower question.",
                "sources": search_results,
                "status": "LIMITED",
                "error": True,
                "model": model,
            }

    text = completion.choices[0].message.content

    if not text or not text.strip():
        text = "I retrieved search results but couldn't generate a written summary — please try rephrasing or asking again."

    _NO_USEFUL_DATA_PHRASES = [
        "don't have any fresh search results",
        "don't have any search results",
        "no results found",
        "couldn't find any",
        "couldn't locate any",
        "i'm not able to tell you",
        "i'm not finding any",
        "no fresh search results",
        "i'm sorry",
        "do not contain",
        "do not include",
        "does not contain",
        "none of the search results",
        "not present in the data",
    ]
    model_found_nothing_useful = search_results and any(
        phrase in text.lower().replace("\u2019", "'")
        for phrase in _NO_USEFUL_DATA_PHRASES
    )

    match = _match_facts(text, search_results, latest_query)
    ratio_ok = (
        match is not None
        and match["total"] >= 2
        and match["matched"] / match["total"] >= 0.75
    )
    ratio_ok = ratio_ok and _relevant(latest_query, search_results)

    if not search_results:
        status = "NONE"
    elif model_found_nothing_useful:
        status = "LIMITED"
    elif len(search_results) >= 2 and ratio_ok:
        status = "VERIFIED"
    else:
        status = "LIMITED"

    return {
        "text": text,
        "sources": search_results,
        "status": status,
        "model": model,
        "match": match,
    }
