#!/usr/bin/env python3
"""Relocate a staged shared FFmpeg build for an app-local runtime."""
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
files = [root / "bin/ffmpeg", root / "bin/ffprobe"]
files += [path for path in (root / "lib").glob("*.dylib") if not path.is_symlink()]
prefix = "/opt/creator-source-importer-runtime/lib/"

for path in files:
    output = subprocess.check_output(["otool", "-L", str(path)], text=True)
    for line in output.splitlines()[1:]:
        dependency = line.strip().split(" ", 1)[0]
        if dependency.startswith(prefix):
            name = Path(dependency).name
            replacement = (
                f"@executable_path/../lib/{name}"
                if path.parent.name == "bin"
                else f"@loader_path/{name}"
            )
            subprocess.run(
                ["install_name_tool", "-change", dependency, replacement, str(path)],
                check=True,
            )
    if path.suffix == ".dylib":
        subprocess.run(
            ["install_name_tool", "-id", f"@loader_path/{path.name}", str(path)],
            check=True,
        )

