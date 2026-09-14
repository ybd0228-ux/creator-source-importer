#!/usr/bin/env python3
"""Restore MLX symlinks that Tauri dereferences while copying resources."""
from pathlib import Path
import os
import sys

internal = Path(sys.argv[1]) / "Contents/Resources/resources/sidecar/_internal"
(internal / "mlx.metallib").unlink(missing_ok=True)
for name, target in {
    "libmlx.dylib": "mlx/lib/libmlx.dylib",
    "libjaccl.dylib": "mlx/lib/libjaccl.dylib",
}.items():
    path = internal / name
    path.unlink(missing_ok=True)
    os.symlink(target, path)
