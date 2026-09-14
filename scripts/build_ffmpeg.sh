#!/bin/zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$root/build/ffmpeg-9.0.1"
stage="$root/build/ffmpeg-stage-generic"
runtime="$root/build/ffmpeg-runtime"

cd "$source_dir"
make distclean >/dev/null 2>&1 || true
./configure \
  --prefix=/opt/creator-source-importer-runtime \
  --disable-autodetect --enable-securetransport \
  --enable-shared --disable-static \
  --disable-doc --disable-debug --disable-ffplay
make -j"$(sysctl -n hw.logicalcpu)"
make install DESTDIR="$stage"

mkdir -p "$runtime"
rsync -a --delete "$stage/opt/creator-source-importer-runtime/" "$runtime/"
"$root/scripts/relocate_ffmpeg.py" "$runtime"

