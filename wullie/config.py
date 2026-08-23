"""Central configuration, read from the environment (.env)."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- Brain (the LLM that IS Wullie) ---
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    brain_model: str = field(default_factory=lambda: os.getenv("WULLIE_BRAIN_MODEL", "claude-sonnet-4-6"))

    # --- Voice: wake word (OpenWakeWord) ---
    wake_model_paths: list[str] = field(default_factory=lambda: [
        p.strip() for p in os.getenv("WULLIE_WAKE_MODELS", "").split(",") if p.strip()
    ])
    wake_framework: str = field(default_factory=lambda: os.getenv("WULLIE_WAKE_FRAMEWORK", "onnx"))
    wake_sensitivity: float = field(default_factory=lambda: float(os.getenv("WULLIE_WAKE_SENSITIVITY", "0.5")))

    # --- Voice: speech to text (local faster-whisper) ---
    stt_model: str = field(default_factory=lambda: os.getenv("WULLIE_STT_MODEL", "base.en"))
    stt_device: str = field(default_factory=lambda: os.getenv("WULLIE_STT_DEVICE", "auto"))

    # --- Voice: text to speech ---
    # "piper"      = local neural TTS via piper-tts (free, has a Scottish voice);
    # "elevenlabs" = server-side ElevenLabs synth (paid voice quality);
    # "browser"    = web UI uses the browser's Web Speech API, voice loop silent;
    # "off"        = TTS disabled everywhere.
    tts_mode: str = field(default_factory=lambda: os.getenv("WULLIE_TTS_MODE", "piper").lower())
    piper_voice_path: str = field(default_factory=lambda: os.getenv("WULLIE_PIPER_VOICE_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voices", "en_GB-alba-medium.onnx")))
    # For multi-speaker Piper voices like en_GB-vctk-medium. Value is the speaker key from the .onnx.json (e.g. "p241"). Ignored for single-speaker voices.
    piper_speaker: str = field(default_factory=lambda: os.getenv("WULLIE_PIPER_SPEAKER", ""))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.getenv("WULLIE_VOICE_ID", ""))
    elevenlabs_model: str = field(default_factory=lambda: os.getenv("WULLIE_TTS_MODEL", "eleven_turbo_v2_5"))

    # --- Brain: persistent memory (file the LLM reads/writes across restarts) ---
    memory_path: str = field(default_factory=lambda: os.getenv("WULLIE_MEMORY_PATH", os.path.expanduser("~/.wullie/memory.md")))

    # --- Agent orchestration (Docker) ---
    docker_network: str = field(default_factory=lambda: os.getenv("WULLIE_DOCKER_NETWORK", "wullie-net"))
    base_agent_image: str = field(default_factory=lambda: os.getenv("WULLIE_BASE_AGENT_IMAGE", "wullie-base-agent:latest"))
    agent_call_timeout: int = field(default_factory=lambda: int(os.getenv("WULLIE_AGENT_TIMEOUT", "120")))
    allow_provisioning: bool = field(default_factory=lambda: _bool("WULLIE_ALLOW_PROVISIONING", True))

    # --- Web interface ---
    web_host: str = field(default_factory=lambda: os.getenv("WULLIE_WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("WULLIE_WEB_PORT", "7777")))

    # --- Modes ---
    text_mode: bool = field(default_factory=lambda: _bool("WULLIE_TEXT_MODE", False))
    web_mode: bool = field(default_factory=lambda: _bool("WULLIE_WEB_MODE", False))


config = Config()
