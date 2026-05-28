"""Energy-based voice-activity detection.

Pure numpy, no extra deps. Compares the RMS of the input window to a fixed
threshold. Good enough for "is the user talking right now?" decisions in
reasonably quiet rooms; tune `vad_rms_threshold` in config for noisy ones.
"""
from __future__ import annotations

import numpy as np


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))


def has_speech(samples: np.ndarray, threshold: float = 500.0) -> bool:
    return rms(samples) >= threshold
