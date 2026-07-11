import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def get_api_key():
    # Try Streamlit Cloud secrets first (only available when deployed)
    try:
        import streamlit as st
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    # Fall back to local .env / environment variable
    return os.environ.get("GROQ_API_KEY")


client = Groq(api_key=get_api_key())

DEFAULT_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = (
    "You are a helpful, friendly assistant. Give clear, concise answers. "
    "If you don't know something, say so honestly."
)


def get_response(messages, model=DEFAULT_MODEL, search_context=None):
    """
    messages: list of {"role": "user"/"assistant", "content": "..."}
    search_context: optional string of fresh web search results to ground the answer
    Returns the assistant's reply as a string.
    """
    system_content = SYSTEM_PROMPT
    if search_context:
        system_content += (
            "\n\nYou have been given the following up-to-date web search results. "
            "Use them to answer the user's latest question if relevant, and mention "
            "that this reflects current web information:\n\n" + search_context
        )
    chat_messages = [{"role": "system", "content": system_content}] + messages
    completion = client.chat.completions.create(
        model=model,
        messages=chat_messages,
        temperature=0.7,
    )
    return completion.choices[0].message.content