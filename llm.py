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
    "Answer NO if the question is: general knowledge, how-to/coding help, creative "
    "writing, math, casual conversation, explanations of stable concepts, or anything "
    "not tied to real-time information.\n\n"
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
            "use the information:\n\n" + _build_search_context(search_results)
        )
    chat_messages = [{"role": "system", "content": system_content}] + messages
    completion = client.chat.completions.create(
        model=model,
        messages=chat_messages,
        temperature=0.7,
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