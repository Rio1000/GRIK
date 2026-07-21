"""Central configuration, read from the environment (.env)."""
import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- Brain (the LLM that IS Grik) ---
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    brain_model: str = field(default_factory=lambda: os.getenv("GRIK_BRAIN_MODEL", "claude-sonnet-4-6"))

    # --- Voice: wake word (Picovoice Porcupine) ---
    picovoice_access_key: str = field(default_factory=lambda: os.getenv("PICOVOICE_ACCESS_KEY", ""))
    # Path to a custom "Grik" / "Hey Grik" keyword file trained at console.picovoice.ai
    wake_keyword_path: str = field(default_factory=lambda: os.getenv("GRIK_WAKE_PPN", "keywords/grik.ppn"))
    wake_sensitivity: float = field(default_factory=lambda: float(os.getenv("GRIK_WAKE_SENSITIVITY", "0.6")))

    # --- Voice: speech to text (local faster-whisper) ---
    stt_model: str = field(default_factory=lambda: os.getenv("GRIK_STT_MODEL", "base.en"))
    stt_device: str = field(default_factory=lambda: os.getenv("GRIK_STT_DEVICE", "auto"))

    # --- Voice: text to speech (ElevenLabs) ---
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))
    # A voice with an Irish/Scottish lilt. Pick one in your ElevenLabs library.
    elevenlabs_voice_id: str = field(default_factory=lambda: os.getenv("GRIK_VOICE_ID", ""))
    elevenlabs_model: str = field(default_factory=lambda: os.getenv("GRIK_TTS_MODEL", "eleven_turbo_v2_5"))

    # --- Agent orchestration (Docker) ---
    docker_network: str = field(default_factory=lambda: os.getenv("GRIK_DOCKER_NETWORK", "grik-net"))
    base_agent_image: str = field(default_factory=lambda: os.getenv("GRIK_BASE_AGENT_IMAGE", "grik-base-agent:latest"))
    agent_call_timeout: int = field(default_factory=lambda: int(os.getenv("GRIK_AGENT_TIMEOUT", "120")))
    allow_provisioning: bool = field(default_factory=lambda: _bool("GRIK_ALLOW_PROVISIONING", True))

    # --- Modes ---
    text_mode: bool = field(default_factory=lambda: _bool("GRIK_TEXT_MODE", False))


config = Config()
