# =============================================================================
# Dockerfile - Worker Flask
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py otel_config.py ./

EXPOSE 8081

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/health').read()" || exit 1

# Worker single-threaded por instância para que o CPU burn seja perceptível.
# Aumentar workers reduziria efeito da carga, distorcendo medidas.
CMD ["gunicorn", "-w", "2", "--threads", "2", "-b", "0.0.0.0:8081", \
     "--access-logfile", "-", "--error-logfile", "-", "worker:app"]
