#!/usr/bin/env python3
"""Build scripts/fixtures/hello.wav (16 kHz mono PCM16) for provider smoke tests."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
    import soundfile as sf
except ImportError as exc:
    print(
        "Install server deps first: pip install -e server (needs soundfile + numpy).",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "fixtures" / "hello.wav"
TEXT = "Hello, what are your opening hours?"
TARGET_RATE = 16_000


def main() -> None:
    if not shutil.which("say"):
        print(
            "macOS `say` not found. Record ~1s of 16 kHz mono speech and save as:\n"
            f"  {OUT}\n"
            "Or use any WAV editor / ffmpeg:\n"
            "  ffmpeg -i input.wav -ar 16000 -ac 1 scripts/fixtures/hello.wav",
            file=sys.stderr,
        )
        raise SystemExit(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "hello.aiff"
        subprocess.run(["say", "-v", "Samantha", TEXT, "-o", str(aiff)], check=True)
        data, sr = sf.read(aiff, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != TARGET_RATE:
            n = int(len(data) * TARGET_RATE / sr)
            x = np.linspace(0, len(data) - 1, n)
            data = np.interp(x, np.arange(len(data)), data)
        sf.write(OUT, data, TARGET_RATE, subtype="PCM_16")

    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(data) / TARGET_RATE:.2f}s)")


if __name__ == "__main__":
    main()
