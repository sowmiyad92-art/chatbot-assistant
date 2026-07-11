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


def get_response(messages, model=DEFAULT_MODEL):
    """
    messages: list of {"role": "user"/"assistant", "content": "..."}
    Returns the assistant's reply as a string.
    """
    chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    completion = client.chat.completions.create(
        model=model,
        messages=chat_messages,
        temperature=0.7,
    )
    return completion.choices[0].message.content