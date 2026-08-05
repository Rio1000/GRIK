# Runs the Wullie BRAIN in text mode inside Docker (no audio devices).
# For full voice, run the orchestrator on the host instead (see README).
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir anthropic>=0.40 httpx>=0.27 docker>=7.1
COPY wullie ./wullie
ENV WULLIE_TEXT_MODE=true
CMD ["python", "-m", "wullie.main"]
