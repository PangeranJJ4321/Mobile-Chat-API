# Gunakan base image Python slim biar ringan
FROM python:3.11-slim

# Biar UTF-8 aman dan zona waktu
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Jakarta

# Set working directory
WORKDIR /app

# Install OS dependencies dengan fix untuk hash sum mismatch
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update --fix-missing && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    --allow-unauthenticated \
    gcc libpq-dev ffmpeg libmagic-dev curl && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Copy requirements
COPY requirements.txt .

# Install dependencies Python
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Buat direktori upload dengan permission yang lebih aman
RUN mkdir -p /app/uploads/avatars \
             /app/uploads/groups \
             /app/uploads/attachments/images \
             /app/uploads/attachments/videos \
             /app/uploads/attachments/audio \
             /app/uploads/attachments/documents \
             /app/uploads/thumbnails && \
    chmod -R 755 /app/uploads

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Buka port 8000 untuk FastAPI
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Jalankan uvicorn sebagai web server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]