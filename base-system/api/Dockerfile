# =============================================================================
# Dockerfile - API Flask
# =============================================================================
# Imagem slim para reduzir overhead de baseline. Gunicorn como WSGI server
# em produção; Flask dev server seria insuficiente para testes de carga.

FROM python:3.11-slim

# Variáveis de ambiente para Python em containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instala dependências antes do código para aproveitar cache de layers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY app.py otel_config.py ./

# Porta exposta - documentação, não publica nada
EXPOSE 8080

# Healthcheck nativo do Docker (independente do healthcheck do compose)
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()" || exit 1

# Gunicorn com 2 workers e 4 threads cada - configuração modesta para que
# o overhead de observabilidade seja perceptível nos resultados.
CMD ["gunicorn", "-w", "2", "--threads", "4", "-b", "0.0.0.0:8080", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
