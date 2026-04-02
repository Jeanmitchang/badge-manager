FROM debian:bookworm-slim

# ─── Variables de build ───────────────────────────────────
ARG DEBIAN_FRONTEND=noninteractive

# ─── System deps + Wine ───────────────────────────────────
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        wine wine32 wine64 \
        sqlite3 \
        ca-certificates \
        xvfb \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ─── App directory ────────────────────────────────────────
WORKDIR /app

# ─── Python deps ──────────────────────────────────────────
COPY requirements_v2.txt .
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r requirements_v2.txt

# ─── App source ───────────────────────────────────────────
COPY server_v2.py database.py setup_v2.py emergency_v2.py ./
COPY static_v2/ ./static_v2/

# ─── Directories ──────────────────────────────────────────
RUN mkdir -p /app/data /app/mct_output /app/backups

# ─── Default env ──────────────────────────────────────────
ENV PATH="/app/venv/bin:$PATH" \
    VIGIK_HOST=0.0.0.0 \
    VIGIK_PORT=8766 \
    VIGIK_EXE=./vigik_loader_cli.exe \
    VIGIK_CERT=./cert.txt \
    VIGIK_MCT=./mct_output \
    VIGIK_DB_PATH=./data/badge_manager.db \
    WINEDEBUG=-all

EXPOSE 8766

VOLUME ["/app/data", "/app/mct_output", "/app/backups"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8766/api/ping')" || exit 1

# ─── Entrypoint ───────────────────────────────────────────
CMD ["python3", "server_v2.py"]
