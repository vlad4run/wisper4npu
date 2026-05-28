#!/usr/bin/env bash
# Build a flm-voice RPM from the PyInstaller binary.
#
# Output: ~/rpmbuild/RPMS/x86_64/flm-voice-<version>-<release>.x86_64.rpm
#
# Requires:
#   rpm-build  (sudo zypper install rpm-build)
#
# Builds the binary first via scripts/build-binary.sh if dist/flm-voice
# is missing. Pass FORCE_REBUILD=1 to always rebuild the binary.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v rpmbuild >/dev/null; then
    echo "error: rpmbuild not found. Install:  sudo zypper install rpm-build" >&2
    exit 1
fi

if [ "${FORCE_REBUILD:-0}" = "1" ] || [ ! -x dist/flm-voice ]; then
    echo ">>> Building dist/flm-voice"
    scripts/build-binary.sh
fi

TOP="$(rpm --eval %{_topdir})"
mkdir -p "$TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

echo ">>> Staging sources into $TOP/SOURCES"
cp dist/flm-voice                "$TOP/SOURCES/flm-voice"
cp packaging/flm-voice.service   "$TOP/SOURCES/flm-voice.service"
cp LICENSE                       "$TOP/SOURCES/LICENSE"
cp README.md                     "$TOP/SOURCES/README.md"

echo ">>> Building RPM"
rpmbuild -bb packaging/flm-voice.spec

RPM=$(ls -t "$TOP/RPMS"/*/flm-voice-*.rpm 2>/dev/null | head -1)
if [ -z "$RPM" ]; then
    echo "error: rpmbuild completed but produced no RPM under $TOP/RPMS/" >&2
    exit 1
fi

SIZE=$(du -h "$RPM" | awk '{print $1}')
echo
echo ">>> Built $RPM ($SIZE)"
echo
echo "Install:    sudo zypper install $RPM"
echo "Uninstall:  sudo zypper remove flm-voice"
echo "Inspect:    rpm -qpl $RPM"
