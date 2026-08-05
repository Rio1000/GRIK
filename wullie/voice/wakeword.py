"""
Wake-word detection.

Grik stays deaf until it hears its name. We use OpenWakeWord — fully open
source, runs locally, no account or API key needed.

The bundled "hey_jarvis" model is used by default (closest to "Hey Grik").
To train a custom "Grik" wake word, see:
  https://github.com/dscripka/openWakeWord#training-new-models

Nothing is streamed anywhere: audio is processed locally, frame by frame,
and discarded.
"""
from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from ..config import config

log = logging.getLogger("grik.wake")

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80ms at 16kHz — the chunk size OpenWakeWord expects


class WakeWord:
    def __init__(self):
        model_paths = config.wake_model_paths
        if model_paths:
            self.model = Model(wakeword_models=model_paths,
                               inference_framework=config.wake_framework)
        else:
            self.model = Model(inference_framework=config.wake_framework)

        self.threshold = config.wake_sensitivity
        self.model_names = list(self.model.models.keys())
        log.info("Wake word models loaded: %s (threshold=%.2f)",
                 self.model_names, self.threshold)

    def wait(self) -> None:
        """Block until the wake word is heard."""
        log.info("Listening for wake word...")
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES,
                               dtype="int16", channels=1) as stream:
            while True:
                block, _ = stream.read(FRAME_SAMPLES)
                audio = np.frombuffer(block, dtype=np.int16)
                predictions = self.model.predict(audio)
                for name in self.model_names:
                    if predictions[name] >= self.threshold:
                        log.info("Wake word detected: %s (score=%.2f)",
                                 name, predictions[name])
                        self.model.reset()
                        return

    def close(self):
        pass
