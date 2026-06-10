# Disable debug subpackage — we ship a pre-built PyInstaller binary with
# no extractable debug symbols.
%global debug_package %{nil}

Name:           wayscribe
Version:        0.2.0
Release:        1%{?dist}
Summary:        Hotkey voice-to-text for KDE Plasma Wayland (Whisper on AMD NPU)
License:        MIT

# Sources are staged by scripts/build-rpm.sh into %%{_topdir}/SOURCES.
Source0:        wayscribe
Source1:        wayscribe.service
Source2:        LICENSE
Source3:        README.md
Source4:        config.example.toml
Source5:        BACKEND.md
# NPU backend: docker-compose for the FastFlowLM (Whisper-on-NPU) container.
Source6:        compose.yaml
Source7:        env.example

# Pre-built x86_64 binary; do not mark noarch.
ExclusiveArch:  x86_64

Requires:       libportaudio2
Recommends:     wl-clipboard
Recommends:     libnotify-tools

%description
wayscribe is a headless voice-to-text daemon for KDE Plasma Wayland. A
global hotkey starts and stops recording; audio is transcribed by Whisper
V3 Turbo running on the AMD Ryzen AI NPU (via FastFlowLM) and the result
lands in the clipboard, with a KDE notification preview.

The Whisper inference engine itself runs in a separate FastFlowLM Docker
container (not packaged here); see the project README for setup of the
NPU backend and KDE hotkey bindings.

%prep
%setup -q -T -c -n %{name}-%{version}
cp -p %{SOURCE2} LICENSE
cp -p %{SOURCE3} README.md
cp -p %{SOURCE4} config.example.toml
cp -p %{SOURCE5} BACKEND.md
# NPU backend compose, shipped as %%doc deploy-npu/ (see BACKEND.md)
mkdir -p deploy-npu
cp -p %{SOURCE6} deploy-npu/compose.yaml
cp -p %{SOURCE7} deploy-npu/.env.example

%install
install -D -m 0755 %{SOURCE0} %{buildroot}%{_bindir}/wayscribe
install -D -m 0644 %{SOURCE1} %{buildroot}%{_userunitdir}/wayscribe.service

%files
%license LICENSE
%doc README.md
%doc BACKEND.md
%doc config.example.toml
# NPU backend compose (FastFlowLM / Whisper-on-NPU)
%doc deploy-npu
%{_bindir}/wayscribe
%{_userunitdir}/wayscribe.service

%changelog
* Wed Jun 10 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.2.0-1
- Add `wayscribe doctor` self-diagnosis command
- status reports backend reachability; warmup notifies on a down backend
- Probe backend outside the daemon state lock

* Mon Jun 09 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.1.0-1
- Default language ru; follow KDE keyboard layout by default
- Ship config.example.toml reference

* Thu May 28 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.1.0-1
- Initial RPM: PyInstaller-bundled binary + systemd user unit
