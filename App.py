import streamlit as st
import streamlit.components.v1 as components
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
    --bg: #0B0E14;
    --bg-sidebar: #10141C;
    --bg-input: #161B24;
    --bg-panel: #131720;
    --text: #E8E6E0;
    --text-dim: #6B7280;
    --accent-user: #D9704A;
    --accent-assistant: #6FA8AF;
    --accent-verified: #4CAF6D;
    --accent-limited: #D97706;
    --border: #232A36;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    color: var(--text) !important;
}
* { scrollbar-color: var(--border) var(--bg); }

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

/* Sidebar section labels: uppercase small-caps monospace, matching reference */
section[data-testid="stSidebar"] h3 {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim) !important;
    font-weight: 500 !important;
}

/* "+ new_session" style button: bordered, monospace, green */
section[data-testid="stSidebar"] .stButton:first-of-type button {
    font-family: 'JetBrains Mono', monospace !important;
    background-color: transparent !important;
    color: var(--accent-verified) !important;
    border: 1px solid var(--accent-verified) !important;
    border-radius: 4px !important;
    font-weight: 500 !important;
    text-align: center !important;
}
section[data-testid="stSidebar"] .stButton:first-of-type button:hover {
    background-color: rgba(76, 175, 109, 0.1) !important;
}

.session-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    cursor: pointer;
    border-radius: 4px;
}
.session-row:hover { background: rgba(255,255,255,0.04); }
.session-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--border);
    flex-shrink: 0;
}
.session-row.active .session-dot { background: var(--accent-verified); }
.session-name { color: var(--text-dim); }
.session-row.active .session-name { color: var(--text); font-weight: 500; }

.stChatMessage {
    background: transparent !important;
    border-radius: 0 !important;
    padding-left: 14px !important;
    margin-bottom: 4px;
}
div[data-testid="stChatMessageContent"] { font-family: 'Inter', sans-serif; }

/* Hide default avatar icon entirely — reference design has no icon, just a colored border */
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"],
[data-testid*="Avatar"] {
    display: none !important;
}
.stChatMessage:has(div[data-testid="stChatMessageAvatarUser"]) {
    border-left: 2px solid var(--accent-user);
}
.stChatMessage:has(div[data-testid="stChatMessageAvatarAssistant"]) {
    border-left: 2px solid var(--accent-assistant);
}

.role-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 4px;
    margin-left: 14px;
}
.role-label.user { color: var(--accent-user); }
.role-label.assistant { color: var(--accent-assistant); }
.role-label .time {
    color: var(--text-dim);
    font-weight: 400;
    margin-left: 8px;
    font-size: 12px;
}

/* Model badge pill */
.model-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 3px 12px;
    margin-left: 14px;
    margin-top: 8px;
    margin-bottom: 6px;
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

.tavily-usage {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
}

/* Status flags */
.status-verified, .status-limited {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 500;
    margin-left: 14px;
    margin-top: 6px;
}
.status-verified { color: var(--accent-verified); }
.status-verified::before { content: "● "; }
.status-limited { color: var(--accent-limited); }
.status-limited::before { content: "● "; }

.sources-panel {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    margin: 8px 0 8px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}
.sources-panel .src-line { color: var(--text-dim); margin: 4px 0; }
.sources-panel .src-line a { color: #6FA8D9; text-decoration: none; }
.sources-panel .src-line a:hover { text-decoration: underline; }

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

# NOTE: st.chat_message(avatar=...) is unreliable across Streamlit versions —
# it validates against emoji ranges and can crash on both geometric shapes (●/◆)
# AND standard emoji depending on the Streamlit/Python build (confirmed crash on
# python3.14 here). We don't use avatar= at all — role labels (user/assistant)
# are rendered as styled markdown text above each message instead.

# ---------- Sidebar: sessions + settings ----------
# Session switching uses a query param + <a href> link (not st.button) so the
# active-session dot can be styled independently from the label text —
# st.button only renders plain text, so the dot and text always shared one color.
qp = st.query_params
if "session_id" in qp:
    try:
        qid = int(qp["session_id"])
        if qid != st.session_state.get("current_session_id"):
            st.session_state.current_session_id = qid
    except ValueError:
        pass

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
if "tavily_search_count" not in st.session_state:
    st.session_state.tavily_search_count = 0

with st.sidebar:
    st.markdown("### Sessions")
    if st.button("+ new_session", use_container_width=True):
        new_id = db.create_session("New chat")
        st.session_state.current_session_id = new_id
        st.query_params["session_id"] = str(new_id)
        st.rerun()

    sessions = db.get_sessions()
    for s in sessions:
        col1, col2 = st.columns([5, 1])
        with col1:
            is_active = s["id"] == st.session_state.current_session_id
            row_class = "session-row active" if is_active else "session-row"
            st.markdown(
                f'<a href="?session_id={s["id"]}" target="_self" style="text-decoration:none;">'
                f'<div class="{row_class}"><span class="session-dot"></span>'
                f'<span class="session-name">{s["name"]}</span></div></a>',
                unsafe_allow_html=True,
            )
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

    st.markdown("---")
    with st.expander("▸ tavily_usage (click to reveal)"):
        st.markdown(
            f'<span class="tavily-usage">{st.session_state.tavily_search_count} searches this session</span>',
            unsafe_allow_html=True,
        )

# ---------- Main chat area ----------
st.markdown("## Aadsia")
if st.session_state.show_subtitle:
    st.caption("groq · supabase · tavily — verified web-grounded answers")
else:
    st.caption("verified web-grounded answers")

session_id = st.session_state.current_session_id
history = db.get_session_messages(session_id)

if not history:
    st.info("No messages yet — say hello to start this session.")

for i, msg in enumerate(history):
    role = msg["role"]
    ts = msg["timestamp"][11:19] if msg["timestamp"] else ""

    with st.chat_message(role):
        st.markdown(
            f'<div class="role-label {role}">{role}<span class="time">{ts}</span></div>',
            unsafe_allow_html=True,
        )
        st.write(msg["content"])

        if role == "assistant":
            extra = db.get_message_meta(msg)

            if extra:
                status = extra.get("status")
                sources = extra.get("sources")
                if status == "VERIFIED" and sources:
                    st.markdown(f'<div class="status-verified">VERIFIED · {len(sources)} sources</div>', unsafe_allow_html=True)
                elif status == "LIMITED" and sources:
                    st.markdown(f'<div class="status-limited">LIMITED · {len(sources)} source, low confidence</div>', unsafe_allow_html=True)
                if sources:
                    with st.expander(f"see sources · {len(sources)}"):
                        lines = "".join(
                            f'<div class="src-line">→ {s["title"]} — <a href="{s["url"]}" target="_blank">{s["url"]}</a></div>'
                            for s in sources
                        )
                        st.markdown(f'<div class="sources-panel">{lines}</div>', unsafe_allow_html=True)

            model_for_badge = extra["model"] if extra and extra.get("model") else st.session_state.selected_model
            model_label = f"⚡ groq/{model_for_badge}" if st.session_state.show_full_model_name else "⚡"
            st.markdown(f'<span class="model-badge" title="groq/{model_for_badge}">{model_label}</span>', unsafe_allow_html=True)

            safe_text = msg["content"].replace("\\", "\\\\").replace("`", "'").replace("\n", "\\n").replace('"', '\\"')
            html_escaped_content = (
                msg["content"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            components.html(f"""
                <style>
                  body {{ margin: 0; }}
                  .copy-btn {{
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 11px;
                    color: #6B7280;
                    background: transparent;
                    border: 1px solid #232A36;
                    border-radius: 4px;
                    padding: 2px 10px;
                    cursor: pointer;
                  }}
                  .copy-btn:hover {{ color: #E8E6E0; border-color: #6FA8AF; }}
                </style>
                <button class="copy-btn" id="copyBtn">copy</button>
                <textarea id="copySource" style="position:absolute; left:-9999px;">{html_escaped_content}</textarea>
                <script>
                  document.getElementById("copyBtn").addEventListener("click", function() {{
                    const btn = this;
                    const text = document.getElementById("copySource").value;
                    function fallbackCopy() {{
                      const ta = document.getElementById("copySource");
                      ta.style.left = "0px";
                      ta.focus();
                      ta.select();
                      try {{ document.execCommand("copy"); }} catch (e) {{}}
                      ta.style.left = "-9999px";
                    }}
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                      navigator.clipboard.writeText(text).catch(fallbackCopy);
                    }} else {{
                      fallbackCopy();
                    }}
                    btn.innerText = "copied";
                    setTimeout(function() {{ btn.innerText = "copy"; }}, 1500);
                  }});
                </script>
            """, height=32)

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
                st.session_state.tavily_search_count += 1
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