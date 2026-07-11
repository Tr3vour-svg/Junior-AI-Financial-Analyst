import streamlit as st
import requests
import time
import json
import uuid
from datetime import datetime
import pandas as pd


st.set_page_config(
    page_title="Agentic 10-K Financial Analyst",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better visual feedback
st.markdown("""
<style>
    .status-box {
        background-color: #f0f2f6;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        font-size: 0.9rem;
        color: #666;
    }
    .spinner-text {
        display: inline-block;
        margin-left: 0.5rem;
    }
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .source-tag {
        background-color: #e3f2fd;
        padding: 0.2rem 0.5rem;
        border-radius: 0.3rem;
        font-size: 0.8rem;
        display: inline-block;
        margin: 0.2rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "latency_history" not in st.session_state:
    st.session_state.latency_history = []
if "processing" not in st.session_state:
    st.session_state.processing = False

# ============================================================================
# Sidebar
# ============================================================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/financial-analyst.png", width=80)
    st.markdown("## 🎛️ Controls")

    # Session info
    st.markdown("### 📋 Session")
    st.info(f"🆔 Session ID: `{st.session_state.thread_id[:8]}...`")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🆕 New Session", use_container_width=True):
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.latency_history = []
            st.rerun()
    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    st.markdown("---")

    # API Configuration
    st.markdown("### 🔌 Connection")
    api_url = st.text_input("API URL", value="http://localhost:8000", help="FastAPI backend URL")

    # Test connection
    if st.button("🔍 Test Connection", use_container_width=True):
        try:
            response = requests.get(f"{api_url}/health", timeout=5)
            if response.status_code == 200:
                st.success("✅ Backend connected!")
            else:
                st.error(f"❌ Error: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Cannot connect: {e}")

    st.markdown("---")

    # Performance metrics
    if st.session_state.latency_history:
        st.markdown("### 📊 Performance")
        avg_latency = sum(st.session_state.latency_history) / len(st.session_state.latency_history)
        st.metric("Avg Response Time", f"{avg_latency:.1f}s")
        st.metric("Total Queries", len(st.session_state.latency_history))

        # Latency chart
        if len(st.session_state.latency_history) > 1:
            latency_df = pd.DataFrame({
                "Query": range(1, len(st.session_state.latency_history) + 1),
                "Latency": st.session_state.latency_history
            })
            st.line_chart(latency_df.set_index("Query"))

# ============================================================================
# Main Chat Interface
# ============================================================================
st.title("💼 Senior AI Financial Analyst")
st.markdown("""
    <div style='background-color: #e8f4f8; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;'>
    🎯 <b>Expert 10-K Analysis</b> – Ask about risk factors, financial metrics, supply chain dependencies,
    and comparative analysis across tech giants.
    </div>
""", unsafe_allow_html=True)

# Quick example queries
with st.expander("🔍 Example Queries", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📊 Risk Factors", use_container_width=True):
            st.session_state.example_query = "What are the specific 'Risk Factors' Broadcom listed regarding their dependency on a 'limited number of customers'?"
    with col2:
        if st.button("💹 Financial Metrics", use_container_width=True):
            st.session_state.example_query = "What was Microsoft's total 'Property and Equipment' for data centers in FY2025?"
    with col3:
        if st.button("🔗 Supply Chain", use_container_width=True):
            st.session_state.example_query = "Map the cascading supply chain dependencies between ASML, TSMC, and NVIDIA"

# Display chat history
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Show sources for assistant messages
        if message["role"] == "assistant" and "sources" in message and message["sources"]:
            with st.expander(f"📚 Sources ({len(message['sources'])})", expanded=False):
                for source in message["sources"]:
                    st.markdown(f"📄 `{source}`")

# ============================================================================
# Chat Input and Processing
# ============================================================================
if prompt := st.chat_input("Ask about 10-K filings, risk factors, financial comparisons..."):
    # Handle example query
    if "example_query" in st.session_state:
        prompt = st.session_state.example_query
        del st.session_state.example_query

    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Assistant response
    with st.chat_message("assistant"):
        # Create placeholders for different UI elements
        status_placeholder = st.empty()
        response_placeholder = st.empty()

        try:
            start_time = time.time()

            # Show initial status
            status_placeholder.markdown("""
            <div class="status-box">
            🔍 <b>Step 1/4:</b> Analyzing your question...
            </div>
            """, unsafe_allow_html=True)

            # Make API request (your existing endpoint)
            response = requests.post(
                f"{api_url}/analyze",
                json={
                    "query": prompt,
                    "thread_id": st.session_state.thread_id
                },
                timeout=120
            )

            # Update status
            status_placeholder.markdown("""
            <div class="status-box">
            📡 <b>Step 2/4:</b> Searching 10-K documents...
            </div>
            """, unsafe_allow_html=True)

            if response.status_code == 200:
                data = response.json()
                answer = data["answer"]
                sources = data["metadata"].get("sources", [])
                latency = data["metadata"].get("latency_seconds", time.time() - start_time)

                # Update status to generating
                status_placeholder.markdown("""
                <div class="status-box">
                💡 <b>Step 3/4:</b> Generating analysis...
                </div>
                """, unsafe_allow_html=True)

                # Simulate typing effect (visual only)
                full_response = ""
                words = answer.split()
                for i in range(0, len(words), 3):
                    full_response = " ".join(words[:i+3])
                    response_placeholder.markdown(full_response + " ▌")
                    time.sleep(0.01)  # Tiny delay for typing effect

                # Final response without cursor
                response_placeholder.markdown(answer)

                # Update status to complete
                status_placeholder.markdown(f"""
                <div class="status-box" style="background-color: #d4edda; color: #155724;">
                ✅ <b>Step 4/4:</b> Complete! ⏱️ {latency:.1f}s • 📊 {len(sources)} sources
                </div>
                """, unsafe_allow_html=True)

                # Store in session
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources
                })
                st.session_state.latency_history.append(latency)

                # Show sources in expander
                if sources:
                    with st.expander(f"📚 Retrieved Sources ({len(sources)})", expanded=False):
                        for source in sources:
                            st.markdown(f"📄 `{source}`")

            else:
                error_msg = f"❌ API Error: {response.status_code}"
                status_placeholder.markdown(f"""
                <div class="status-box" style="background-color: #f8d7da; color: #721c24;">
                {error_msg}
                </div>
                """, unsafe_allow_html=True)
                response_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

        except requests.exceptions.Timeout:
            error_msg = "⏰ Request timed out. Please try a simpler question."
            status_placeholder.markdown(f"""
            <div class="status-box" style="background-color: #f8d7da; color: #721c24;">
            {error_msg}
            </div>
            """, unsafe_allow_html=True)
            response_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            status_placeholder.markdown(f"""
            <div class="status-box" style="background-color: #f8d7da; color: #721c24;">
            {error_msg}
            </div>
            """, unsafe_allow_html=True)
            response_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

        finally:
            # Clear status after a moment (optional)
            time.sleep(2)
            status_placeholder.empty()

# ============================================================================
# Footer
# ============================================================================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray; font-size: 0.8rem;'>"
    "🔍 Powered by Pinecone | 🤖 GPT-4o | 📊 10-K Filings 2025-2026"
    "</div>",
    unsafe_allow_html=True
)
