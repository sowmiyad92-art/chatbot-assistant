import json
import streamlit as st
from kb_search import get_kb_supabase_client, get_kb_groq_client


def get_random_chunk(kind):
    fn = "random_doc_chunk" if kind == "docs" else "random_code_chunk"
    rows = get_kb_supabase_client().rpc(fn, {}).execute().data
    return rows[0] if rows else None


def generate_question(chunk, kind):
    focus = ("the purpose, reasoning, or what would break if it changed"
             if kind == "code" else "a key concept or decision")
    prompt = (
        "From ONLY the text below, write one interview-style question about "
        f"{focus}, and a 2-4 sentence answer. Return ONLY JSON: "
        '{"question": "...", "answer": "..."}\n\n' + chunk["content"][:3000]
    )
    try:
        r = get_kb_groq_client().chat.completions.create(
            model="openai/gpt-oss-20b", max_tokens=1500,
            messages=[{"role": "user", "content": prompt}])
        text = r.choices[0].message.content
        qa = json.loads(text[text.index("{"):text.rindex("}") + 1])
        return qa if qa.get("question") and qa.get("answer") else None
    except Exception as e:
        print(f"[LEARN] generation error: {e}")
        return None


def _source(c, kind):
    if kind == "docs":
        return f"{c.get('project_name')}/{c.get('file_name')}"
    lr = f"#L{c['line_range']}" if c.get("line_range") else ""
    return f"{c.get('project_name')}/{c.get('file_path')}{lr}"


def _new_question(kind):
    ss = st.session_state
    for _ in range(3):
        chunk = get_random_chunk(kind)
        qa = generate_question(chunk, kind) if chunk else None
        if qa:
            ss.learn_q = {**qa, "source": _source(chunk, kind), "snippet": chunk["content"]}
            ss.learn_revealed = False
            return
    ss.learn_q = None
    st.error("Couldn't generate a question. Try again.")


def render_learn_mode():
    ss = st.session_state
    for k in ("learn_score", "learn_total", "learn_streak", "learn_bad"):
        ss.setdefault(k, 0)
    st.subheader("🎓 Learn")
    kind = st.radio("Practice from", ["docs", "code"], horizontal=True, key="learn_kind")
    if "learn_q" not in ss or st.button("New question", key="learn_new"):
        _new_question(kind)
    q = ss.get("learn_q")
    if q:
        st.markdown(f"**{q['question']}**")
        if st.button("Reveal answer", key="learn_reveal"):
            ss.learn_revealed = True
        if ss.get("learn_revealed"):
            st.write(q["answer"])
            st.caption(f"Source: {q['source']}")
            with st.expander("Source chunk"):
                st.code(q["snippet"])
            c1, c2, c3 = st.columns(3)
            if c1.button("✅ Got it", key="learn_ok"):
                ss.learn_score += 1; ss.learn_total += 1; ss.learn_streak += 1
                _new_question(kind); st.rerun()
            if c2.button("❌ Missed it", key="learn_miss"):
                ss.learn_total += 1; ss.learn_streak = 0
                _new_question(kind); st.rerun()
            if c3.button("👎 Bad question", key="learn_bad_btn"):
                ss.learn_bad += 1
                _new_question(kind); st.rerun()
    st.caption(f"Score {ss.learn_score}/{ss.learn_total} · Streak {ss.learn_streak} · Flagged bad {ss.learn_bad}")
    if st.button("Close Learn", key="learn_close"):
        ss.learn_open = False
        st.rerun()
