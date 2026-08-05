"""
Text-to-speech for the voice loop.

Dispatches on config.tts_mode:
  - "piper":      local neural TTS (default, has a Scottish voice)
  - "elevenlabs": cloud voice via ElevenLabs
  - "browser":    no-op here — the browser handles TTS in web mode
  - "off":        no-op

The Celtic *grammar* comes from the brain (personality.py); the Celtic
*accent* comes from the voice engine chosen here.
"""
from __future__ import annotations

import io
import logging
import wave

from ..config import config

log = logging.getLogger("wullie.tts")


class _PiperBackend:
    def __init__(self, voice_path: str, speaker: str = ""):
        import json
        from piper import PiperVoice
        self.voice = PiperVoice.load(voice_path)
        self.sample_rate = self.voice.config.sample_rate
        self.speaker_id = None
        if speaker:
            with open(voice_path + ".json") as f:
                id_map = json.load(f).get("speaker_id_map", {})
            if speaker not in id_map:
                log.warning("piper speaker %r not in voice's id_map — using default", speaker)
            else:
                self.speaker_id = id_map[speaker]
        log.info("Piper TTS ready (voice=%s, speaker=%s, sr=%d)",
                 voice_path, speaker or "default", self.sample_rate)

    def speak(self, text: str) -> None:
        import numpy as np
        import sounddevice as sd
        from piper.config import SynthesisConfig
        syn_config = SynthesisConfig(speaker_id=self.speaker_id) if self.speaker_id is not None else None
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self.voice.synthesize_wav(text, wf, syn_config=syn_config)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16)
        sd.play(samples, self.sample_rate)
        sd.wait()


class _ElevenLabsBackend:
    def __init__(self):
        from elevenlabs.client import ElevenLabs
        self.client = ElevenLabs(api_key=config.elevenlabs_api_key)
        self.voice_id = config.elevenlabs_voice_id
        self.model = config.elevenlabs_model
        log.info("ElevenLabs TTS ready (voice=%s)", self.voice_id)

    def speak(self, text: str) -> None:
        from elevenlabs import stream as play_stream
        audio = self.client.text_to_speech.stream(
            voice_id=self.voice_id,
            model_id=self.model,
            text=text,
            output_format="mp3_44100_128",
        )
        play_stream(audio)


class _SilentBackend:
    def __init__(self, mode: str):
        log.info("TTS mode=%s — voice loop is silent (web UI handles TTS)", mode)

    def speak(self, text: str) -> None:
        pass


class TTS:
    def __init__(self):
        mode = config.tts_mode
        if mode == "piper":
            self._backend = _PiperBackend(config.piper_voice_path, config.piper_speaker)
        elif mode == "elevenlabs":
            self._backend = _ElevenLabsBackend()
        else:
            self._backend = _SilentBackend(mode)

    def speak(self, text: str) -> None:
        if not text:
            return
        self._backend.speak(text)
