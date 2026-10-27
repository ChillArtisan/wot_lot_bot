FROM python:3.12-slim

WORKDIR /app

# Headless Chromium renders the slides offline (see render.py);
# fonts-dejavu-core is only a fallback, the slide fonts are bundled.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata chromium-headless-shell fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin appuser

# constraints.txt pins exact versions: an uncached rebuild must not pull new releases.
COPY requirements.txt constraints.txt pyproject.toml /app/
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY src /app/src
RUN pip install --no-cache-dir --no-deps . \
    && mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser
ENV DATA_DIR=/app/data PYTHONUNBUFFERED=1

CMD ["python", "-m", "wot_lot_bot"]
