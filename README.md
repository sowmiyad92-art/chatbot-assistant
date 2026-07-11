# Groq Chat Assistant

A multi-turn chatbot built with Streamlit and Groq's LLM API, with persistent
chat memory and support for multiple named conversation sessions — similar to
ChatGPT's sidebar, but self-built end to end.

**Live demo:** _add your Streamlit Cloud URL here after deploying_

## Features

- Multi-turn conversation with full context memory per session
- Multiple named chat sessions (create, switch, delete)
- Auto-naming of sessions from the first message
- Model picker — switch between `llama-3.1-8b-instant` (fast) and
  `llama-3.3-70b-versatile` (stronger reasoning)
- Optional live web search (via Tavily) toggle — grounds answers in current
  information instead of relying solely on the model's training cutoff
- Custom dark UI design (not a default Streamlit theme)
- SQLite-backed persistence

## Tech stack

- **Frontend:** Streamlit
- **LLM:** Groq API (Llama 3.1 / 3.3 models)
- **Storage:** Supabase (hosted Postgres) — persists permanently across redeploys

## Running locally

```bash
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`) with:
```
GROQ_API_KEY=your_key_here
DATABASE_URL=your_supabase_connection_string_here
```

Then run:
```bash
streamlit run app.py
```

## Notes

Chat history is stored in a hosted Postgres database (Supabase), so it persists
permanently — unlike a local SQLite file, it survives redeploys and restarts
on Streamlit Community Cloud.

## Project structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI, session state, page layout |
| `db.py` | Supabase (Postgres) helpers — sessions and messages |
| `llm.py` | Groq API wrapper, system prompt, model config |
| `requirements.txt` | Python dependencies |