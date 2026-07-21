"""
Wake-word detection.

Grik stays deaf until it hears its name. We use Picovoice Porcupine with a
custom keyword file ("Grik" / "Hey Grik") that you train for free at
https://console.picovoice.ai — download the .ppn and point GRIK_WAKE_PPN at it.

Nothing is streamed anywhere before the wake word fires: audio is processed
locally, frame by frame, and discarded.
"""
from __future__ import annotations

import logging

import pvporcupine
from pvrecorder import PvRecorder

from .config import config

log = logging.getLogger("grik.wake")


class WakeWord:
    def __init__(self):
        self.porcupine = pvporcupine.create(
            access_key=config.picovoice_access_key,
            keyword_paths=[config.wake_keyword_path],
            sensitivities=[config.wake_sensitivity],
        )
        self.recorder = PvRecorder(frame_length=self.porcupine.frame_length, device_index=-1)

    def wait(self) -> None:
        """Block until the wake word is heard."""
        self.recorder.start()
        log.info("Listening for 'Grik'...")
        try:
            while True:
                pcm = self.recorder.read()
                if self.porcupine.process(pcm) >= 0:
                    log.info("Wake word detected.")
                    return
        finally:
            self.recorder.stop()

    def close(self):
        self.recorder.delete()
        self.porcupine.delete()
