# ERakshak — container image (API + dashboard)
#
# Two stages on purpose. The compiler toolchain is needed to install the
# scientific stack when a wheel is unavailable for the target platform (arm64
# most often), but shipping gcc in a forensic image that handles case evidence
# is needless attack surface. The builder keeps it; the runtime never sees it.

# ── Stage 1: build the virtualenv ───────────────────────────────────────
FROM python:3.11-slim AS builder

# The scientific stack pulls ~500 MB of wheels; pip's 15s default read timeout makes
# a single slow PyPI response fail the whole build. Retry rather than go red at random.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

# Only needed when pip has to compile from sdist (pdfplumber/Pillow/reportlab).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# PYTHONUNBUFFERED: without it uvicorn/streamlit logs sit in a pipe buffer and
# `docker logs` stays empty during an incident — exactly when it is needed.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Streamlit phones home with usage telemetry by default. This image handles real
# case evidence; nothing about a session should leave the host.
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# matplotlib and streamlit both want a writable HOME for their caches. A service
# account has none by default, and the failure surfaces as an unrelated-looking
# permission error deep in a plot call.
ENV HOME=/home/erakshak \
    MPLCONFIGDIR=/home/erakshak/.cache/matplotlib

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . .

# Run as a service account, not root. A forensic tool ingests attacker-supplied
# files — malformed archives, PDFs, spreadsheets — so a parser bug should not
# start out with root in the container.
#
# Analyst-writable paths: learned mapping profiles land in config/profiles,
# uploads/outputs/models under data/. Created and chowned here so a read-only
# mount is a deliberate choice rather than a first-write crash.
RUN groupadd --system --gid 10001 erakshak \
    && useradd --system --uid 10001 --gid 10001 --home-dir "$HOME" erakshak \
    && mkdir -p data/uploads data/outputs data/models config/profiles "$MPLCONFIGDIR" \
    && chown -R 10001:10001 /app "$HOME"

USER 10001:10001

EXPOSE 8000 8501

# No HEALTHCHECK here on purpose: this one image serves two roles (API on 8000,
# dashboard on 8501), so a single baked probe would mark whichever container
# isn't the API permanently unhealthy. The probes live per-service in
# docker-compose.yml, where the role is known.

# Default: run the API. Override command for the dashboard.
CMD ["uvicorn", "backend.app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
