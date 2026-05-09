FROM python:3.12-slim

WORKDIR /app

# System deps for sentence-transformers / faiss
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build agents.financial package structure
RUN mkdir -p agents/financial && touch agents/__init__.py
COPY . agents/financial/

ENV PYTHONPATH=/app

CMD ["uvicorn", "agents.financial.agent:app", "--host", "0.0.0.0", "--port", "8002"]
