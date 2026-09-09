"""Audio helper — convert any browser/upload audio to Gemini-friendly MP3.

Uses the ffmpeg binary bundled by the `imageio-ffmpeg` pip package, so NO system
ffmpeg install is required on the VPS. We call ffmpeg directly (no ffprobe
dependency). Browsers record webm/opus which Gemini cannot ingest directly; we
transcode to mono 16kHz MP3 which Gemini accepts.
"""
import os
import subprocess
import tempfile

import imageio_ffmpeg


def to_mp3(raw: bytes, suffix: str = ".webm") -> bytes:
    """Transcode arbitrary audio bytes to MP3 bytes. Raises ValueError on bad audio."""
    if not raw:
        raise ValueError("empty audio")
    inp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".webm")
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    inp.write(raw)
    inp.flush()
    inp.close()
    out.close()
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [exe, "-y", "-i", inp.name, "-f", "mp3", "-acodec", "libmp3lame",
             "-ar", "16000", "-ac", "1", out.name],
            capture_output=True, timeout=90,
        )
        if proc.returncode != 0 or not os.path.exists(out.name) or os.path.getsize(out.name) == 0:
            raise ValueError("audio conversion failed (unsupported or corrupted file)")
        with open(out.name, "rb") as f:
            return f.read()
    finally:
        for p in (inp.name, out.name):
            try:
                os.unlink(p)
            except Exception:
                pass
