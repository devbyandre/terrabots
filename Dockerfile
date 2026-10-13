# Terrabots in a container: battle viewer on port 8765.
#   docker compose up --build        -> http://localhost:8765/
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY terrabots ./terrabots
RUN pip install --no-cache-dir .

# User bots and battle files stay importable from the working directory.
COPY bots ./bots
COPY battles ./battles

RUN useradd --create-home terrabots && mkdir -p /app/results /app/bot_data && chown terrabots /app/results /app/bot_data
USER terrabots

EXPOSE 8765
# Inside the container the server must listen on all interfaces; compose publishes
# the port on the host's 127.0.0.1 only.
CMD ["terrabots-battle", "battles/example.toml", "--host", "0.0.0.0", "--port", "8765"]
