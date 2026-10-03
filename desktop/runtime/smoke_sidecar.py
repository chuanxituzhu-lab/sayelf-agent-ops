"""Exercise the frozen executable with no developer tools on PATH."""
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


def main():
    binary = Path(sys.argv[1]).resolve()
    environment = os.environ.copy()
    environment["PATH"] = environment.get("SystemRoot", "/usr") + ("/System32" if os.name == "nt" else "/bin")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="sayelf-frozen-") as temporary:
        root = Path(temporary) / "数据 space"
        for action, pack, expected in (("health", "engineering", 10), ("initialize", "engineering", 0),
                                       ("initialize", "engineering", 0), ("health", "engineering", 0),
                                       ("initialize", "media", 10)):
            output = subprocess.run([str(binary), action, "--data-dir", str(root), "--pack", pack],
                                    env=environment, capture_output=True, text=True, timeout=45)
            result = json.loads(output.stdout)
            assert output.returncode == result["code"] == expected, result
            if expected == 0:
                assert result["data"]["checks"]["core"] == "ok"
            if action == "initialize" and expected == 10:
                assert result["data"]["reason"] == "PACK_MISMATCH"
        schema_root = Path(temporary) / "future schema"
        subprocess.run([str(binary), "initialize", "--data-dir", str(schema_root)], env=environment,
                       capture_output=True, text=True, check=True, timeout=45)
        with closing(sqlite3.connect(schema_root / "runtime.sqlite3")) as connection:
            connection.execute("BEGIN")
            connection.execute("UPDATE metadata SET value='999' WHERE key='schema'")
            connection.commit()
        output = subprocess.run([str(binary), "health", "--data-dir", str(schema_root)], env=environment,
                                capture_output=True, text=True, timeout=45)
        result = json.loads(output.stdout)
        assert output.returncode == result["code"] == 10
        assert result["data"]["reason"] == "SCHEMA_UNSUPPORTED"
        foreign_root = Path(temporary) / "keep existing files"
        foreign_root.mkdir()
        (foreign_root / "keep.txt").write_text("unchanged")
        output = subprocess.run([str(binary), "initialize", "--data-dir", str(foreign_root)], env=environment,
                                capture_output=True, text=True, timeout=45)
        result = json.loads(output.stdout)
        assert output.returncode == result["code"] == 10
        assert result["data"]["reason"] == "FOREIGN_DATA"
        assert (foreign_root / "keep.txt").read_text() == "unchanged"
    print("Frozen sidecar: missing-data / initialize / relaunch / health PASS; developer PATH absent")


if __name__ == "__main__":
    main()
