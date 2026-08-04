"""Central configuration, read from the environment (.env)."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- Brain (the LLM that IS Grik) ---
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    brain_model: str = field(default_factory=lambda: os.getenv("GRIK_BRAIN_MODEL", "claude-sonnet-4-6"))

    # --- Voice: wake word (OpenWakeWord) ---
    wake_model_paths: list[str] = field(default_factory=lambda: [
        p.strip() for p in os.getenv("GRIK_WAKE_MODELS", "").split(",") if p.strip()
    ])
    wake_framework: str = field(default_factory=lambda: os.getenv("GRIK_WAKE_FRAMEWORK", "onnx"))
    wake_sensitivity: float = field(default_factory=lambda: float(os.getenv("GRIK_WAKE_SENSITIVITY", "0.5")))

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

    # --- Web interface ---
    web_host: str = field(default_factory=lambda: os.getenv("GRIK_WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("GRIK_WEB_PORT", "7777")))

    # --- Modes ---
    text_mode: bool = field(default_factory=lambda: _bool("GRIK_TEXT_MODE", False))
    web_mode: bool = field(default_factory=lambda: _bool("GRIK_WEB_MODE", False))


config = Config()
