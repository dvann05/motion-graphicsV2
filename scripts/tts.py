"""
tts.py
Generate narration audio per-scene with edge-tts (gratis, tidak butuh API key)
dan ukur durasinya lewat ffprobe.
"""

import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts


async def _synthesize(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def synthesize_sentence(text: str, voice: str, out_path: Path) -> None:
    """Sintesis satu kalimat jadi file mp3."""
    asyncio.run(_synthesize(text, voice, out_path))


def get_audio_duration(path: Path) -> float:
    """Ambil durasi audio (detik) pakai ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
