FROM python:3.12-slim

# Install Stockfish (or other UCI engines)
RUN apt-get update && \
    apt-get install -y --no-install-recommends stockfish && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY chess.py .
COPY relay_server.py .
COPY example_config.json config.json

# Engine ports (override in docker-compose or via -p)
EXPOSE 9998
# Relay server port
EXPOSE 19000

# Data volume for logs and TLS certs
VOLUME ["/app/data"]

ENTRYPOINT ["python", "chess.py"]
