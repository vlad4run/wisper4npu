"""Recorder buffer helpers — no real microphone needed."""
from __future__ import annotations

import numpy as np

from flm_voice.recorder import Recorder, silent_wav


def test_silent_wav_has_correct_header_and_length() -> None:
    wav = silent_wav(1.0, sample_rate=16000)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    # 16-bit mono 16kHz, 1s = 32000 PCM bytes + 44-byte header
    assert len(wav) == 44 + 32000


def test_peek_recent_returns_tail() -> None:
    rec = Recorder(sample_rate=16000)
    # 3 chunks of 0.1s each = 0.3s total
    for value in (1, 2, 3):
        rec._chunks.append(
            np.full((1600, 1), fill_value=value, dtype=np.int16)
        )
    assert rec.current_duration() == 0.3

    last_100ms = rec.peek_recent(0.1)
    assert last_100ms.shape == (1600,)
    assert (last_100ms == 3).all()

    last_200ms = rec.peek_recent(0.2)
    assert last_200ms.shape == (3200,)
    assert (last_200ms[:1600] == 2).all()
    assert (last_200ms[1600:] == 3).all()


def test_peek_recent_empty_when_no_chunks() -> None:
    rec = Recorder()
    assert rec.peek_recent(1.0).size == 0
    assert rec.current_duration() == 0.0
