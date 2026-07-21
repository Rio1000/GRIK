"""The always-on voice loop: wake -> listen -> think -> speak."""
from __future__ import annotations

import logging

from .wakeword import WakeWord
from .audio import record_until_silence, pcm_to_wav
from .stt import STT
from .tts import TTS
from ..brain import Grik

log = logging.getLogger("grik.loop")


def run_voice_loop():
    wake = WakeWord()
    stt = STT()
    tts = TTS()
    grik = Grik()

    tts.speak("Grik's awake and listening, so. Say my name whenever ye need me.")
    try:
        while True:
            wake.wait()                                   # blocks on "Grik"/"Hey Grik"
            pcm = record_until_silence()                  # capture the command
            command = stt.transcribe(pcm_to_wav(pcm))     # local STT
            if not command:
                continue
            if command.lower().strip(" .!?") in {"never mind", "stop", "cancel"}:
                continue
            reply = grik.ask(command)                     # orchestrate + delegate
            tts.speak(reply)                              # Celtic voice out
    except KeyboardInterrupt:
        pass
    finally:
        wake.close()
