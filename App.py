import streamlit as st
import db
import llm
import search

st.set_page_config(page_title="Aadsia", page_icon="◆", layout="wide")

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

.stApp { background-color: var(--bg); }

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
textarea::placeholder { color: var(--text-dim) !important; }
div:has(> div > textarea) { background-color: var(--bg) !important; }

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
div[data-testid="stCaptionContainer"] { color: var(--text-dim) !important; }

.session-item {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: var(--text-dim);
    cursor: pointer;
}
.session-item.active { color: var(--text) !important; font-weight: 500; }
.session-item.active::before { content: "◆ "; color: var(--accent-assistant); }

.stChatMessage {
    background: transparent !important;
    border-radius: 0 !important;
    padding-left: 14px !important;
    margin-bottom: 4px;
}
div[data-testid="stChatMessageContent"] { font-family: 'Inter', sans-serif; }

.stChatMessage:has(div[data-testid="stChatMessageAvatarUser"]) {
    border-left: 2px solid var(--accent-user);
}
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

/* Model badge pill */
.model-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2px 10px;
    margin-left: 14px;
    margin-bottom: 10px;
    cursor: help;
}

/* Copy button */
.copy-btn {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 8px;
    margin-left: 14px;
    cursor: pointer;
}
.copy-btn:hover { color: var(--text); border-color: var(--accent-assistant); }

/* Status flags */
.status-verified {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #6FAF7A;
    margin-left: 14px;
}
.status-verified::before { content: "● "; }
.status-limited {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #D9A441;
    margin-left: 14px;
}
.status-limited::before { content: "● "; }

section[data-testid="stSidebar"] .stButton:first-of-type button {
    font-family: 'Space Grotesk', sans-serif;
    background-color: var(--accent-assistant);
    color: var(--bg);
    border: none;
    border-radius: 4px;
    font-weight: 700;
}
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

# ---------- Avatars ----------
# NOTE: st.chat_message(avatar=...) is unreliable across Streamlit versions —
# it validates against emoji ranges and can crash on both geometric shapes (●/◆)
# AND standard emoji depending on the Streamlit/Python build (confirmed crash on
# python3.14 here). Safest fix: don't use avatar= at all. Render our own marker
# as plain markdown text instead — same visual result, no validation risk.
AVATAR_USER = "●"
AVATAR_ASSISTANT = "◆"

# ---------- Sidebar: sessions + settings ----------
if "current_session_id" not in st.session_state:
    sessions = db.get_sessions()
    if sessions:
        st.session_state.current_session_id = sessions[0]["id"]
    else:
        st.session_state.current_session_id = db.create_session("New chat")

if "show_subtitle" not in st.session_state:
    st.session_state.show_subtitle = False   # hidden by default per your call
if "show_full_model_name" not in st.session_state:
    st.session_state.show_full_model_name = False  # hidden by default, badge shows short form

with st.sidebar:
    st.markdown("### Sessions")
    if st.button("+ New chat", use_container_width=True):
        new_id = db.create_session("New chat")
        st.session_state.current_session_id = new_id
        st.rerun()

    sessions = db.get_sessions()
    for s in sessions:
        col1, col2 = st.columns([5, 1])
        with col1:
            label = ("◆ " if s["id"] == st.session_state.current_session_id else "") + s["name"]
            if st.button(label, key=f"session_{s['id']}", use_container_width=True):
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

    st.markdown("---")
    with st.expander("⚙ Settings"):
        st.session_state.show_subtitle = st.checkbox(
            "Show tagline (groq · supabase · tavily)", value=st.session_state.show_subtitle
        )
        st.session_state.show_full_model_name = st.checkbox(
            "Show full model name on badge", value=st.session_state.show_full_model_name
        )

# ---------- Main chat area ----------
st.markdown("## Aadsia")
if st.session_state.show_subtitle:
    st.caption("groq · supabase · tavily — verified web-grounded answers")

session_id = st.session_state.current_session_id
history = db.get_session_messages(session_id)

if not history:
    st.info("No messages yet — say hello to start this session.")

for i, msg in enumerate(history):
    marker = AVATAR_USER if msg["role"] == "user" else AVATAR_ASSISTANT
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

        ts = msg["timestamp"][11:19] if msg["timestamp"] else ""
        who = "you" if msg["role"] == "user" else "aadsia"
        st.markdown(f'<div class="timestamp">{marker} {who} · {ts}</div>', unsafe_allow_html=True)

        if msg["role"] == "assistant":
            extra = db.get_message_meta(msg)

            if extra:
                status = extra.get("status")
                sources = extra.get("sources")
                if status == "VERIFIED" and sources:
                    st.markdown(f'<div class="status-verified">VERIFIED · {len(sources)} sources</div>', unsafe_allow_html=True)
                elif status == "LIMITED" and sources:
                    st.markdown(f'<div class="status-limited">LIMITED · {len(sources)} source, low confidence</div>', unsafe_allow_html=True)
                if sources:
                    with st.expander(f"see sources ({len(sources)})"):
                        for s in sources:
                            st.markdown(f"→ **{s['title']}** — [{s['url']}]({s['url']})")

            model_for_badge = extra["model"] if extra and extra.get("model") else st.session_state.selected_model
            model_label = model_for_badge if st.session_state.show_full_model_name else "⚡"
            st.markdown(f'<span class="model-badge" title="{model_for_badge}">{model_label}</span>', unsafe_allow_html=True)

            safe_text = msg["content"].replace("`", "'").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
            st.markdown(f"""
                <button class="copy-btn" onclick="navigator.clipboard.writeText(&quot;{safe_text}&quot;)">copy</button>
            """, unsafe_allow_html=True)

if prompt := st.chat_input("Type a message..."):
    if not history:
        db.update_session_name_from_first_message(session_id, prompt)

    db.save_message(session_id, "user", prompt)
    with st.chat_message("user"):
        st.write(prompt)

    full_history = db.get_session_messages(session_id)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in full_history]

    with st.chat_message("assistant"):
        search_results = None
        if st.session_state.get("web_search_enabled"):
            with st.spinner("Searching the web..."):
                search_results = search.search_web(prompt)
        with st.spinner("Thinking..."):
            try:
                result = llm.get_response(
                    api_messages,
                    model=st.session_state.selected_model,
                    search_results=search_results,
                )
                reply = result["text"]
            except Exception as e:
                reply = f"⚠️ Error calling Groq API: {e}"
                result = {"text": reply, "sources": None, "status": "NONE", "model": st.session_state.selected_model}
        st.write(reply)

    db.save_message(
        session_id, "assistant", reply,
        meta={"status": result["status"], "sources": result["sources"], "model": result["model"]},
    )
    st.rerun()