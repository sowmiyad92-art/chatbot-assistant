"""
doc_search.py — Project Document search for Aadsia
Embeds query → searches Supabase pgvector (doc_chunks table) → returns Groq answer + chunks
"""

import os
import time
from sentence_transformers import SentenceTransformer
from supabase import create_client
from groq import Groq

# ============================================================================
# INITIALIZATION (lazy-loaded, mirrors kb_search.py)
# ============================================================================

_doc_model = None
_doc_supabase_client = None
_doc_groq_client = None

def get_doc_embedding_model():
    global _doc_model
    if _doc_model is None:
        print("[DOC] Loading sentence-transformers model...")
        _doc_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _doc_model

def get_doc_supabase_client():
    global _doc_supabase_client
    if _doc_supabase_client is None:
        url = os.getenv("KB_SUPABASE_URL")
        key = os.getenv("KB_SUPABASE_KEY")
        if not url or not key:
            raise ValueError("KB_SUPABASE_URL and KB_SUPABASE_KEY not set")
        _doc_supabase_client = create_client(url, key)
    return _doc_supabase_client

def get_doc_groq_client():
    global _doc_groq_client
    if _doc_groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        _doc_groq_client = Groq(api_key=api_key)
    return _doc_groq_client

# ============================================================================
# EMBEDDING
# ============================================================================

def embed_doc_query(query: str) -> list[float]:
    model = get_doc_embedding_model()
    return model.encode(query, convert_to_tensor=False).tolist()

# ============================================================================
# SEARCH PGVECTOR
# ============================================================================

def search_project_docs(query: str, top_k: int = 5) -> tuple[list[dict], float, float]:
    """Search doc_chunks table via search_doc_chunks RPC. Returns (chunks, embed_time, search_time)."""
    start_time = time.time()
    embedding = embed_doc_query(query)
    embed_time = time.time() - start_time

    search_start = time.time()
    supabase = get_doc_supabase_client()

    try:
        response = supabase.rpc(
            "search_doc_chunks",
            {"query_embedding": embedding, "match_count": top_k}
        ).execute()

        chunks = response.data if response.data else []
        search_time = time.time() - search_start

        formatted_chunks = []
        for chunk in chunks:
            formatted_chunks.append({
                "id": chunk.get("id"),
                "snippet": chunk.get("content", ""),
                "project": chunk.get("project_name", "unknown"),
                "file": chunk.get("file_name", "unknown"),
                "page": chunk.get("page_number"),
                "relevance_score": chunk.get("similarity", 0.0)
            })

        return formatted_chunks, embed_time, search_time

    except Exception as e:
        print(f"[DOC] Supabase search error: {e}")
        return [], embed_time, 0.0

# ============================================================================
# FORMAT CONTEXT + GROQ CALL
# ============================================================================

def format_doc_context(chunks: list[dict], query: str) -> str:
    if not chunks:
        return f"Query: {query}\n\nNo relevant chunks found."

    context = f"Query: {query}\n\n=== RELEVANT DOCUMENT CHUNKS ===\n\n"
    for i, chunk in enumerate(chunks, 1):
        citation = f"[{chunk['project']}/{chunk['file']}"
        if chunk.get("page"):
            citation += f" p.{chunk['page']}"
        citation += "]"
        context += f"CHUNK {i} {citation} (relevance: {chunk['relevance_score']:.2f})\n"
        context += f"{chunk['snippet']}\n\n"
    return context

def ask_doc(query: str, top_k: int = 5) -> dict:
    """
    Main entry point for Aadsia to call.
    Returns: {"answer": str, "chunks": list[dict], "metadata": dict}
    """
    chunks, embed_ms, search_ms = search_project_docs(query, top_k=top_k)
    context = format_doc_context(chunks, query)

    groq = get_doc_groq_client()
    system_prompt = """You are an assistant answering questions about the user's own project
documentation. Answer using only the provided chunks. Reference chunks inline using their
citations like [project/file p.N]. Be concise."""

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