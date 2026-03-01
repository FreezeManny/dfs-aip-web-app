FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (OCR for PDF processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ocrmypdf tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY basic/requirements.txt aip-requirements.txt
COPY docker-webinterface/backend/requirements.txt .
RUN pip install --no-cache-dir -r aip-requirements.txt -r requirements.txt

# Copy application code
COPY basic/aip.py .
COPY basic/aip/ aip/
COPY docker-webinterface/backend/main.py .

# Create data directories
RUN mkdir -p data output cache

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
