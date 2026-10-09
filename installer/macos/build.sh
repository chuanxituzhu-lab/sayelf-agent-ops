#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
requested="${1:-}"
machine="$(uname -m)"
case "$machine" in arm64) host_arch=arm64; target=aarch64-apple-darwin ;; x86_64) host_arch=x64; target=x86_64-apple-darwin ;; *) echo 'Supported build hosts: Apple Silicon and Intel Mac.' >&2; exit 2 ;; esac
if [[ "$requested" != "$host_arch" ]]; then echo "Build $requested on the matching $host_arch Mac host." >&2; exit 2; fi
python3.12 -c 'import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12"'
rustc -vV | grep -F "host: $target" >/dev/null || { echo 'Rust target must match this Mac.' >&2; exit 2; }
cd "$repo"
python3.12 -m venv desktop/runtime/.venv
desktop/runtime/.venv/bin/python -m pip install --disable-pip-version-check -r desktop/runtime/requirements-build.txt
desktop/runtime/.venv/bin/python desktop/runtime/build_sidecar.py
cd desktop/tauri
npm ci
npm run tauri -- build --bundles dmg
bundle="src-tauri/target/release/bundle/dmg"
artifact="$(find "$bundle" -maxdepth 1 -name '*.dmg' -print -quit)"
[[ -n "$artifact" ]] || { echo 'Tauri did not produce a DMG.' >&2; exit 1; }
case "$host_arch" in arm64) suffix=arm64 ;; x64) suffix=x64 ;; esac
dist="$repo/installer/macos/dist"
mkdir -p "$dist"
cp "$artifact" "$dist/Sayelf-Agent-Ops-macOS-$suffix.dmg"
shasum -a 256 "$dist/Sayelf-Agent-Ops-macOS-$suffix.dmg"
