"""
kb_search.py — Code Knowledge Base search for Aadsia
Embeds query → searches Supabase pgvector (code_chunks table) → returns Groq answer + chunks
"""

import os
import time
from sentence_transformers import SentenceTransformer
from supabase import create_client
from groq import Groq

# ============================================================================
# INITIALIZATION (lazy-loaded, separate from Aadsia's main Supabase client)
# ============================================================================

_kb_model = None
_kb_supabase_client = None
_kb_groq_client = None

def get_kb_embedding_model():
    global _kb_model
    if _kb_model is None:
        print("[KB] Loading sentence-transformers model...")
        _kb_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _kb_model

def get_kb_supabase_client():
    global _kb_supabase_client
    if _kb_supabase_client is None:
        url = os.getenv("KB_SUPABASE_URL")
        key = os.getenv("KB_SUPABASE_KEY")
        if not url or not key:
            raise ValueError("KB_SUPABASE_URL and KB_SUPABASE_KEY not set")
        _kb_supabase_client = create_client(url, key)
    return _kb_supabase_client

def get_kb_groq_client():
    global _kb_groq_client
    if _kb_groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")  # reuse Aadsia's existing Groq key
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        _kb_groq_client = Groq(api_key=api_key)
    return _kb_groq_client

# ============================================================================
# EMBEDDING
# ============================================================================

def embed_kb_query(query: str) -> list[float]:
    model = get_kb_embedding_model()
    return model.encode(query, convert_to_tensor=False).tolist()

# ============================================================================
# SEARCH PGVECTOR
# ============================================================================

def search_code_knowledge_base(query: str, top_k: int = 5) -> tuple[list[dict], float, float]:
    """Search code_chunks table via search_code_chunks RPC. Returns (chunks, embed_time, search_time)."""
    start_time = time.time()
    embedding = embed_kb_query(query)
    embed_time = time.time() - start_time

    search_start = time.time()
    supabase = get_kb_supabase_client()

    try:
        response = supabase.rpc(
            "search_code_chunks",
            {"query_embedding": embedding, "match_count": top_k}
        ).execute()

        chunks = response.data if response.data else []
        search_time = time.time() - search_start

        formatted_chunks = []
        for chunk in chunks:
            formatted_chunks.append({
                "id": chunk.get("id"),
                "chunk_id": chunk.get("chunk_id"),
                "snippet": chunk.get("content", ""),
                "repo": chunk.get("project_name", "unknown"),
                "file": chunk.get("file_path", "unknown"),
                "chunk_name": chunk.get("chunk_name"),
                "line_range": chunk.get("line_range"),
                "relevance_score": chunk.get("similarity", 0.0)
            })

        return formatted_chunks, embed_time, search_time

    except Exception as e:
        print(f"[KB] Supabase search error: {e}")
        return [], embed_time, 0.0

# ============================================================================
# FORMAT CONTEXT + GROQ CALL
# ============================================================================

def format_kb_context(chunks: list[dict], query: str) -> str:
    if not chunks:
        return f"Query: {query}\n\nNo relevant chunks found."

    context = f"Query: {query}\n\n=== RELEVANT CODE CHUNKS ===\n\n"
    for i, chunk in enumerate(chunks, 1):
        citation = f"[{chunk['repo']}/{chunk['file']}"
        if chunk.get("chunk_name"):
            citation += f"::{chunk['chunk_name']}"
        if chunk.get("line_range"):
            citation += f"#L{chunk['line_range']}"
        citation += "]"
        context += f"CHUNK {i} {citation} (relevance: {chunk['relevance_score']:.2f})\n"
        context += f"```\n{chunk['snippet']}\n```\n\n"
    return context

def ask_kb(query: str, top_k: int = 5) -> dict:
    """
    Main entry point for Aadsia to call.
    Returns: {"answer": str, "chunks": list[dict], "metadata": dict}
    """
    chunks, embed_ms, search_ms = search_code_knowledge_base(query, top_k=top_k)
    context = format_kb_context(chunks, query)

    groq = get_kb_groq_client()
    system_prompt = """You are an expert code assistant.
Answer questions about the user's code repositories using the provided chunks.
Reference chunks inline using their citations like [repo/file#L45-L52].
Be concise and technical."""

    try:
        response = groq.chat.completions.create(
            model="openai/gpt-oss-20b",
            max_tokens=1000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{context}\n\nQuestion: {query}"}
            ]
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"Error calling Groq: {e}"

    return {
        "answer": answer,
        "chunks": chunks,
        "metadata": {
            "total_chunks_searched": len(chunks),
            "query_embedding_ms": int(embed_ms * 1000),
            "retrieval_ms": int(search_ms * 1000)
        }
    }