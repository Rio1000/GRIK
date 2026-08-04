"""Speech-to-text, local, via faster-whisper (no cloud round-trip for STT)."""
from __future__ import annotations

import io
import logging

from faster_whisper import WhisperModel

from ..config import config

log = logging.getLogger("grik.stt")


class STT:
    def __init__(self):
        device = config.stt_device
        compute = "int8" if device in ("cpu", "auto") else "float16"
        self.model = WhisperModel(config.stt_model, device=device, compute_type=compute)

    def transcribe(self, wav_bytes: bytes) -> str:
        segments, _ = self.model.transcribe(io.BytesIO(wav_bytes), language="en", vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        log.info("heard: %s", text)
        return text
