FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build coordinator package structure
RUN mkdir -p coordinator
COPY . coordinator/

ENV PYTHONPATH=/app

RUN mkdir -p /data

CMD ["uvicorn", "coordinator.agent:app", "--host", "0.0.0.0", "--port", "8000"]
