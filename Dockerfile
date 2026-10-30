FROM python:3.11-slim

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure full read/write permissions for SQLite database and RAG cache
RUN chmod -R 777 /app

ENV HOST=0.0.0.0
ENV PORT=7860

EXPOSE 7860

CMD ["python", "run.py"]
