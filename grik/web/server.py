"""
Grik web interface.

A FastAPI server that serves a chat UI and relays messages to Grik's brain
over WebSocket. Voice features:
  - TTS: ElevenLabs (the same Celtic voice as voice mode) streamed as audio
    to the browser, with browser Speech Synthesis as fallback.
  - STT: faster-whisper on the server when available, with browser Web Speech
    API as the primary path (no round-trip needed when supported).

Run standalone:
    python -m grik.web.server

Or via the main entrypoint:
    GRIK_WEB_MODE=true python -m grik.main
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..brain import Grik
from ..config import config
from ..manager import AgentManager

log = logging.getLogger("grik.web")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Grik Web")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_sessions: dict[str, Grik] = {}

_tts_client = None
_stt_model = None


def _get_tts():
    global _tts_client
    if _tts_client is not None:
        return _tts_client
    if not config.elevenlabs_api_key or not config.elevenlabs_voice_id:
        return None
    try:
        from elevenlabs.client import ElevenLabs
        _tts_client = ElevenLabs(api_key=config.elevenlabs_api_key)
        log.info("ElevenLabs TTS ready (voice=%s)", config.elevenlabs_voice_id)
        return _tts_client
    except ImportError:
        log.info("ElevenLabs SDK not installed — browser TTS only")
        return None


def _get_stt():
    global _stt_model
    if _stt_model is not None:
        return _stt_model
    try:
        from faster_whisper import WhisperModel
        device = config.stt_device
        compute = "int8" if device in ("cpu", "auto") else "float16"
        _stt_model = WhisperModel(config.stt_model, device=device, compute_type=compute)
        log.info("faster-whisper STT ready (model=%s)", config.stt_model)
        return _stt_model
    except ImportError:
        log.info("faster-whisper not installed — browser STT only")
        return None


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


@app.get("/api/capabilities")
async def capabilities():
    """Tell the frontend which server-side voice features are available."""
    return {
        "tts": _get_tts() is not None,
        "stt": _get_stt() is not None,
    }


@app.post("/api/tts")
async def tts_endpoint(body: dict):
    """Generate ElevenLabs TTS audio and stream it as MP3."""
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    client = _get_tts()
    if client is None:
        return JSONResponse({"error": "ElevenLabs not configured"}, status_code=503)

    try:
        audio_iter = client.text_to_speech.convert(
            voice_id=config.elevenlabs_voice_id,
            model_id=config.elevenlabs_model,
            text=text,
            output_format="mp3_44100_128",
        )

        def generate():
            for chunk in audio_iter:
                if chunk:
                    yield chunk

        return StreamingResponse(generate(), media_type="audio/mpeg",
                                 headers={"Cache-Control": "no-cache"})
    except Exception as e:
        log.exception("TTS error")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/stt")
async def stt_endpoint(audio: UploadFile = File(...)):
    """Transcribe uploaded audio using faster-whisper."""
    model = _get_stt()
    if model is None:
        return JSONResponse({"error": "STT not available"}, status_code=503)

    try:
        audio_bytes = await audio.read()
        segments, _ = model.transcribe(io.BytesIO(audio_bytes), language="en", vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        log.info("STT heard: %s", text)
        return {"text": text}
    except Exception as e:
        log.exception("STT error")
        return JSONResponse({"error": str(e)}, status_code=500)


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
    _get_tts()
    _get_stt()
    log.info("Starting Grik web on %s:%s", config.web_host, config.web_port)
    uvicorn.run(app, host=config.web_host, port=config.web_port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    run()
