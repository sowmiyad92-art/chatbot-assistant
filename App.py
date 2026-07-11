import streamlit as st
import db
import llm
import search

st.set_page_config(page_title="Assistant", page_icon="●", layout="wide")

db.init_db()

# ---------- Custom CSS: design system ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap');

:root {
    --bg: #14181F;
    --bg-sidebar: #1A1F29;
    --bg-input: #1F2530;
    --text: #F5F1E8;
    --text-dim: #A8ADB8;
    --accent-assistant: #6FA8AF;
    --accent-user: #E08A4F;
    --border: #333B4A;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    color: var(--text) !important;
}

.stApp {
    background-color: var(--bg);
}

/* Theme Streamlit's own chrome: header bar + bottom input container */
/* Wildcard-match testids since exact names shift between Streamlit versions */
header, [data-testid*="Header"] {
    background-color: var(--bg) !important;
    border-bottom: 1px solid var(--border);
}
[data-testid*="Bottom"], [class*="bottom"], .stChatInput, [data-testid*="ChatInput"] {
    background-color: var(--bg) !important;
}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: var(--bg) !important;
}
textarea, [data-testid*="ChatInput"] textarea, [class*="stChatInput"] textarea {
    background-color: var(--bg-input) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}
textarea::placeholder {
    color: var(--text-dim) !important;
}
/* Catch-all: any div sitting at the bottom input row */
div:has(> div > textarea) {
    background-color: var(--bg) !important;
}

section[data-testid="stSidebar"] {
    background-color: var(--bg-sidebar);
    border-right: 1px solid var(--border);
}

h1, h2, h3, p, span, label, li, ol, ul, .stCaption, div[data-testid="stCaptionContainer"] {
    color: var(--text) !important;
}

h1, h2, h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    letter-spacing: -0.02em;
}

div[data-testid="stCaptionContainer"] {
    color: var(--text-dim) !important;
}

/* Session list styling */
.session-item {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: var(--text-dim);
    cursor: pointer;
}
.session-item.active {
    color: var(--text) !important;
    font-weight: 500;
}
.session-item.active::before {
    content: "● ";
    color: var(--accent-assistant);
}

/* Chat message styling - "stitched note" signature */
.stChatMessage {
    background: transparent !important;
    border-radius: 0 !important;
    padding-left: 14px !important;
    margin-bottom: 4px;
}

div[data-testid="stChatMessageContent"] {
    font-family: 'Inter', sans-serif;
}

/* User message: ember left border */
.stChatMessage:has(div[data-testid="stChatMessageAvatarUser"]) {
    border-left: 2px solid var(--accent-user);
}

/* Assistant message: teal left border */
.stChatMessage:has(div[data-testid="stChatMessageAvatarAssistant"]) {
    border-left: 2px solid var(--accent-assistant);
}

.timestamp {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    margin-top: -6px;
    margin-bottom: 8px;
    margin-left: 14px;
}

/* New chat button (primary, first button in sidebar) */
section[data-testid="stSidebar"] .stButton:first-of-type button {
    font-family: 'Space Grotesk', sans-serif;
    background-color: var(--accent-assistant);
    color: var(--bg);
    border: none;
    border-radius: 4px;
    font-weight: 700;
}

/* Session list buttons: look like plain text rows, not buttons */
section[data-testid="stSidebar"] .stButton button {
    background-color: transparent !important;
    color: var(--text-dim) !important;
    border: none !important;
    text-align: left !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 400 !important;
    padding: 8px 4px !important;
    border-bottom: 1px solid var(--border) !important;
    border-radius: 0 !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    color: var(--text) !important;
    background-color: rgba(255,255,255,0.03) !important;
}
</style>
""", unsafe_allow_html=True)

# ---------- Sidebar: real session list ----------
if "current_session_id" not in st.session_state:
    sessions = db.get_sessions()
    if sessions:
        st.session_state.current_session_id = sessions[0]["id"]
    else:
        st.session_state.current_session_id = db.create_session("New chat")

with st.sidebar:
    st.markdown("### Sessions")
    if st.button("+ New chat", use_container_width=True):
        new_id = db.create_session("New chat")
        st.session_state.current_session_id = new_id
        st.rerun()

    sessions = db.get_sessions()
    for s in sessions:
        active = " active" if s["id"] == st.session_state.current_session_id else ""
        col1, col2 = st.columns([5, 1])
        with col1:
            if st.button(s["name"], key=f"session_{s['id']}", use_container_width=True):
                st.session_state.current_session_id = s["id"]
                st.rerun()
        with col2:
            if st.button("🗑", key=f"del_{s['id']}"):
                db.delete_session(s["id"])
                remaining = db.get_sessions()
                if remaining:
                    st.session_state.current_session_id = remaining[0]["id"]
                else:
                    st.session_state.current_session_id = db.create_session("New chat")
                st.rerun()

    st.markdown("---")
    st.markdown("### Model")
    selected_model = st.selectbox(
        "Choose model",
        options=["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
        index=0,
        label_visibility="collapsed",
    )
    st.session_state.selected_model = selected_model

    st.markdown("---")
    web_search_enabled = st.checkbox("🔍 Enable web search", value=False)
    st.session_state.web_search_enabled = web_search_enabled

# ---------- Main chat area ----------
st.markdown("## Assistant")
st.caption("Multi-turn chatbot — Groq + Supabase persistence, multiple named sessions, live web search.")

session_id = st.session_state.current_session_id
history = db.get_session_messages(session_id)

if not history:
    st.info("No messages yet — say hello to start this session.")

for msg in history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Type a message..."):
    # Auto-name session from first message
    if not history:
        db.update_session_name_from_first_message(session_id, prompt)

    db.save_message(session_id, "user", prompt)
    with st.chat_message("user"):
        st.write(prompt)

    # Build full history for context
    full_history = db.get_session_messages(session_id)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in full_history]

    with st.chat_message("assistant"):
        search_context = None
        if st.session_state.get("web_search_enabled"):
            with st.spinner("Searching the web..."):
                search_context = search.search_web(prompt)
        with st.spinner("Thinking..."):
            try:
                reply = llm.get_response(
                    api_messages,
                    model=st.session_state.selected_model,
                    search_context=search_context,
                )
            except Exception as e:
                reply = f"⚠️ Error calling Groq API: {e}"
        st.write(reply)

    db.save_message(session_id, "assistant", reply)
    st.rerun()