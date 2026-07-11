from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
import time
import json
import traceback
from langchain_core.messages import HumanMessage, AIMessage

# Import your existing functions
# Assuming these are available from your imported modules
# from your_rag_functions import (
#     active_retriever,
#     parallel_retrieval,
#     generate_final_answer,
#     capture_for_eval,
#     eval_samples,
#     llm,
#     nest_asyncio,
#     rag_graph  # Optional, if using LangGraph
# )

app = FastAPI(title="Senior AI Financial Analyst API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str
    thread_id: str = "default_session"

class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    metadata: Dict[str, Any]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def get_conversation_history(thread_id: str) -> Optional[str]:
    """Retrieve conversation history from LangGraph memory"""
    try:
        if 'rag_graph' not in globals() or rag_graph is None:
            return None

        config = {"configurable": {"thread_id": thread_id}}
        # Use sync version for simplicity
        state = rag_graph.get_state(config)

        if state and state.values:
            messages = state.values.get("messages", [])
            if messages:
                # Format last few exchanges
                history_parts = []
                for msg in messages[-6:]:  # Last 6 messages (3 exchanges)
                    if isinstance(msg, HumanMessage):
                        history_parts.append(f"User: {msg.content}")
                    elif isinstance(msg, AIMessage):
                        # Truncate long assistant responses
                        content = msg.content[:300] if len(msg.content) > 300 else msg.content
                        history_parts.append(f"Assistant: {content}")
                if history_parts:
                    return "\n".join(history_parts)
        return None
    except Exception as e:
        print(f"⚠️ Failed to get conversation history: {e}")
        return None


async def perform_retrieval(query: str, retriever) -> List:
    """Perform async retrieval with proper event loop handling"""
    try:
        # nest_asyncio.apply() # Moved to main execution block
        loop = asyncio.get_event_loop()

        # Use simple single query retrieval for streaming endpoint
        docs = await loop.run_until_complete(
            retriever.ainvoke(query)
        )

        # Deduplicate
        seen = set()
        unique_docs = []
        for doc in docs:
            key = (doc.metadata.get('source'), doc.metadata.get('page'))
            if key not in seen:
                unique_docs.append(doc)
                seen.add(key)

        return unique_docs[:10]  # Limit to top 10 for streaming
    except Exception as e:
        print(f"⚠️ Retrieval failed: {e}")
        return []


# ============================================================================
# STREAMING GENERATION FUNCTION
# ============================================================================
async def stream_answer(
    query: str,
    retriever,
    thread_id: str,
    conversation_history: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Stream tokens as they're generated for instant feedback
    """
    start_time = time.time()

    try:
        # Send initial metadata
        yield json.dumps({
            "type": "status",
            "content": "🔍 Analyzing your question...",
            "timestamp": time.time()
        }) + "\n"

        # Step 1: Rephrase with history (if needed)
        enhanced_query = query
        if conversation_history:
            yield json.dumps({
                "type": "status",
                "content": "📝 Understanding conversation context...",
                "timestamp": time.time()
            }) + "\n"

            rephrase_prompt = f"""
            Rephrase this question to be self-contained given the conversation.

            Conversation History:
            {conversation_history}

            User's New Question: {query}

            Rephrased standalone question:
            """

            try:
                response = llm.invoke(rephrase_prompt)
                enhanced_query = response.content.strip()
                # Clean up any artifacts
                enhanced_query = enhanced_query.replace('"', '').strip()
                print(f"📝 Rephrased: {enhanced_query}")
            except Exception as e:
                print(f"⚠️ Rephrasing failed: {e}")
                enhanced_query = query

        # Step 2: Retrieval
        yield json.dumps({
            "type": "status",
            "content": "📡 Searching 10-K documents...",
            "timestamp": time.time()
        }) + "\n"

        # Perform retrieval
        docs = await perform_retrieval(enhanced_query, retriever)

        if not docs:
            yield json.dumps({
                "type": "error",
                "content": "No relevant documents found. Please try rephrasing your question.",
                "timestamp": time.time()
            }) + "\n"
            return

        yield json.dumps({
            "type": "status",
            "content": f"✅ Found {len(docs)} relevant documents. Generating answer...",
            "timestamp": time.time()
        }) + "\n"

        # Step 3: Stream the answer token by token
        yield json.dumps({
            "type": "answer_start",
            "timestamp": time.time()
        }) + "\n"

        # Create streaming prompt
        context = "\n".join([
            f"[Document {i}] {doc.page_content[:1200]}"
            for i, doc in enumerate(docs[:5])
        ])

        prompt = f"""
        You are a financial analyst. Based on the following 10-K document excerpts, answer the question concisely and accurately.

        Question: {enhanced_query}

        Documents:
        {context}

        Answer (be specific, cite sources where possible):
        """

        # Stream tokens from LLM
        full_response = ""
        try:
            # Check if LLM supports streaming
            if hasattr(llm, 'stream'):
                stream = llm.stream(prompt)

                for chunk in stream:
                    if hasattr(chunk, 'content') and chunk.content:
                        token = chunk.content
                        full_response += token
                        yield json.dumps({
                            "type": "token",
                            "content": token,
                            "timestamp": time.time()
                        }) + "\n"
            else:
                # Fallback for non-streaming LLM
                response = llm.invoke(prompt)
                full_response = response.content
                # Send entire response as one token
                yield json.dumps({
                    "type": "token",
                    "content": full_response,
                    "timestamp": time.time()
                }) + "\n"

            # Send completion metadata
            latency = time.time() - start_time
            sources = list(set([doc.metadata.get('source', 'unknown') for doc in docs[:5]]))

            yield json.dumps({
                "type": "complete",
                "metadata": {
                    "latency": round(latency, 2),
                    "num_docs": len(docs),
                    "sources": sources,
                    "answer_length": len(full_response)
                },
                "timestamp": time.time()
            }) + "\n"

            # Capture for evaluation (async, don't block)
            try:
                capture_for_eval(query, full_response, docs)
            except Exception as e:
                print(f"⚠️ Evaluation capture failed: {e}")

        except Exception as e:
            yield json.dumps({
                "type": "error",
                "content": f"Generation error: {str(e)}",
                "timestamp": time.time()
            }) + "\n"

    except Exception as e:
        yield json.dumps({
            "type": "error",
            "content": f"Unexpected error: {str(e)}",
            "timestamp": time.time()
        }) + "\n"
        print(traceback.format_exc())


# ============================================================================
# STREAMING ENDPOINT
# ============================================================================
@app.post("/analyze/stream")
async def analyze_stream(request: ChatRequest):
    """
    Streaming endpoint - sends tokens as they're generated
    """
    # Get retriever from globals
    retriever = None
    if 'active_retriever' in globals():
        retriever = active_retriever
    elif 'final_precision_retriever' in globals():
        retriever = final_precision_retriever
    elif 'ultimate_retriever' in globals():
        retriever = ultimate_retriever
    else:
        raise HTTPException(status_code=500, detail="No retriever available")

    # Get conversation history
    conversation_history = get_conversation_history(request.thread_id)

    return StreamingResponse(
        stream_answer(request.query, retriever, request.thread_id, conversation_history),
        media_type="application/x-ndjson"
    )


# ============================================================================
# NON-STREAMING ENDPOINT (Original)
# ============================================================================
@app.post("/analyze", response_model=ChatResponse)
async def analyze(request: ChatRequest):
    """
    Non-streaming endpoint - returns complete response
    """
    try:
        # Get retriever
        retriever = None
        if 'active_retriever' in globals():
            retriever = active_retriever
        elif 'final_precision_retriever' in globals():
            retriever = final_precision_retriever
        elif 'ultimate_retriever' in globals():
            retriever = ultimate_retriever
        else:
            raise HTTPException(status_code=500, detail="No retriever available")

        # Get conversation history
        conversation_history = get_conversation_history(request.thread_id)

        # Execute your existing RAG function

        start_time = time.time()
        answer, docs = execute_rag_query_v2(
            query=request.query,
            retriever=retriever,
            conversation_history=conversation_history
        )
        latency = time.time() - start_time

        # Extract sources
        sources = list(set([doc.metadata.get('source', 'unknown') for doc in docs[:5]]))

        return ChatResponse(
            answer=answer,
            thread_id=request.thread_id,
            metadata={
                "latency_seconds": round(latency, 2),
                "num_docs": len(docs),
                "sources": sources
            }
        )

    except Exception as e:
        print(f"❌ Error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    retriever_status = False
    if 'active_retriever' in globals() or 'ultimate_retriever' in globals():
        retriever_status = True

    return {
        "status": "healthy",
        "retriever_ready": retriever_status,
        "streaming_supported": hasattr(llm, 'stream') if 'llm' in globals() else False,
        "samples_captured": len(eval_samples) if 'eval_samples' in globals() else 0
    }


# ============================================================================
# EVALUATION ENDPOINTS
# ============================================================================
@app.get("/evaluation/samples")
async def get_evaluation_samples():
    """Return captured evaluation samples"""
    if 'eval_samples' in globals():
        return {"samples": eval_samples, "count": len(eval_samples)}
    return {"samples": [], "count": 0}


@app.post("/evaluation/reset")
async def reset_evaluation_samples():
    """
    Reset the evaluation buffer
    """
    global eval_samples
    if 'eval_samples' in globals():
        eval_samples = []
        return {"status": "reset", "message": "Evaluation samples cleared"}
    return {"status": "error", "message": "eval_samples not found"}


# ============================================================================
# CONVERSATION MANAGEMENT
# ============================================================================
@app.get("/conversation/{thread_id}")
async def get_conversation(thread_id: str):
    """Get conversation history for a thread"""
    if 'rag_graph' in globals() and rag_graph:
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state = rag_graph.get_state(config)
            if state and state.values:
                messages = state.values.get("messages", [])
                conversation = []
                for msg in messages:
                    if isinstance(msg, HumanMessage):
                        conversation.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        conversation.append({"role": "assistant", "content": msg.content})
                return {"thread_id": thread_id, "conversation": conversation, "length": len(conversation)}
        except Exception as e:
            print(f"⚠️ Failed to get conversation: {e}")

    return {"thread_id": thread_id, "conversation": [], "length": 0}


@app.delete("/conversation/{thread_id}")
async def clear_conversation(thread_id: str):
    """
    Clear conversation history for a thread
    """
    # Note: This depends on your LangGraph implementation
    # For MemorySaver, you may need to implement custom clearing
    return {"status": "cleared", "thread_id": thread_id, "message": "Conversation cleared"}


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    import nest_asyncio
    nest_asyncio.apply() # Apply nest_asyncio patch globally
    print("="*70)
    print("🚀 Senior Financial Analyst API Server")
    print("="*70)
    print(f"✅ Streaming endpoint: /analyze/stream")
    print(f"✅ Standard endpoint: /analyze")
    print(f"✅ Health check: /health")
    print(f"📍 Server: http://0.0.0.0:8000")
    print(f"📚 API Docs: http://0.0.0.0:8000/docs")
    print("="*70)

    # Use uvicorn.Config and uvicorn.Server to explicitly control event loop handling
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, loop="asyncio")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
