"""Energy-based VAD smoke tests."""
from __future__ import annotations

import numpy as np

from flm_voice import vad


def test_silence_is_not_speech() -> None:
    silence = np.zeros(8000, dtype=np.int16)
    assert vad.rms(silence) == 0.0
    assert not vad.has_speech(silence)


def test_loud_signal_is_speech() -> None:
    t = np.arange(8000, dtype=np.float32) / 16000
    tone = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16)
    assert vad.rms(tone) > 1000
    assert vad.has_speech(tone)


def test_quiet_noise_below_threshold() -> None:
    rng = np.random.default_rng(0)
    quiet = (rng.standard_normal(8000) * 50).astype(np.int16)
    assert not vad.has_speech(quiet, threshold=500.0)


def test_empty_window_is_silent() -> None:
    assert vad.rms(np.zeros(0, dtype=np.int16)) == 0.0
    assert not vad.has_speech(np.zeros(0, dtype=np.int16))
