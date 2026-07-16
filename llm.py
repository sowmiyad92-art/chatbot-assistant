import os
from groq import Groq
from dotenv import load_dotenv

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

DEFAULT_MODEL = "llama-3.1-8b-instant"

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
    "shown separately to the user, so just write the answer in plain prose."
)


CLASSIFIER_MODEL = "llama-3.1-8b-instant"  # cheapest/fastest — this call should cost almost nothing

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
            max_tokens=3,
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


def _build_system_content(search_results, max_chars=None, search_attempted=False):
    system_content = SYSTEM_PROMPT
    if search_results:
        system_content += (
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
            "literally appear in the search results below — never invent, "
            "paraphrase-into-a-new-title, or guess a plausible-sounding "
            "alternative that isn't actually there. If the search results don't "
            "contain something the user asked for, say so honestly instead of "
            "making up a substitute. If a search result contains an exact "
            "number (view count, subscriber count, date, etc.), state that "
            "exact number directly — never say it's 'high', 'unable to "
            "determine', or 'not mentioned' when the number is actually "
            "present in the result. "
            "present the result directly and confidently — do not add hedges "
            "like 'I don't have information about their most-watched videos "
            "in general' or similar disclaimers when the results already "
            "answer the question. If a result's content includes text like "
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
            "there instead:\n\n" + _build_search_context(search_results, max_chars)
        )
    elif search_attempted:
        # A search was actually run (YouTube API, Exa, or Tavily) but came
        # back with nothing usable. Without this, the model has no idea a
        # search even happened and will improvise a plausible-sounding
        # answer as if it searched — exactly the hallucination-with-no-data
        # failure this whole grounding system exists to prevent.
        system_content += (
            "\n\nA live search was attempted for this request but returned no "
            "usable results. You do NOT have any real search data for this "
            "turn — none at all. Do not say 'I found', 'I've searched and "
            "found', or invent any titles, channels, view counts, or other "
            "facts. Tell the user plainly that no results were found for "
            "that query and suggest they check the spelling/name or try "
            "rephrasing."
        )
    return system_content


def get_response(messages, model=DEFAULT_MODEL, search_results=None, search_attempted=False):
    """
    messages: list of {"role": "user"/"assistant", "content": "..."}
    search_results: optional list of {"title","url","content"} from search.search_web
    search_attempted: pass True whenever search_web() was actually called this
        turn, regardless of whether it returned results. Lets the model know
        the difference between "search wasn't needed" and "search ran and
        found nothing" — without it, an empty search silently falls back to
        the model improvising an answer as if it had real data.

    Returns a dict:
        {
            "text": str,              # the answer, no inline URLs
            "sources": list | None,   # the raw search_results passed in, for the UI panel
            "status": "VERIFIED" | "LIMITED" | "NONE",
            "model": str,
        }
    Status is a simple source-count heuristic — swap in a real confidence
    check later (e.g. did the model's claims actually match source content).
    """
    system_content = _build_system_content(search_results, search_attempted=search_attempted)
    chat_messages = [{"role": "system", "content": system_content}] + messages
    # Lower temperature for grounded (search-backed) answers — reduces the
    # rambling/self-correcting behavior that shows up when the model has to
    # reconcile multiple sources at higher randomness. Ungrounded, more
    # conversational replies keep the higher temperature.
    temperature = 0.3 if search_results else 0.7
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=700,       # hard cap — safety net against repetition-loop runaway output
            frequency_penalty=0.4,  # penalize repeated tokens/phrases, small models are prone to looping
        )
    except Exception as e:
        err = str(e)
        too_large = search_results and (
            "413" in err or "rate_limit_exceeded" in err
            or "tokens per minute" in err.lower() or "request too large" in err.lower()
        )
        if not too_large:
            raise
        # Request exceeded the TPM limit — retry once with heavily trimmed
        # source content instead of surfacing a raw API error to the user.
        print(f"[llm.py] request too large, retrying with trimmed context: {err[:200]}")
        trimmed_system = _build_system_content(search_results, max_chars=150)
        chat_messages = [{"role": "system", "content": trimmed_system}] + messages
        completion = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=500,
            frequency_penalty=0.4,
        )
    text = completion.choices[0].message.content

    if not search_results:
        status = "NONE"
    elif len(search_results) >= 2:
        status = "VERIFIED"
    else:
        status = "LIMITED"

    return {
        "text": text,
        "sources": search_results,
        "status": status,
        "model": model,
    }