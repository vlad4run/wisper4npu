# whisper.npu — voice-to-text overlay for KDE Plasma Wayland

Press a global hotkey, speak, press again. Audio is transcribed by Whisper V3
Turbo running on the AMD Ryzen AI NPU, and the text lands in your clipboard
(and optionally is typed into the focused window).

## Backend

Transcription runs in [fastflowlm-docker](../ai370.npu/fastflowlm-docker/) as
a long-running OpenAI-compatible API server on port `52625`:

```bash
docker run -d --rm \
  --device=/dev/accel/accel0 \
  --ulimit memlock=-1:-1 \
  -v ~/.config/flm:/root/.config/flm \
  -p 52625:52625 \
  --restart unless-stopped \
  fastflowlm serve gemma3:1b --asr 1
```

See [fastflowlm-docker README](../ai370.npu/fastflowlm-docker/README.md) for
the NPU prerequisites, kernel driver setup, and Docker image build.

## Status

**MVP + phase-6 polish working** — phases 1-2 and the safety/UX bits from
phase 6 are implemented. The daemon also auto-stops on a hard duration cap
and (optionally) when the user stops talking; it warms FLM up at startup so
the first real transcription isn't cold. Connection-refused errors against a
not-yet-running FLM container produce a clean WARNING + notification.
Phase 3 (KDE hotkey wiring) and phase 4 (PyQt overlay) are still pending.

## MVP setup

### 1. System packages

```bash
# openSUSE
sudo zypper install wl-clipboard libnotify-tools
# (optional, for keystroke auto-insert) sudo zypper install wtype
```

`notify-send` is usually already present on KDE.

### 2. Python install

```bash
cd /home/vladislav/AI/whisper.npu
python3 -m venv .venv
.venv/bin/pip install -e .
```

For a system-wide binary in `~/.local/bin` instead, use `pipx install .`.

### 3. Start the FLM server (NPU backend)

```bash
docker run -d --rm \
  --device=/dev/accel/accel0 \
  --ulimit memlock=-1:-1 \
  -v ~/.config/flm:/root/.config/flm \
  -p 52625:52625 \
  --restart unless-stopped \
  --name flm-serve \
  fastflowlm serve gemma3:1b --asr 1
```

See [fastflowlm-docker README](../ai370.npu/fastflowlm-docker/README.md).

### 4. Run the daemon

In a terminal (or via the systemd `--user` unit in
[flm_voice/service/flm-voice.service](flm_voice/service/flm-voice.service)):

```bash
.venv/bin/flm-voice daemon
```

### 5. Bind a hotkey

```bash
./scripts/install-kde-hotkey.sh   # generates a .desktop launcher
```

Then follow the printed steps in **System Settings → Shortcuts → Custom
Shortcuts** to bind:

- `Meta+Alt+Space` → `.venv/bin/flm-voice toggle` *(start/stop recording)*
- `Meta+Alt+L` → `.venv/bin/flm-voice lang next` *(cycle language; see notify-send popup for the new value)*

### 6. Talk

Press the hotkey, speak, press again. Transcript lands in the clipboard
and a notification pops up with a preview. Paste with `Ctrl+V`.

## Implementation plan

### Architecture

```text
   KDE Custom Shortcut (Meta+Alt+Space)
              │ exec
              ▼
       flm-voice toggle ──► Unix socket ──► flm-voice daemon (QApplication)
                                                    │
                                ┌───────────────────┼───────────────────┐
                                ▼                   ▼                   ▼
                            Recorder           Overlay UI          Transcriber
                        (sounddevice)        (PyQt6 frameless)   (httpx → FLM)
                                                                       │
                                                                       ▼
                                                    Output: wl-copy / wtype / notify
```

Key decisions:

- **Long-lived daemon, not fork-and-die per keypress.** `flm-voice toggle` is
  a thin client that sends one JSON line to a Unix socket in
  `$XDG_RUNTIME_DIR/flm-voice.sock`. The daemon holds the `QApplication` event
  loop, PortAudio stream, and overlay windows — so toggle response is
  immediate (no PyQt cold start per shot).
- **No local model.** Transcription is an HTTP POST to FastFlowLM's
  `/v1/audio/transcriptions`. The NPU integration is entirely owned by the
  container; our Python only deals with audio capture and UX.
- **State machine in the daemon:** `IDLE → RECORDING → TRANSCRIBING → IDLE`.
  `toggle` from `RECORDING` stops the stream and dispatches transcription;
  from `TRANSCRIBING` it is ignored (with a notification).
- **Wayland-native I/O:** `wl-copy` for clipboard, `wtype`/`ydotool` for
  keystroke synthesis, KDE notifications via `notify-send`. No X11
  assumptions anywhere.

### Project layout

```text
whisper.npu/
├── pyproject.toml
├── flm_voice/
│   ├── __main__.py             # CLI: daemon | toggle | status | stop | oneshot
│   ├── config.py               # XDG config + socket path
│   ├── ipc.py                  # line-delimited JSON over Unix socket (client)
│   ├── daemon.py               # QApplication + asyncio IPC server + state machine
│   ├── recorder.py             # sounddevice → 16kHz mono WAV bytes
│   ├── transcriber.py          # httpx client for FLM serve
│   ├── output.py               # wl-copy / wtype / ydotool / notify-send
│   ├── overlay/
│   │   ├── indicator.py        # frameless always-on-top recording indicator
│   │   └── result.py           # result window with Copy / Insert / Edit
│   └── service/
│       └── flm-voice.service   # systemd --user unit
├── scripts/
│   ├── install-kde-hotkey.sh   # register Custom Shortcut helper
│   └── bench_transcribe.py     # latency smoke test against FLM serve
└── tests/
```

### Phases

- **Phase 0** — Smoke test FLM `/v1/audio/transcriptions` latency from Python.
  *(`scripts/bench_transcribe.py`)*
- **Phase 1** — Recorder + Transcriber; `flm-voice oneshot` works end-to-end.
  *(`recorder.py`, `transcriber.py`)*
- **Phase 2** — Daemon + IPC; `flm-voice toggle` works from another terminal.
  *(`daemon.py`, `ipc.py`, `__main__.py`)*
- **Phase 3** — KDE Custom Shortcut + systemd `--user` unit.
  *(`service/`, `scripts/install-kde-hotkey.sh`)*
- **Phase 4** — PyQt6 overlay (recording indicator + result window).
  *(`overlay/indicator.py`, `overlay/result.py`)*
- **Phase 5** — Output backends wired into the daemon.
  *(`output.py`)*
- **Phase 6** *(partially done)* — energy-based VAD auto-stop, max-duration
  cap, FLM warm-up, live language switching via `flm-voice lang`. Tray icon
  is still TODO (depends on PyQt from phase 4).

### Minimal MVP

Phases 0-3 + clipboard-only output: press hotkey, see a notification
"recording", press again, get transcript in the clipboard. Overlay UI (phase
4) can land later.

### Risks / open questions

1. **PortAudio + PipeWire** — `sounddevice` usually finds PipeWire via the
   ALSA shim. Fallback: `subprocess.Popen(["pw-record", ...])` reading stdout.
2. **`WindowStaysOnTopHint` under KWin Wayland** is unreliable for some hint
   combinations. If it fails for the indicator, replace just the indicator
   with a GTK4 + `gtk4-layer-shell` window; keep the result window in PyQt.
3. **Hotkey conflicts** — `Meta+Space` is Krunner. Default to
   `Meta+Alt+Space`; configurable via `FLM_VOICE_HOTKEY` in the install
   script.
4. **FLM container uptime** — make the docker run `--restart unless-stopped`
   (see [Backend](#backend) snippet) so the daemon's first POST always finds
   a server.

## Configuration

Optional `$XDG_CONFIG_HOME/flm-voice/config.toml`:

```toml
endpoint = "http://localhost:52625"
model = "whisper-v3:turbo"
language = "ru"                       # ISO-639-1; omit or set to nothing for auto-detect
languages = ["ru", "en"]              # cycled by `flm-voice lang next`; add "auto" to include auto-detect
sample_rate = 16000
# input_device = "alsa_input.pci-0000_..."
outputs = ["clipboard", "notify"]     # also: "type" (wtype/ydotool)

# Phase-6 polish
warmup = true                         # POST a 1s silent WAV at daemon startup
max_duration_sec = 300                # hard cap; auto-stops + transcribes
auto_stop = false                     # opt-in: silence-detection auto-stop
auto_stop_silence_sec = 1.5           # required quiet window after first speech
auto_stop_min_record_sec = 0.8        # never auto-stop in the first N seconds
vad_rms_threshold = 500.0             # higher = needs louder speech
```

## CLI reference

| Command | What it does |
| --- | --- |
| `flm-voice daemon` | Run the long-lived daemon in the foreground (for systemd or a terminal). |
| `flm-voice toggle` | Start recording if idle; stop and transcribe if recording. |
| `flm-voice status` | Print the daemon state as JSON. |
| `flm-voice cancel` | Discard the current recording without transcribing. |
| `flm-voice stop` | Tell the daemon to exit cleanly. |
| `flm-voice oneshot --duration 5` | Record N seconds and print the transcript (no daemon). |
| `flm-voice lang` | Show the current transcription language. |
| `flm-voice lang next` | Cycle to the next language in `cfg.languages`. |
| `flm-voice lang ru` / `lang en` / `lang auto` | Set the language explicitly. `auto` clears the hint and lets Whisper detect. |

## Development

```bash
.venv/bin/pip install -e .[dev]
.venv/bin/pytest -q
```
