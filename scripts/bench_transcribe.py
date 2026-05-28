"""Smoke test: record N seconds, POST to FLM, print round-trip latency.

Usage:
    python -m scripts.bench_transcribe --duration 5
"""
from __future__ import annotations

import argparse
import time

from flm_voice.recorder import record_to_wav
from flm_voice.transcriber import transcribe_sync


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--duration", type=float, default=5.0)
    args = p.parse_args()

    print(f"Recording {args.duration}s...")
    wav = record_to_wav(duration=args.duration)
    print(f"Captured {len(wav)} bytes, sending to FLM...")

    t0 = time.perf_counter()
    text = transcribe_sync(wav)
    dt = time.perf_counter() - t0
    print(f"Transcribed in {dt:.2f}s: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
