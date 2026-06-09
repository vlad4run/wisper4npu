# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`flm-voice`: hotkey voice-to-text for KDE Plasma Wayland. A KDE global shortcut
runs `flm-voice toggle`; a long-lived daemon records the mic, ships the audio to
a **FastFlowLM (FLM) container** that runs Whisper V3 Turbo on an AMD Ryzen AI
NPU, and drops the transcript into the clipboard / focused window / a KDE
notification. Headless: no GUI, just a daemon + Unix socket + `notify-send`.

## Commands

```bash
.venv/bin/pip install -e .[dev]        # dev install (pytest, ruff)
.venv/bin/pytest -q                    # run tests
.venv/bin/pytest tests/test_vad.py::test_name   # single test
.venv/bin/ruff check .                 # lint (E,F,I,B,UP,RUF; line-length 100)
.venv/bin/ruff format .                # format

scripts/bench_transcribe.py            # latency smoke test vs a running FLM
scripts/build-binary.sh                # PyInstaller --onefile -> dist/flm-voice (~30MB)
scripts/build-rpm.sh                   # openSUSE RPM -> ~/rpmbuild/RPMS/x86_64/
```

Runtime CLI: `flm-voice daemon|toggle|status|stop|cancel|oneshot|lang`. See
README for the full table. Tests use `pytest-asyncio` in `asyncio_mode = auto`.

## Architecture

Two processes, split across a Unix socket at `$XDG_RUNTIME_DIR/flm-voice.sock`:

- **Thin client** (`ipc.py`, invoked by `toggle`/`status`/`stop`/`cancel`/`lang`):
  sends one line-delimited JSON command, reads one JSON reply, exits. No state.
  Exit code 2 if the daemon socket is absent/refused.
- **Daemon** (`daemon.py`): asyncio Unix-socket server owning the `Recorder` and
  a state machine `IDLE → RECORDING → TRANSCRIBING → IDLE`. A single
  `asyncio.Lock` serializes every command in `handle_command`.

Request flow: `toggle` → daemon records (`recorder.py`, sounddevice stream) →
on second `toggle` stops and POSTs WAV bytes to FLM (`transcriber.py`, httpx →
`/v1/audio/transcriptions`) → result fans out to `output.py` backends.

Key invariants worth knowing before editing:

- **No local model.** All NPU/Whisper work lives in the FLM container; this repo
  only HTTP-POSTs WAV bytes. The container is a sibling repo:
  `../fastflowlm-docker/`. Started via `deploy/compose.yaml` on port
  `52625`. If it's down, the daemon notifies "FLM unreachable" and stays idle —
  it does not crash.
- **Blocking I/O is offloaded.** sounddevice `start`/`stop` are sync and run via
  `asyncio.to_thread`; transcription uses the async httpx client. Don't call
  blocking audio APIs directly on the event loop.
- **Lazy async primitives.** `Daemon._lock`/`_stop_event` are created on first
  property access, so a `Daemon` can be constructed outside a running loop
  (tests rely on this). Don't move them into `__init__`.
- **Watchdogs.** Two background tasks may auto-stop a recording:
  `_max_duration_watchdog` (hard cap, always on) and `_vad_watchdog` (energy VAD,
  opt-in via `auto_stop`). Both are torn down together by `_cancel_watchdogs()`,
  which skips the currently-running task to avoid self-cancellation.
- **`oneshot` bypasses the daemon entirely** — synchronous `record_to_wav` +
  `transcribe_sync`, no socket, no state machine.
- **Output backends** (`output.py`): `clipboard` (wl-copy) and `type`
  (wtype/ydotool) raise `RuntimeError` when their tool is missing so the daemon
  logs it; `notify` (notify-send) is best-effort and silently no-ops.

## Config

`Config` dataclass (`config.py`) loaded from
`$XDG_CONFIG_HOME/flm-voice/config.toml`; unknown keys are warned-and-ignored.
Defaults are usable with no config file. Full key reference is in README.

## Hardware constraint (don't re-investigate)

The NPU has **8 columns**, and Whisper V3 Turbo alone consumes the whole budget.
Confirmed on Strix Point HX 370 that **no LLM fits alongside Whisper** in one FLM
container — not even the smallest catalog model, and `--pmode turbo` doesn't
help. This is harmless for flm-voice (transcription is unaffected). To also use
`/v1/chat/completions`, run a *second* FLM container without `--asr 1`. See the
troubleshooting table in `SETUP.md` for the exact error signatures.
