# Runtime for sandboxed bots: Python and numpy only. The engine's terrabots
# package and the bot's own files are mounted read-only at run time, so this
# image doesn't need rebuilding when either changes.
#   docker build -t terrabots-sandbox -f docker/sandbox.Dockerfile docker/
FROM python:3.12-slim
RUN pip install --no-cache-dir "numpy==2.4.*" \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin bot
USER 10001
WORKDIR /bot
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/bot:/engine
