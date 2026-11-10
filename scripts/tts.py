"""Synthesize narration with edge-tts and inspect audio using ffprobe."""

import asyncio
import json
import subprocess
import time
from pathlib import Path

import edge_tts

DEFAULT_VOICE = "id-ID-ArdiNeural"
FALLBACK_VOICES = {
    "id-ID-ArdiNeural": "id-ID-GadisNeural",
    "id-ID-GadisNeural": "id-ID-ArdiNeural",
    "en-US-GuyNeural": "en-US-JennyNeural",
    "en-US-JennyNeural": "en-US-GuyNeural",
}


def _voice_candidates(voice: str) -> list[str]:
    selected = (voice or DEFAULT_VOICE).strip()
    fallback = FALLBACK_VOICES.get(selected, DEFAULT_VOICE)
    return list(dict.fromkeys([selected, fallback, DEFAULT_VOICE]))


async def _synthesize(text: str, voice: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice).save(str(out_path))


def synthesize_sentence(text: str, voice: str, out_path: Path) -> None:
    """Try the requested voice, then fallback voices, with a network retry."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Teks narasi kosong untuk TTS.")

    errors = []
    for candidate in _voice_candidates(voice):
        for attempt in range(2):
            out_path.unlink(missing_ok=True)
            try:
                asyncio.run(_synthesize(text, candidate, out_path))
                if out_path.is_file() and out_path.stat().st_size > 0:
                    print(f"TTS menggunakan voice: {candidate}")
                    return
                raise RuntimeError("TTS menghasilkan file kosong.")
            except Exception as exc:
                errors.append(f"{candidate}, percobaan {attempt + 1}: {exc}")
                out_path.unlink(missing_ok=True)
                if attempt == 0:
                    time.sleep(0.5)

    details = " | ".join(errors[-4:])
    raise RuntimeError(f"TTS gagal dengan semua voice yang dicoba. Detail: {details}")


def get_audio_duration(path: Path) -> float:
    """Return a verified audio duration; do not hide invalid audio behind a default."""
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"File audio tidak ada atau kosong: {path}")

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"ffprobe gagal membaca audio: {result.stderr.strip()}")

    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Durasi audio tidak valid: {path}") from exc

    if duration <= 0:
        raise RuntimeError(f"Durasi audio harus positif: {path}")
    return duration
