# Setup on a new machine

Quick-reference checklist. Detailed background lives in [README.md](README.md)
and [../fastflowlm-docker/README.md](../fastflowlm-docker/README.md).

## 0. Hardware / OS prerequisites

```bash
# AMD Ryzen AI NPU present + driver loaded
lsmod | grep amdxdna                         # expect a match
ls -la /dev/accel/accel0                     # expect crw-rw---- root:render
ls /lib/firmware/amdnpu/                     # expect firmware files

# Kernel new enough (>= 6.11)
uname -r

# Render group + your user
getent group render                          # note the GID
id | grep -q render || sudo usermod -aG render $USER && newgrp render
```

If `/dev/accel/accel0` is missing, follow the host-side install in
[fastflowlm-docker README](../fastflowlm-docker/README.md).

## 1. System packages (openSUSE)

```bash
sudo zypper install \
    docker docker-compose \
    rpm-build \
    libportaudio2 wl-clipboard libnotify-tools \
    python3 python3-pip python3-virtualenv
sudo systemctl enable --now docker
sudo usermod -aG docker $USER && newgrp docker
```

memlock unlimited (one-time, needs reboot):

```bash
echo -e "* soft memlock unlimited\n* hard memlock unlimited" | sudo tee -a /etc/security/limits.conf
sudo reboot
```

## 2. Build the FLM container image

```bash
cd ~/AI/ai370.npu/fastflowlm-docker
docker build -t fastflowlm .       # ~15-25 min
docker run --rm --device=/dev/accel/accel0 --ulimit memlock=-1:-1 fastflowlm validate
```

## 3. Start the FLM backend

```bash
cd ~/AI/ai370.npu/whisper.npu/deploy
cp .env.example .env
# Edit RENDER_GID in .env to the actual host value:
sed -i "s/^RENDER_GID=.*/RENDER_GID=$(getent group render | cut -d: -f3)/" .env

docker compose up -d
docker compose logs -f       # wait for "WebServer started on port 52625"; Ctrl-C
```

First run downloads ~625 MB into `~/.config/flm/` (root-owned via the
container; `sudo chown -R $USER ~/.config/flm` if you want to inspect).

## 4. Build & install flm-voice

Pick **one** path.

### 4a. From source (development)

```bash
cd ~/AI/ai370.npu/whisper.npu
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pytest -q              # 18 passed
.venv/bin/flm-voice oneshot --duration 3   # smoke test: speak, see transcript
```

Then create the user systemd unit:

```bash
mkdir -p ~/.config/systemd/user
cp flm_voice/service/flm-voice.service ~/.config/systemd/user/
# Edit ExecStart= to point at the venv binary:
sed -i "s|%h/.local/bin/flm-voice|$PWD/.venv/bin/flm-voice|" ~/.config/systemd/user/flm-voice.service
systemctl --user daemon-reload
systemctl --user enable --now flm-voice
```

### 4b. From RPM (deployment)

```bash
cd ~/AI/ai370.npu/whisper.npu
scripts/build-rpm.sh
sudo zypper install ~/rpmbuild/RPMS/x86_64/flm-voice-*.rpm
systemctl --user enable --now flm-voice
```

## 5. Bind KDE hotkeys

```bash
~/AI/ai370.npu/whisper.npu/scripts/install-kde-hotkey.sh
```

Follow the printed steps in **System Settings → Shortcuts → Custom
Shortcuts**:

- `Meta+Alt+Space` → `flm-voice toggle`
- `Meta+Alt+L`     → `flm-voice lang next` (optional)

## 6. Smoke test the full stack

```bash
flm-voice status              # {"ok": true, "state": "idle", "language": "auto"}
flm-voice toggle              # press hotkey, speak 3 sec, hotkey again
wl-paste                      # transcript should be in the clipboard
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `flm-voice daemon not running` | Daemon not started | `systemctl --user start flm-voice` |
| `FLM unreachable at http://localhost:52625` | Container down | `cd ~/AI/ai370.npu/whisper.npu/deploy && docker compose ps` |
| `Permission denied` on `~/.config/flm` | SELinux label | Already handled by `:z` in compose; check `ls -lZ ~/.config/flm` |
| `Unable to find group render` (docker) | `group_add` used name, not GID | Confirm `RENDER_GID` in `deploy/.env` matches `getent group render` |
| `WebServer started on port 52625` but `curl localhost:52625` is refused | FLM defaults `--host 127.0.0.1` (container loopback); Docker can't forward to that | Add `--host 0.0.0.0` to the serve command (already in `deploy/compose.yaml`) |
| `Failed to load default model: <any LLM>` + `DRM_IOCTL_AMDXDNA_CREATE_HWCTX failed` | NPU has 8 columns; Whisper alone consumes the budget. Confirmed on Strix Point HX 370 that **no LLM fits alongside Whisper** — even the smallest catalog entry (qwen3:0.6b, 0.4 GB) and changing `--pmode turbo` don't help. Hardware constraint. | Harmless for flm-voice (Whisper transcription is unaffected; the server still starts on :52625 and `/v1/audio/transcriptions` works). If you want the `/v1/chat/completions` endpoint instead, run a second container without `--asr 1`. |
| Transcription empty | Mic muted / wrong source | `pactl list sources short`; pick one and set `input_device` in `~/.config/flm-voice/config.toml` |
| Clipboard not updated | `wl-clipboard` missing | `sudo zypper install wl-clipboard` |
