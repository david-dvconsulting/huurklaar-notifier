#!/bin/bash
# Vernieuwt de vastgepinde afhankelijkheden (met hashes) voor de releasebuilds: requirements/release-mac.txt en
# requirements/release-windows.txt. Gebruik: scripts/lock-release.sh [extra uv-opties, bv. --upgrade-package keyring]
# Vereist uv (https://docs.astral.sh/uv/). uv lost op voor het doelplatform, dus beide locks kunnen vanaf elk
# platform gemaakt worden. Zie docs/bouwen-en-releasen.md.
set -euo pipefail
cd "$(dirname "$0")/.."

# Relatieve paden en een vaste kop, zodat er geen lokaal pad in de lockbestanden komt (de repo is publiek).
lock() {
  local platform="$1" extra="$2" out="$3"
  shift 3
  uv pip compile pyproject.toml requirements/release-build.in \
    --extra "$extra" --extra dev \
    --generate-hashes --python-version 3.13 --python-platform "$platform" \
    --custom-compile-command "scripts/lock-release.sh" \
    -o "$out" "$@"
}

# macos-latest is Apple Silicon en build-mac.sh bouwt voor de eigen architectuur (geen --target-arch).
lock aarch64-apple-darwin mac requirements/release-mac.txt "$@"
lock x86_64-pc-windows-msvc windows requirements/release-windows.txt "$@"
