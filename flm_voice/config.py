"""Configuration loaded from $XDG_CONFIG_HOME/flm-voice/config.toml."""
from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "flm-voice"


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/flm-voice-{os.getuid()}"
    return Path(base)


def socket_path() -> Path:
    return runtime_dir() / "flm-voice.sock"


@dataclass
class Config:
    endpoint: str = "http://localhost:52625"
    model: str = "whisper-v3:turbo"
    request_timeout_sec: float = 60.0
    language: str | None = None
    languages: list[str] = field(default_factory=lambda: ["ru", "en"])
    sample_rate: int = 16000
    input_device: str | None = None
    outputs: list[str] = field(default_factory=lambda: ["clipboard", "notify"])
    # Phase-6 polish
    max_duration_sec: float = 300.0
    warmup: bool = True
    auto_stop: bool = False
    auto_stop_silence_sec: float = 1.5
    auto_stop_min_record_sec: float = 0.8
    vad_rms_threshold: float = 500.0

    @classmethod
    def load(cls) -> Config:
        path = config_dir() / "config.toml"
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        fields = cls.__dataclass_fields__
        unknown = sorted(set(data) - set(fields))
        if unknown:
            log.warning("ignoring unknown config keys in %s: %s", path, unknown)
        return cls(**{k: v for k, v in data.items() if k in fields})
