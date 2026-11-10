import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

VOICE_FALLBACKS = {
    "id-ID-ArdiNeural": "id-ID-ArdiNeural",
    "id-ID-GadisNeural": "id-ID-GadisNeural",
    "en-US-GuyNeural": "en-US-GuyNeural",
    "en-US-JennyNeural": "en-US-JennyNeural",
    "id-ID-RizkyNeural": "id-ID-RizkyNeural",
    "id-ID-NadiaNeural": "id-ID-NadiaNeural",
    "en-US-AnaNeural": "en-US-AnaNeural",
}


def _resolve_voice(voice: str) -> str:
    voice = (voice or "id-ID-ArdiNeural").strip()
    return VOICE_FALLBACKS.get(voice, "id-ID-ArdiNeural")


async def _synthesize(text: str, voice: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_voice = _resolve_voice(voice)
    communicate = edge_tts.Communicate(text, resolved_voice)
    await communicate.save(str(out_path))


def synthesize_sentence(text: str, voice: str, out_path: Path) -> None:
    """Sintesis satu kalimat menjadi file audio MP3 dengan fallback voice."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Teks narasi kosong untuk TTS.")

    last_error = None
    for attempt in range(3):
        try:
            asyncio.run(_synthesize(text, voice, out_path))
            if out_path.exists() and out_path.stat().st_size > 0:
                return
        except Exception as exc:  # pragma: no cover - runtime external dependency
            last_error = exc

        if attempt < 2:
            try:
                asyncio.sleep(0.2)
            except Exception:
                pass

    raise RuntimeError(f"TTS gagal setelah 3 percobaan: {last_error}") from last_error


def get_audio_duration(path: Path) -> float:
    """Ambil durasi audio (detik) memakai ffprobe, dengan fallback aman."""
    if not path.exists():
        return 1.0

    try:
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
            check=False,
        )
        if result.returncode != 0:
            return 1.0
        data = json.loads(result.stdout or "{}")
        duration = float(data.get("format", {}).get("duration", 1.0))
        return max(duration, 1.0)
    except Exception:
        return 1.0
