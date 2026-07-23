"""
Grik web interface.

A FastAPI server that serves a chat UI and relays messages to Grik's brain
over WebSocket. Supports text and browser-based voice input (Web Speech API
on the client side — no local mic needed on the server).

Run standalone:
    python -m grik.web.server

Or via the main entrypoint:
    GRIK_WEB_MODE=true python -m grik.main
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..brain import Grik
from ..config import config
from ..manager import AgentManager

log = logging.getLogger("grik.web")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Grik Web")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_sessions: dict[str, Grik] = {}


def _get_or_create_session(session_id: str) -> Grik:
    if session_id not in _sessions:
        _sessions[session_id] = Grik(manager=AgentManager())
        log.info("New session: %s", session_id)
    return _sessions[session_id]


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"ok": True, "service": "grik-web"}


@app.websocket("/ws/{session_id}")
async def websocket_chat(ws: WebSocket, session_id: str):
    await ws.accept()
    grik = _get_or_create_session(session_id)
    log.info("WebSocket connected: %s", session_id)

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            await ws.send_json({"type": "thinking"})

            try:
                reply = grik.ask(user_text)
            except Exception as e:
                log.exception("Brain error")
                reply = f"Something went wrong: {e}"

            await ws.send_json({"type": "reply", "text": reply})
    except WebSocketDisconnect:
        log.info("WebSocket disconnected: %s", session_id)


def run():
    import uvicorn
    log.info("Starting Grik web on %s:%s", config.web_host, config.web_port)
    uvicorn.run(app, host=config.web_host, port=config.web_port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    run()
