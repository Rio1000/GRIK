"""
Text-to-speech via ElevenLabs — this is where the Celtic lilt actually
lands in the ear. Pick a voice with an Irish/Scottish accent in your
ElevenLabs library (or design one) and set GRIK_VOICE_ID.

The Celtic *grammar* comes from the brain (personality.py); the Celtic
*accent* comes from the ElevenLabs voice here. Together they read naturally.
"""
from __future__ import annotations

import logging

from elevenlabs.client import ElevenLabs
from elevenlabs import stream as play_stream

from .config import config

log = logging.getLogger("grik.tts")


class TTS:
    def __init__(self):
        self.client = ElevenLabs(api_key=config.elevenlabs_api_key)
        self.voice_id = config.elevenlabs_voice_id
        self.model = config.elevenlabs_model

    def speak(self, text: str) -> None:
        if not text:
            return
        audio = self.client.text_to_speech.stream(
            voice_id=self.voice_id,
            model_id=self.model,
            text=text,
            output_format="mp3_44100_128",
        )
        play_stream(audio)  # streams to the default speaker with low latency
