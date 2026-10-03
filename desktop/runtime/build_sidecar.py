"""Build on matching native OS/architecture. No cross-compiling Python."""
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
}


def main():
    target = TARGETS.get((platform.system(), platform.machine()))
    if not target:
        raise SystemExit("Build on supported native Windows x64 or macOS arm64/x64 host")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Release builder requires Python 3.12")
    host = subprocess.check_output(["rustc", "-vV"], text=True)
    if f"host: {target}" not in host:
        raise SystemExit("Python architecture and Rust host must match")
    destination = ROOT / "desktop/tauri/src-tauri/binaries"
    destination.mkdir(parents=True, exist_ok=True)
    frozen = ROOT / "build/frozen"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", "sayelf-runtime", "--paths", str(ROOT),
        "--distpath", str(frozen), "--workpath", str(ROOT / "build/sidecar"),
        "--specpath", str(ROOT / "build"),
        str(ROOT / "desktop/runtime/entrypoint.py"),
    ], cwd=ROOT, check=True)
    built = frozen / ("sayelf-runtime.exe" if sys.platform == "win32" else "sayelf-runtime")
    binary = destination / (f"sayelf-runtime-{target}" + (".exe" if sys.platform == "win32" else ""))
    shutil.copy2(built, binary)
    # Release-time contract check against the actual packaged executable.
    subprocess.run([sys.executable, str(ROOT / "desktop/runtime/smoke_sidecar.py"), str(binary)], check=True)


if __name__ == "__main__":
    main()
