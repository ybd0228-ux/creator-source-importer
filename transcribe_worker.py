"""Separate process keeps a failed GPU/model job from terminating the batch."""
import json
import os
from pathlib import Path
import sys
import resource
import time

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def main():
    from huggingface_hub import snapshot_download
    import mlx_whisper
    import mlx.core as mx
    audio, output, model, language = sys.argv[1:]
    cache_root = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache/huggingface/hub"))
    repo_cache = cache_root / ("models--" + model.replace("/", "--"))
    ref = repo_cache / "refs/main"
    override = Path(os.environ.get("CSI_MODEL_OVERRIDE", ""))
    local = str(override) if (
        (override / "config.json").is_file()
        and any((override / name).is_file() for name in ("weights.npz", "weights.safetensors"))
    ) else None
    if ref.is_file():
        candidate = repo_cache / "snapshots" / ref.read_text().strip()
        if (candidate / "config.json").is_file() and any((candidate / f).is_file() for f in ("weights.npz", "weights.safetensors")):
            local = str(candidate)
    if local is None:
        local = snapshot_download(model)
    started = time.monotonic()
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=local,
                                    language=None if language == "auto" else language,
                                    task="transcribe", verbose=False, temperature=0.0)
    result["performance"] = {"transcription_seconds": round(time.monotonic() - started, 2),
                             "peak_gpu_bytes": mx.get_peak_memory(),
                             "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    # Keep recognizer output as-is: no cleanup, translation or LLM calls.
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
