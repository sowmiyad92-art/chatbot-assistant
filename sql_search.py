"""
sql_search.py — SQL / IMDb search for Aadsia
Runs a LangGraph SQL agent (pandas lookup tool + SQLDatabaseToolkit) against
the local IMDb dataset. Returns an answer + which tools were used, mirroring
kb_search.py's ask_kb() entry-point shape.
"""

import os
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase

# ============================================================================
# LAZY-LOADED SINGLETONS (mirrors kb_search.py's pattern)
# ============================================================================

_sql_agent = None
_imdb_df = None


def get_imdb_df():
    global _imdb_df
    if _imdb_df is None:
        _imdb_df = pd.read_csv("data/imdb_filtered_2000_2024.csv")
        _imdb_df["startYear"] = _imdb_df["startYear"].fillna(0).astype(int)
        _imdb_df["numVotes"] = _imdb_df["numVotes"].fillna(0).astype(int)
    return _imdb_df


# ============================================================================
# IMDB LOOKUP TOOL (pandas-based, for filtered/ranked queries)
# ============================================================================

class ImdbQuery(BaseModel):
    genre: Optional[str] = Field(None, description="Genre to filter by, e.g. Horror, Drama")
    min_votes: Optional[int] = Field(None, description="Minimum number of votes")
    year_from: Optional[int] = Field(None, description="Earliest release year")
    year_to: Optional[int] = Field(None, description="Latest release year")


def imdb_lookup(genre: Optional[str] = None, min_votes: Optional[int] = None,
                 year_from: Optional[int] = None, year_to: Optional[int] = None) -> str:
    df = get_imdb_df().copy()
    if genre:
        df = df[df["genres"].str.contains(genre, case=False, na=False)]
    if min_votes:
        df = df[df["numVotes"] >= min_votes]
    if year_from:
        df = df[df["startYear"] >= year_from]
    if year_to:
        df = df[df["startYear"] <= year_to]
    if df.empty:
        return "No movies found matching those filters."
    df = df.sort_values("averageRating", ascending=False).head(10)
    lines = [
        f"{r['primaryTitle']} ({r['startYear']}) - Rating {r['averageRating']}, Votes {r['numVotes']}"
        for _, r in df.iterrows()
    ]
    return "\n".join(lines)


def get_imdb_tool():
    return StructuredTool.from_function(
        func=imdb_lookup,
        name="imdb_lookup",
        description="Query a dataset of 30,000+ movies (2000-2024) by genre, vote count, or year range.",
        args_schema=ImdbQuery,
    )


# ============================================================================
# SQL AGENT SETUP
# ============================================================================

SQL_SYSTEM_INSTRUCTION = "You are a movie research assistant with access to an IMDb dataset and SQL database."


def get_sql_agent_cached():
    """Build the SQL agent once and reuse it — the original get_sql_agent()
    rebuilt the toolkit on every call, wasteful in a Streamlit rerun loop."""
    global _sql_agent
    if _sql_agent is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")

        db = SQLDatabase.from_uri("sqlite:///data/imdb.db")
        sql_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0, api_key=api_key)
        sql_tools = SQLDatabaseToolkit(db=db, llm=sql_llm).get_tools()

        agent_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0, api_key=api_key)
        _sql_agent = create_react_agent(
            model=agent_llm,
            tools=[get_imdb_tool()] + sql_tools,
            prompt=SQL_SYSTEM_INSTRUCTION,
        )
    return _sql_agent


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def ask_sql(query: str) -> dict:
    """
    Main entry point for Aadsia to call.
    Returns: {"answer": str, "tool_calls_used": list[str], "status_hint": str, "metadata": dict}
    """
    try:
        agent_executor = get_sql_agent_cached()
    except Exception as e:
        return {
            "answer": f"⚠️ Error setting up SQL agent: {e}",
            "tool_calls_used": [],
            "status_hint": "LIMITED",
            "metadata": {"error": True},
        }

    final_content = ""
    tool_calls_used = []

    try:
        for event in agent_executor.stream(
            {"messages": [("human", query)]},
            stream_mode="values",
            config={"recursion_limit": 50},
        ):
            if "messages" not in event:
                continue
            last_msg = event["messages"][-1]
            if last_msg.type == "ai":
                calls = getattr(last_msg, "tool_calls", None)
                if calls:
                    tool_calls_used.extend(c["name"] for c in calls)
                else:
                    final_content = last_msg.content
    except Exception as e:
        return {
            "answer": f"⚠️ Error running SQL agent: {e}",
            "tool_calls_used": tool_calls_used,
            "status_hint": "LIMITED",
            "metadata": {"error": True},
        }

    status_hint = "VERIFIED" if tool_calls_used else "LIMITED"

    return {
        "answer": final_content or "No answer generated.",
        "tool_calls_used": tool_calls_used,
        "status_hint": status_hint,
        "metadata": {"num_tool_calls": len(tool_calls_used)},
    }