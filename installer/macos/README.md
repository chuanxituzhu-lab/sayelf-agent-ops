# macOS DMG

Build on each matching Mac host using Python 3.12, Rust, Node.js/npm and Xcode Command Line Tools. These tools exist only on the builder; the app embeds its Python runtime as a sidecar.

Run `./installer/macos/build.sh arm64` on Apple Silicon or `./installer/macos/build.sh x64` on Intel. The script rejects a mismatched host rather than producing a mislabeled binary. It writes `installer/macos/dist/Sayelf-Agent-Ops-macOS-arm64.dmg` or `Sayelf-Agent-Ops-macOS-x64.dmg`.

The DMG contains the app, Applications shortcut, local PDF reader, Chinese/English OCR engine and language models, plus their third-party notices. Parsing user-selected material does not require a network connection. First launch initializes `~/Library/Application Support/Sayelf` unless a user selects another directory. Removing the app does not remove this data.

Signing and notarization require the publisher's Apple Developer credentials. The local build intentionally does not read or store credentials; complete signing through the release owner's protected process.
