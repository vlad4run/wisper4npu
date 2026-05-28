"""Long-lived daemon: asyncio Unix-socket server + state machine.

Owns the Recorder, dispatches transcription, and feeds output backends
(clipboard / keystroke synthesis / KDE notifications). Headless — no GUI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from enum import Enum
from typing import Any

import httpx

from flm_voice import output, vad
from flm_voice.config import Config, socket_path
from flm_voice.recorder import Recorder, silent_wav
from flm_voice.transcriber import transcribe_async

log = logging.getLogger("flm-voice")


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class Daemon:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.state = State.IDLE
        self.recorder = Recorder(sample_rate=cfg.sample_rate, device=cfg.input_device)
        self._lock: asyncio.Lock | None = None
        self._stop_event: asyncio.Event | None = None
        self._inflight: asyncio.Task[None] | None = None
        self._max_duration_task: asyncio.Task[None] | None = None
        self._vad_task: asyncio.Task[None] | None = None

    def _ensure_async_primitives(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

    @property
    def lock(self) -> asyncio.Lock:
        self._ensure_async_primitives()
        assert self._lock is not None
        return self._lock

    @property
    def stop_event(self) -> asyncio.Event:
        self._ensure_async_primitives()
        assert self._stop_event is not None
        return self._stop_event

    def _status_snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        snap: dict[str, Any] = {
            "ok": True,
            "state": self.state.value,
            "language": self.cfg.language or "auto",
        }
        if extra:
            snap.update(extra)
        return snap

    def _set_language(self, value: str | None) -> str:
        if value is None or value == "auto":
            self.cfg.language = None
        else:
            self.cfg.language = value
        display = self.cfg.language or "auto"
        output.notify("flm-voice", f"language: {display}")
        log.info("language set to %s", display)
        return display

    def _cycle_language(self) -> str:
        langs = self.cfg.languages or []
        if not langs:
            return self.cfg.language or "auto"
        current = self.cfg.language or "auto"
        try:
            idx = langs.index(current)
        except ValueError:
            idx = -1
        next_value = langs[(idx + 1) % len(langs)]
        return self._set_language(next_value)

    async def handle_command(self, msg: dict[str, Any]) -> dict[str, Any]:
        cmd = msg.get("cmd", "")
        async with self.lock:
            if cmd == "status":
                return self._status_snapshot()

            if cmd == "stop":
                self.stop_event.set()
                return self._status_snapshot({"stopping": True})

            if cmd == "cancel":
                if self.state == State.RECORDING:
                    self._cancel_watchdogs()
                    await asyncio.to_thread(self.recorder.stop)
                    self.state = State.IDLE
                    output.notify("flm-voice", "cancelled")
                return self._status_snapshot()

            if cmd == "toggle":
                if self.state == State.IDLE:
                    return await self._start_recording_locked()
                if self.state == State.RECORDING:
                    return await self._stop_and_dispatch_locked(reason="toggle")
                output.notify("flm-voice", "still transcribing previous recording…")
                return self._status_snapshot({"ok": False, "reason": "busy"})

            if cmd == "lang_set":
                self._set_language(msg.get("value"))
                return self._status_snapshot()

            if cmd == "lang_next":
                self._cycle_language()
                return self._status_snapshot()

            return {"ok": False, "error": f"unknown command: {cmd!r}"}

    async def _start_recording_locked(self) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self.recorder.start)
        except Exception as exc:
            log.exception("recorder failed to start")
            output.notify("flm-voice", f"mic error: {exc}", icon="dialog-error")
            return {"ok": False, "error": str(exc)}
        self.state = State.RECORDING
        output.notify("flm-voice", "recording…", icon="audio-input-microphone")
        self._max_duration_task = asyncio.create_task(self._max_duration_watchdog())
        if self.cfg.auto_stop:
            self._vad_task = asyncio.create_task(self._vad_watchdog())
        return self._status_snapshot()

    async def _stop_and_dispatch_locked(self, reason: str) -> dict[str, Any]:
        self._cancel_watchdogs()
        wav = await asyncio.to_thread(self.recorder.stop)
        self.state = State.TRANSCRIBING
        log.info("captured %d bytes (reason=%s)", len(wav), reason)
        self._inflight = asyncio.create_task(self._transcribe_and_output(wav))
        return self._status_snapshot({"bytes": len(wav), "reason": reason})

    def _cancel_watchdogs(self) -> None:
        current = asyncio.current_task()
        for attr in ("_max_duration_task", "_vad_task"):
            task = getattr(self, attr)
            if task is not None and task is not current and not task.done():
                task.cancel()
            setattr(self, attr, None)

    async def _max_duration_watchdog(self) -> None:
        try:
            await asyncio.sleep(self.cfg.max_duration_sec)
        except asyncio.CancelledError:
            return
        async with self.lock:
            if self.state != State.RECORDING:
                return
            log.info("max duration %.1fs reached, auto-stopping", self.cfg.max_duration_sec)
            output.notify("flm-voice", f"max duration reached ({int(self.cfg.max_duration_sec)}s)")
            await self._stop_and_dispatch_locked(reason="max-duration")

    async def _vad_watchdog(self) -> None:
        speech_seen = False
        silence_sec = self.cfg.auto_stop_silence_sec
        min_record = self.cfg.auto_stop_min_record_sec
        threshold = self.cfg.vad_rms_threshold
        try:
            while True:
                await asyncio.sleep(0.2)
                if self.state != State.RECORDING:
                    return
                duration = self.recorder.current_duration()
                if duration < min_record:
                    continue
                recent = self.recorder.peek_recent(0.5)
                if vad.has_speech(recent, threshold=threshold):
                    speech_seen = True
                    continue
                if not speech_seen:
                    continue
                window = self.recorder.peek_recent(silence_sec)
                if vad.has_speech(window, threshold=threshold):
                    continue
                async with self.lock:
                    if self.state != State.RECORDING:
                        return
                    log.info("VAD: %.1fs silence, auto-stopping", silence_sec)
                    await self._stop_and_dispatch_locked(reason="vad")
                return
        except asyncio.CancelledError:
            return

    async def _transcribe_and_output(self, wav: bytes) -> None:
        try:
            text = await transcribe_async(wav, self.cfg)
        except httpx.ConnectError as exc:
            log.warning("FLM unreachable at %s: %s", self.cfg.endpoint, exc)
            output.notify(
                "flm-voice", f"FLM unreachable ({self.cfg.endpoint})", icon="dialog-error"
            )
            self.state = State.IDLE
            return
        except Exception as exc:
            log.exception("transcription failed")
            output.notify("flm-voice", f"transcription failed: {exc}", icon="dialog-error")
            self.state = State.IDLE
            return
        text = (text or "").strip()
        if not text:
            output.notify("flm-voice", "(empty transcription)")
            self.state = State.IDLE
            return
        for backend in self.cfg.outputs:
            try:
                if backend == "clipboard":
                    output.to_clipboard(text)
                elif backend == "type":
                    output.type_text(text)
                elif backend == "notify":
                    preview = text if len(text) < 200 else text[:197] + "…"
                    output.notify("flm-voice", preview)
            except Exception:
                log.exception("output backend %r failed", backend)
        log.info("transcribed %d chars", len(text))
        self.state = State.IDLE

    async def warmup(self) -> None:
        if not self.cfg.warmup:
            return
        try:
            wav = silent_wav(1.0, sample_rate=self.cfg.sample_rate)
            await transcribe_async(wav, self.cfg)
            log.info("FLM warmup OK")
        except httpx.ConnectError:
            log.warning("FLM warmup skipped: %s not reachable", self.cfg.endpoint)
        except Exception as exc:
            log.warning("FLM warmup failed: %s", exc)


async def _client_handler(
    daemon: Daemon,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        line = await reader.readline()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            resp: dict[str, Any] = {"ok": False, "error": f"bad json: {exc}"}
        else:
            if not isinstance(msg, dict):
                resp = {"ok": False, "error": "request must be a JSON object"}
            else:
                resp = await daemon.handle_command(msg)
    except Exception as exc:
        log.exception("handler error")
        resp = {"ok": False, "error": str(exc)}
    try:
        writer.write(json.dumps(resp).encode() + b"\n")
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _serve(daemon: Daemon) -> None:
    sock = socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(
        lambda r, w: _client_handler(daemon, r, w),
        path=str(sock),
    )
    log.info("listening on %s", sock)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop_event.set)

    warmup_task = asyncio.create_task(daemon.warmup())

    try:
        async with server:
            await daemon.stop_event.wait()
    finally:
        daemon._cancel_watchdogs()
        await _drain_task(warmup_task)
        await _drain_task(daemon._inflight)
        if daemon.recorder.is_recording:
            await asyncio.to_thread(daemon.recorder.stop)
        sock.unlink(missing_ok=True)
        log.info("daemon exited")


async def _drain_task(task: asyncio.Task[Any] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.load()
    daemon = Daemon(cfg)
    try:
        asyncio.run(_serve(daemon))
    except KeyboardInterrupt:
        return 0
    return 0
