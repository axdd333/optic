FROM python:3.11-slim

# ── Optic V1 — Single-container deployment ────────────────────────
# Build:  docker build -t optic-v1 .
# Run:    docker run -p 3003:3003 -v optic_data:/root/.optic optic-v1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV OPTIC_HOST=0.0.0.0
ENV OPTIC_PORT=3003
ENV PYTHONPATH=/app/src

EXPOSE 3003

CMD ["uvicorn", "optic.v1.server:app", "--host", "0.0.0.0", "--port", "3003"]
