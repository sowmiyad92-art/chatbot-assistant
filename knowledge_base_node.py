"""
Knowledge Base Node for LangGraph Router Agent
Embeds query → searches Supabase pgvector → returns top chunks + Groq answer with inline citations
"""

import os
import json
import time
from typing import Any
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client
from groq import Groq
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

# ============================================================================
# INITIALIZATION
# ============================================================================

# Lazy load model (avoid reloading on every call)
_model = None
_supabase_client = None
_groq_client = None

def get_embedding_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        print("[KB] Loading sentence-transformers model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim, fast
    return _model

def get_supabase_client() -> Client:
    """Lazy-load Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY not set")
        _supabase_client = create_client(url, key)
    return _supabase_client

def get_groq_client() -> Groq:
    """Lazy-load Groq client."""
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        _groq_client = Groq(api_key=api_key)
    return _groq_client

# ============================================================================
# EMBEDDING
# ============================================================================

def embed_query(query: str) -> list[float]:
    """Embed query using sentence-transformers."""
    model = get_embedding_model()
    embedding = model.encode(query, convert_to_tensor=False)
    return embedding.tolist()

# ============================================================================
# SEARCH PGVECTOR
# ============================================================================

def search_knowledge_base(query: str, top_k: int = 5) -> list[dict]:
    """
    Search Supabase pgvector for top_k chunks.
    
    Returns:
        List of dicts with: chunk_id, snippet, repo, file, line_range, similarity
    """
    start_time = time.time()
    
    # Embed query
    embedding = embed_query(query)
    embed_time = time.time() - start_time
    
    # Search pgvector
    search_start = time.time()
    supabase = get_supabase_client()
    
    try:
        response = supabase.rpc(
            "search_code_chunks",  # RPC function from create_rpc_search.sql
            {
                "query_embedding": embedding,
                "match_count": top_k
            }
        ).execute()
        
        chunks = response.data if response.data else []
        search_time = time.time() - search_start
        
        # Reformat for output
        formatted_chunks = []
        for i, chunk in enumerate(chunks):
            formatted_chunks.append({
                "id": chunk.get("id"),
                "snippet": chunk.get("content", ""),
                "repo": chunk.get("project_name", "unknown"),
                "file": chunk.get("file_path", "unknown"),
                "line_range": chunk.get("line_range"),  # "45-78" string or null
                "relevance_score": chunk.get("similarity", 0.0)
            })
        
        return formatted_chunks, embed_time, search_time
    
    except Exception as e:
        print(f"[KB] Supabase search error: {e}")
        return [], embed_time, 0.0

# ============================================================================
# FORMAT CONTEXT
# ============================================================================

def format_context_for_groq(chunks: list[dict], query: str) -> str:
    """
    Format search results into context block for Groq.
    Includes file refs for inline citations.
    """
    if not chunks:
        return f"Query: {query}\n\nNo relevant chunks found."
    
    context = f"Query: {query}\n\n"
    context += "=== RELEVANT CODE CHUNKS ===\n\n"
    
    for i, chunk in enumerate(chunks, 1):
        repo = chunk["repo"]
        file = chunk["file"]
        line_range = chunk["line_range"]  # "45-78" or null
        snippet = chunk["snippet"]
        score = chunk["relevance_score"]
        
        # Citation format: [repo/file#L45-L78] or [repo/file]
        if line_range:
            citation = f"[{repo}/{file}#L{line_range}]"
        else:
            citation = f"[{repo}/{file}]"
        
        context += f"CHUNK {i} {citation} (relevance: {score:.2f})\n"
        context += f"```\n{snippet}\n```\n\n"
    
    return context

# ============================================================================
# GROQ CALL
# ============================================================================

def call_groq_with_context(context: str, query: str) -> str:
    """
    Call Groq llama-3.3-70b with context chunks.
    Model should embed citations inline like [file#line].
    """
    groq = get_groq_client()
    
    system_prompt = """You are an expert code assistant. 
Answer questions about the user's code repositories using the provided chunks.
Reference chunks inline in your answer using their citations like [repo/file#L45-L52].
Be concise and technical. Focus on answering the specific question."""
    
    user_message = f"{context}\n\nQuestion: {query}"
    
    try:
        response = groq.messages.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        return response.content[0].text
    except Exception as e:
        print(f"[KB] Groq error: {e}")
        return f"Error calling Groq: {e}"

# ============================================================================
# MAIN NODE
# ============================================================================

def knowledge_base_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node: search knowledge base and return answer.
    
    Input state:
        {
            "messages": [...],
            "query": str
        }
    
    Output state:
        {
            "result": {
                "answer": str,
                "chunks": list[dict],
                "metadata": {
                    "total_chunks_searched": int,
                    "query_embedding_ms": int,
                    "retrieval_ms": int
                }
            },
            "source_used": "knowledge_base"
        }
    """
    
    query = state.get("query", "")
    if not query:
        return {
            "result": {
                "answer": "No query provided.",
                "chunks": [],
                "metadata": {}
            },
            "source_used": "knowledge_base"
        }
    
    print(f"\n[KB] Searching knowledge base for: '{query}'")
    
    # Search
    chunks, embed_ms, search_ms = search_knowledge_base(query, top_k=5)
    print(f"[KB] Found {len(chunks)} chunks (embed: {embed_ms*1000:.1f}ms, search: {search_ms*1000:.1f}ms)")
    
    # Format context
    context = format_context_for_groq(chunks, query)
    
    # Call Groq
    answer = call_groq_with_context(context, query)
    
    # Return result
    result = {
        "answer": answer,
        "chunks": chunks,
        "metadata": {
            "total_chunks_searched": len(chunks),
            "query_embedding_ms": int(embed_ms * 1000),
            "retrieval_ms": int(search_ms * 1000)
        }
    }
    
    return {
        "result": result,
        "source_used": "knowledge_base"
    }

# ============================================================================
# FASTAPI REQUEST/RESPONSE MODELS
# ============================================================================

class KBSearchRequest(BaseModel):
    """Request body for /kb-search endpoint."""
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    top_k: int = Field(default=5, ge=1, le=10, description="Number of chunks to return")

class ChunkResponse(BaseModel):
    """Single chunk in the response."""
    id: Any
    snippet: str
    repo: str
    file: str
    line_range: str | None
    relevance_score: float

class KBSearchResponse(BaseModel):
    """Response body for /kb-search endpoint."""
    answer: str
    chunks: list[ChunkResponse]
    metadata: dict[str, int]

# ============================================================================
# FASTAPI ROUTER
# ============================================================================

def create_kb_router() -> APIRouter:
    """Create FastAPI router with /kb-search endpoint."""
    router = APIRouter(prefix="/api", tags=["knowledge-base"])
    
    @router.post("/kb-search", response_model=KBSearchResponse)
    async def kb_search(request: KBSearchRequest) -> KBSearchResponse:
        """
        Search code knowledge base.
        
        Returns:
            - answer: Groq's response with inline citations [file#L45-L78]
            - chunks: List of relevant code chunks with metadata
            - metadata: Timing and count stats
        """
        try:
            # Build LangGraph-compatible state
            state = {
                "query": request.query
            }
            
            # Call knowledge base node
            output = knowledge_base_node(state)
            result = output.get("result", {})
            
            # Format response
            chunks_formatted = [
                ChunkResponse(**chunk) for chunk in result.get("chunks", [])
            ]
            
            return KBSearchResponse(
                answer=result.get("answer", ""),
                chunks=chunks_formatted,
                metadata=result.get("metadata", {})
            )
        
        except Exception as e:
            print(f"[KB] Error in kb_search: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return router

# ============================================================================
# STANDALONE TEST (for debugging)
# ============================================================================

if __name__ == "__main__":
    # Test without LangGraph
    test_state = {
        "query": "How do I query the PDF RAG agent?"
    }
    
    output = knowledge_base_node(test_state)
    
    print("\n=== OUTPUT ===")
    print(f"Answer:\n{output['result']['answer']}")
    print(f"\nChunks found: {len(output['result']['chunks'])}")
    for chunk in output['result']['chunks']:
        print(f"  - {chunk['repo']}/{chunk['file']} ({chunk['relevance_score']:.2f})")
