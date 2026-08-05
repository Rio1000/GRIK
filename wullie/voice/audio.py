"""
Microphone capture (record the command after the wake word) + playback.

We record 16 kHz mono until the speaker goes quiet for a moment, using a
simple energy-based silence detector. Good enough for command capture and
avoids a heavyweight VAD dependency.
"""
from __future__ import annotations

import io
import wave
import audioop
import logging

import sounddevice as sd

log = logging.getLogger("wullie.audio")

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME = int(SAMPLE_RATE * FRAME_MS / 1000)


def record_until_silence(max_seconds: float = 12.0,
                         silence_ms: int = 800,
                         threshold: int = 500) -> bytes:
    """Record from the default mic; stop after `silence_ms` of quiet."""
    frames = bytearray()
    silent_frames = 0
    silence_limit = silence_ms // FRAME_MS
    max_frames = int(max_seconds * 1000 / FRAME_MS)
    started = False

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME,
                           dtype="int16", channels=1) as stream:
        for _ in range(max_frames):
            block, _ = stream.read(FRAME)
            frames.extend(block)
            energy = audioop.rms(block, 2)
            if energy > threshold:
                started = True
                silent_frames = 0
            elif started:
                silent_frames += 1
                if silent_frames > silence_limit:
                    break
    return bytes(frames)


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()
