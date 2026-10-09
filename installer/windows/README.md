# Windows Setup.exe

Build on Windows x64 with Python 3.12 x64, Rust MSVC x64, Node.js/npm, and the Microsoft C++ Build Tools. These are builder-only prerequisites. The distributed installer embeds the Python sidecar and the WebView2 offline installer so the end user needs no Python, Node, Git, Docker, database install or network access during setup.

From the repository root, run `installer/windows/build.ps1`. The resulting NSIS installer is copied to `installer/windows/dist/Sayelf-Agent-Ops-Setup-x64.exe`.

The installer bundles the local PDF reader, Chinese/English OCR engine and language models, plus their third-party notices. The app does not need a network connection to parse user-selected material. The installer registers the app and shortcuts. First launch initializes `%LOCALAPPDATA%\Sayelf` or a user-selected directory. The data directory stays outside the install tree and the uninstaller never targets it. App removal leaves user data in place.

Code signing requires a verified publisher certificate. An unsigned local artifact is for installation testing only.
