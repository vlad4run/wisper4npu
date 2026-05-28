"""Microphone capture via sounddevice. Produces 16kHz mono 16-bit PCM WAV bytes."""
from __future__ import annotations

import io
import logging
import threading
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


def _to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.astype(np.int16, copy=False).tobytes())
    return buf.getvalue()


def silent_wav(duration: float, sample_rate: int = 16000) -> bytes:
    samples = np.zeros(int(duration * sample_rate), dtype=np.int16)
    return _to_wav_bytes(samples, sample_rate)


def record_to_wav(
    duration: float,
    sample_rate: int = 16000,
    device: str | int | None = None,
) -> bytes:
    frames = int(duration * sample_rate)
    data = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device,
        blocking=True,
    )
    return _to_wav_bytes(data.reshape(-1), sample_rate)


class Recorder:
    """Stream-based microphone capture.

    Call `start()` to open the input stream; `stop()` returns accumulated WAV
    bytes. Thread-safe — the sounddevice callback runs in PortAudio's audio
    thread and only appends to a list under a lock.
    """

    def __init__(self, sample_rate: int = 16000, device: str | int | None = None) -> None:
        self.sample_rate = sample_rate
        self.device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def current_duration(self) -> float:
        with self._lock:
            total = sum(c.size for c in self._chunks)
        return total / self.sample_rate

    def peek_recent(self, seconds: float) -> np.ndarray:
        target = int(seconds * self.sample_rate)
        with self._lock:
            chunks = list(self._chunks)
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        flat = np.concatenate([c.reshape(-1) for c in chunks])
        if flat.size > target:
            flat = flat[-target:]
        return flat

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                device=self.device,
                callback=self._callback,
            )
            try:
                stream.start()
            except Exception:
                stream.close()
                raise
            self._stream = stream

    def stop(self) -> bytes:
        with self._lock:
            stream = self._stream
            self._stream = None
            chunks = self._chunks
            self._chunks = []
        if stream is not None:
            stream.stop()
            stream.close()
        if not chunks:
            return _to_wav_bytes(np.zeros(0, dtype=np.int16), self.sample_rate)
        data = np.concatenate(chunks).reshape(-1)
        return _to_wav_bytes(data, self.sample_rate)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.warning("sounddevice status: %s", status)
        self._chunks.append(indata.copy())
