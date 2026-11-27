FROM python:3.12-slim-bookworm@sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64
ARG VERSION=0.1.2
ARG VCS_REF=development
LABEL org.opencontainers.image.title="ornament-it" \
      org.opencontainers.image.description="Personalizador local de adornos con texto y helpers automáticos" \
      org.opencontainers.image.source="https://github.com/ValKiriann/ornament-it" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ORNAMENT_HOST=0.0.0.0 ORNAMENT_PORT=8768 ORNAMENT_COMMIT=${VCS_REF} \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --only-binary=:all: -r requirements.txt \
    && useradd --uid 10001 --create-home ornament
COPY app.py generador.py index.html ./
COPY assets/ ./assets/
USER 10001:10001
EXPOSE 8768
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8768/healthz',timeout=3).read()"
CMD ["python", "app.py"]
