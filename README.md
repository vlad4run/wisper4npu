# whisper.npu — hotkey voice-to-text for KDE Plasma Wayland

Press a global hotkey, speak, press again. Audio is transcribed by
Whisper V3 Turbo running on the AMD Ryzen AI NPU and the text lands in
your clipboard (optionally typed into the focused window, with a KDE
notification preview). Headless — no GUI windows; just a daemon, a Unix
socket, and `notify-send`.

## Backend

Transcription runs in [fastflowlm-docker](../ai370.npu/fastflowlm-docker/)
as a long-running OpenAI-compatible API server on port `52625`:

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

See [fastflowlm-docker README](../ai370.npu/fastflowlm-docker/README.md)
for NPU prerequisites, kernel driver setup, and the Docker image build.

## Setup

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

For a binary in `~/.local/bin` instead, use `pipx install .`.

### 3. Run the daemon

In a terminal, or as a systemd `--user` unit
([flm_voice/service/flm-voice.service](flm_voice/service/flm-voice.service)):

```bash
.venv/bin/flm-voice daemon
# or
cp flm_voice/service/flm-voice.service ~/.config/systemd/user/
systemctl --user enable --now flm-voice
```

### 4. Bind hotkeys

```bash
./scripts/install-kde-hotkey.sh   # generates a .desktop launcher
```

Then in **System Settings → Shortcuts → Custom Shortcuts**, bind:

- `Meta+Alt+Space` → `flm-voice toggle` *(start/stop recording)*
- `Meta+Alt+L` → `flm-voice lang next` *(cycle language; notification shows the new value)*

### 5. Talk

Press the hotkey, speak, press again. Transcript goes to the clipboard
and a notification pops up with a preview. Paste with `Ctrl+V`.

## Architecture

```text
   KDE Custom Shortcut (Meta+Alt+Space)
              │ exec
              ▼
       flm-voice toggle ──► Unix socket ──► flm-voice daemon (asyncio)
                                                    │
                                ┌───────────────────┴───────────────────┐
                                ▼                                       ▼
                            Recorder                                Transcriber
                          (sounddevice)                            (httpx → FLM)
                                                                        │
                                                                        ▼
                                                  Output: wl-copy / wtype / notify-send
```

Key choices:

- **Long-lived daemon.** `flm-voice toggle` is a thin client sending one
  JSON line to `$XDG_RUNTIME_DIR/flm-voice.sock`. The daemon holds the
  PortAudio stream and a tiny state machine
  (`IDLE → RECORDING → TRANSCRIBING → IDLE`), so toggle response is
  immediate.
- **No local model.** Transcription is `POST /v1/audio/transcriptions`
  against the FLM container; the NPU integration lives entirely there.
- **Wayland-native I/O.** Clipboard via `wl-copy`, optional keystroke
  injection via `wtype`/`ydotool`, KDE notifications via `notify-send`.
  No X11 assumptions, no display server queries.
- **Safety rails.** A `max_duration_sec` watchdog stops a forgotten
  recording; an opt-in energy-based VAD (`auto_stop = true`) stops
  recording after `auto_stop_silence_sec` of silence following speech.
  A startup warm-up POST primes FLM so the first real transcription
  doesn't pay the cold-load cost.

## Project layout

```text
whisper.npu/
├── pyproject.toml
├── flm_voice/
│   ├── __main__.py             # CLI: daemon | toggle | status | stop | cancel | oneshot | lang
│   ├── config.py               # XDG config + socket path
│   ├── ipc.py                  # line-delimited JSON over Unix socket (client)
│   ├── daemon.py               # asyncio IPC server + state machine + watchdogs
│   ├── recorder.py             # sounddevice → 16kHz mono WAV bytes
│   ├── transcriber.py          # httpx client for FLM serve
│   ├── output.py               # wl-copy / wtype / ydotool / notify-send
│   ├── vad.py                  # energy-based has_speech (pure numpy)
│   └── service/
│       └── flm-voice.service   # systemd --user unit
├── scripts/
│   ├── install-kde-hotkey.sh   # register Custom Shortcut helper
│   └── bench_transcribe.py     # latency smoke test against FLM serve
└── tests/
```

## CLI

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
| `flm-voice lang ru` / `en` / `auto` | Set the language explicitly; `auto` clears the hint so Whisper detects. |

## Configuration

Optional `$XDG_CONFIG_HOME/flm-voice/config.toml`:

```toml
endpoint = "http://localhost:52625"
model = "whisper-v3:turbo"
language = "ru"                       # ISO-639-1; omit for auto-detect
languages = ["ru", "en"]              # cycled by `flm-voice lang next`
sample_rate = 16000
# input_device = "alsa_input.pci-0000_..."
outputs = ["clipboard", "notify"]     # also: "type" (wtype/ydotool)

warmup = true                         # POST a 1s silent WAV at daemon startup
max_duration_sec = 300                # hard cap; auto-stops + transcribes
auto_stop = false                     # opt-in: silence-detection auto-stop
auto_stop_silence_sec = 1.5           # required quiet window after first speech
auto_stop_min_record_sec = 0.8        # never auto-stop in the first N seconds
vad_rms_threshold = 500.0             # higher = needs louder speech
```

## Notes

- **PipeWire vs PortAudio.** `sounddevice` finds PipeWire via the ALSA
  shim on every modern distro this has been tried on. If it ever
  doesn't, the fallback is to spawn `pw-record -f s16 -r 16000 --channels=1 -`
  and read stdout — a ~20-line change in `recorder.py`.
- **Hotkey conflicts.** `Meta+Space` is Krunner. Default suggestion is
  `Meta+Alt+Space`; override with `FLM_VOICE_HOTKEY=` before running the
  install script.
- **FLM container must be up.** The `--restart unless-stopped` flag in
  the docker invocation means it survives reboots. Without it, the
  daemon's first `toggle` will get a clean `FLM unreachable` notification
  and stay idle (it won't crash).

## Development

```bash
.venv/bin/pip install -e .[dev]
.venv/bin/pytest -q
```

## Standalone binary

To produce a single self-contained executable (no Python, no venv required
on the target machine — only `libportaudio.so.2` plus whichever output
tools you use):

```bash
scripts/build-binary.sh
# -> dist/flm-voice  (~30 MB)
```

The script uses PyInstaller in `--onefile` mode. Drop `dist/flm-voice` into
`~/.local/bin/`, point your systemd unit's `ExecStart=` at it, and the
Python source tree is no longer needed at runtime.

## RPM package (openSUSE)

For installing system-wide via the package manager:

```bash
sudo zypper install rpm-build      # one-time
scripts/build-rpm.sh
sudo zypper install ~/rpmbuild/RPMS/x86_64/flm-voice-*.rpm
```

The package installs:

- `/usr/bin/flm-voice` — the PyInstaller binary
- `/usr/lib/systemd/user/flm-voice.service` — systemd user unit
- `/usr/share/doc/packages/flm-voice/README.md`
- `/usr/share/licenses/flm-voice/LICENSE`

Hard dep: `libportaudio2`. Soft deps (`Recommends:`):
`wl-clipboard`, `libnotify-tools`. After install:

```bash
systemctl --user enable --now flm-voice
./scripts/install-kde-hotkey.sh   # prints hotkey-binding steps
```
