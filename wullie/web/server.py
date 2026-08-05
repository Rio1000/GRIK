"""
Wullie web interface.

A FastAPI server that serves a chat UI and relays messages to Wullie's brain
over WebSocket. Voice features:
  - TTS: ElevenLabs (the same Celtic voice as voice mode) streamed as audio
    to the browser, with browser Speech Synthesis as fallback.
  - STT: faster-whisper on the server when available, with browser Web Speech
    API as the primary path (no round-trip needed when supported).

Run standalone:
    python -m wullie.web.server

Or via the main entrypoint:
    WULLIE_WEB_MODE=true python -m wullie.main
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..brain import Wullie
from ..config import config
from ..manager import AgentManager

log = logging.getLogger("wullie.web")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Wullie Web")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_sessions: dict[str, Wullie] = {}

_tts_backend = None   # dict: {"mode": str, "client": ...}  or  None
_stt_model = None


def _get_tts():
    """Return a loaded TTS backend, or None if server-side TTS is disabled."""
    global _tts_backend
    if _tts_backend is not None:
        return _tts_backend

    mode = config.tts_mode

    if mode == "piper":
        try:
            import json
            from piper import PiperVoice
            voice = PiperVoice.load(config.piper_voice_path)
            speaker_id = None
            if config.piper_speaker:
                with open(config.piper_voice_path + ".json") as f:
                    id_map = json.load(f).get("speaker_id_map", {})
                if config.piper_speaker not in id_map:
                    log.warning("piper speaker %r not in voice's id_map — using default",
                                config.piper_speaker)
                else:
                    speaker_id = id_map[config.piper_speaker]
            _tts_backend = {"mode": "piper", "voice": voice, "speaker_id": speaker_id}
            log.info("Piper TTS ready (voice=%s, speaker=%s, sr=%d)",
                     config.piper_voice_path, config.piper_speaker or "default",
                     voice.config.sample_rate)
            return _tts_backend
        except FileNotFoundError:
            log.error("Piper voice file not found: %s — server TTS disabled",
                      config.piper_voice_path)
            return None
        except ImportError:
            log.error("piper-tts not installed — server TTS disabled")
            return None

    if mode == "elevenlabs":
        if not config.elevenlabs_api_key or not config.elevenlabs_voice_id:
            return None
        try:
            from elevenlabs.client import ElevenLabs
            _tts_backend = {"mode": "elevenlabs",
                            "client": ElevenLabs(api_key=config.elevenlabs_api_key)}
            log.info("ElevenLabs TTS ready (voice=%s)", config.elevenlabs_voice_id)
            return _tts_backend
        except ImportError:
            log.info("ElevenLabs SDK not installed — browser TTS only")
            return None

    # "browser" or "off" — frontend uses Web Speech API or stays silent
    log.info("TTS mode=%s — server TTS disabled, frontend uses browser Speech API", mode)
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


def _get_or_create_session(session_id: str) -> Wullie:
    if session_id not in _sessions:
        _sessions[session_id] = Wullie(manager=AgentManager())
        log.info("New session: %s", session_id)
    return _sessions[session_id]


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"ok": True, "service": "wullie-web"}


@app.get("/api/capabilities")
async def capabilities():
    """Tell the frontend which server-side voice features are available."""
    return {
        "tts": _get_tts() is not None,
        "stt": _get_stt() is not None,
    }


@app.post("/api/tts")
async def tts_endpoint(body: dict):
    """Synthesize speech and stream audio back to the browser."""
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    backend = _get_tts()
    if backend is None:
        return JSONResponse({"error": "Server TTS not configured"}, status_code=503)

    try:
        if backend["mode"] == "piper":
            import io, wave
            from piper.config import SynthesisConfig
            syn_config = None
            if backend.get("speaker_id") is not None:
                syn_config = SynthesisConfig(speaker_id=backend["speaker_id"])
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                backend["voice"].synthesize_wav(text, wf, syn_config=syn_config)
            return StreamingResponse(iter([buf.getvalue()]), media_type="audio/wav",
                                     headers={"Cache-Control": "no-cache"})

        # elevenlabs
        audio_iter = backend["client"].text_to_speech.convert(
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
    wullie = _get_or_create_session(session_id)
    log.info("WebSocket connected: %s", session_id)

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            await ws.send_json({"type": "thinking"})

            try:
                reply = wullie.ask(user_text)
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
    log.info("Starting Wullie web on %s:%s", config.web_host, config.web_port)
    uvicorn.run(app, host=config.web_host, port=config.web_port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    run()
