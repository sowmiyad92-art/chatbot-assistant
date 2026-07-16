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


def _build_search_context(search_results):
    """Turn structured search results into a text block for the model prompt."""
    lines = []
    for r in search_results:
        lines.append(f"- {r['title']}: {r['content']}")
    return "\n".join(lines)


def get_response(messages, model=DEFAULT_MODEL, search_results=None):
    """
    messages: list of {"role": "user"/"assistant", "content": "..."}
    search_results: optional list of {"title","url","content"} from search.search_web

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
            "there instead:\n\n" + _build_search_context(search_results)
        )
    chat_messages = [{"role": "system", "content": system_content}] + messages
    # Lower temperature for grounded (search-backed) answers — reduces the
    # rambling/self-correcting behavior that shows up when the model has to
    # reconcile multiple sources at higher randomness. Ungrounded, more
    # conversational replies keep the higher temperature.
    temperature = 0.3 if search_results else 0.7
    completion = client.chat.completions.create(
        model=model,
        messages=chat_messages,
        temperature=temperature,
        max_tokens=700,       # hard cap — safety net against repetition-loop runaway output
        frequency_penalty=0.4,  # penalize repeated tokens/phrases, small models are prone to looping
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