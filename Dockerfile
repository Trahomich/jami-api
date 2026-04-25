FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-gi \
    python3-gi-cairo \
    gir1.2-glib-2.0 \
    dbus \
    dbus-x11 \
    dconf-cli \
    curl \
    gnupg2 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -k https://dl.jami.net/public-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/jami-archive-keyring.gpg \
    && sh -c "echo 'deb [signed-by=/usr/share/keyrings/jami-archive-keyring.gpg] https://dl.jami.net/nightly/debian_12/ jami main' > /etc/apt/sources.list.d/jami.list" \
    && apt-get update \
    && apt-get install -y --no-install-recommends jami-daemon \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir .

COPY app/ ./app/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

VOLUME ["/root/.local/share/jami"]

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
