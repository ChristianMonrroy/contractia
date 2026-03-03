FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para psycopg2, faiss y OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc build-essential \
    tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run inyecta PORT automáticamente
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port $PORT"]
