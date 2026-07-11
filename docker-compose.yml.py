version: '3.8'

services:
  # ============================================================================
  # FastAPI Backend Service
  # ============================================================================
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: financial-analyst-backend:latest
    container_name: financial-analyst-backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - PINECONE_API_KEY=${PINECONE_API_KEY}
      - PINECONE_ENVIRONMENT=${PINECONE_ENVIRONMENT}
      - PINECONE_INDEX_NAME=${PINECONE_INDEX_NAME}
      - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY}
      - LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2:-false}
      - LOG_LEVEL=${LOG_LEVEL:-info}
    volumes:
      - ./checkpoints:/app/checkpoints  # Persistent LangGraph memory
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    networks:
      - analyst-network

  # ============================================================================
  # Streamlit Frontend Service
  # ============================================================================
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    image: financial-analyst-frontend:latest
    container_name: financial-analyst-frontend
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - analyst-network

  # ============================================================================
  # PostgreSQL for LangGraph Production Memory (Optional)
  # ============================================================================
  postgres:
    image: postgres:15-alpine
    container_name: analyst-postgres
    environment:
      - POSTGRES_USER=analyst
      - POSTGRES_PASSWORD=${DB_PASSWORD:-changeme}
      - POSTGRES_DB=langgraph_memory
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - analyst-network
    restart: unless-stopped
    profiles:
      - production

  # ============================================================================
  # Redis for Caching (Optional)
  # ============================================================================
  redis:
    image: redis:7-alpine
    container_name: analyst-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - analyst-network
    restart: unless-stopped
    profiles:
      - production

# ============================================================================
# Networks & Volumes
# ============================================================================
networks:
  analyst-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
