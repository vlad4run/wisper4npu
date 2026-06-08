"""HTTP client for FastFlowLM `/v1/audio/transcriptions` (OpenAI-compatible)."""
from __future__ import annotations

import httpx

from flm_voice.config import Config


def transcribe_sync(wav: bytes, cfg: Config | None = None) -> str:
    cfg = cfg or Config.load()
    files = {"file": ("audio.wav", wav, "audio/wav")}
    data: dict[str, str] = {"model": cfg.model}
    if cfg.language:
        data["language"] = cfg.language
    with httpx.Client(base_url=cfg.endpoint, timeout=cfg.request_timeout_sec) as client:
        r = client.post("/v1/audio/transcriptions", files=files, data=data)
        r.raise_for_status()
        return r.json().get("text", "")


async def transcribe_async(wav: bytes, cfg: Config | None = None) -> str:
    cfg = cfg or Config.load()
    files = {"file": ("audio.wav", wav, "audio/wav")}
    data: dict[str, str] = {"model": cfg.model}
    if cfg.language:
        data["language"] = cfg.language
    async with httpx.AsyncClient(base_url=cfg.endpoint, timeout=cfg.request_timeout_sec) as client:
        r = await client.post("/v1/audio/transcriptions", files=files, data=data)
        r.raise_for_status()
        return r.json().get("text", "")
