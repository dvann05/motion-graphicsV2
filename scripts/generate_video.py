#!/usr/bin/env python3
"""
Generate a motion-graphics video from narration.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tts import get_audio_duration, synthesize_sentence  # noqa: E402
from visual_backend import build_scene_image  # noqa: E402

FPS = 30
TITLE_DURATION = 2.8
OUTRO_DURATION = 2.2
TRANSITION = 0.45
AUDIO_PAD = 0.35

RATIO_TO_SIZE = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate motion graphics video.")
    parser.add_argument("--judul", required=True)
    parser.add_argument("--narasi", required=True)
    parser.add_argument("--durasi", default="otomatis")
    parser.add_argument("--rasio", default="9:16", choices=list(RATIO_TO_SIZE))
    parser.add_argument("--tts-voice", default="id-ID-ArdiNeural")
    parser.add_argument("--output", default="output/video.mp4")
    return parser.parse_args()


def split_sentences(narasi: str) -> List[str]:
    sentences = []
    for line in re.split(r"[\r\n]+", (narasi or "").strip()):
        for part in re.split(r"(?<=[.!?])\s+", line.strip()):
            if part.strip():
                sentences.append(part.strip())
    if not sentences:
        raise ValueError("Narasi kosong setelah pemrosesan.")
    return sentences


def run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode:
        print("CMD:", " ".join(cmd), file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Perintah gagal: {cmd[0]}")


def render_clip(
    image_path: Path,
    size: Tuple[int, int],
    duration: float,
    out_path: Path,
    audio_path: Path | None = None,
    zoom_in: bool = True,
) -> None:
    duration = max(float(duration), 0.5)
    width, height = size
    total_frames = max(int(duration * FPS), 1)
    fade_duration = min(TRANSITION, duration / 2)
    fade_out_start = max(duration - fade_duration, 0.0)

    zoom_expr = "min(zoom+0.001,1.15)" if zoom_in else "max(zoom-0.0007,1.0)"
    video_filter = (
        f"zoompan=z='{zoom_expr}':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={width}x{height}:fps={FPS},"
        f"fade=t=in:st=0:d={fade_duration:.3f},"
        f"fade=t=out:st={fade_out_start:.3f}:d={fade_duration:.3f},"
        "format=yuv420p"
    )

    tmp_out = out_path.with_name(out_path.stem + ".tmp.mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(image_path)]
    if audio_path is not None:
        cmd += ["-i", str(audio_path)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    cmd += [
        "-frames:v", str(total_frames),
        "-vf", video_filter,
        "-af", f"apad,atrim=duration={duration:.3f}",
        "-ar", "44100",
        "-ac", "2",
        "-c:v", "libx264",
        "-crf", "19",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(tmp_out),
    ]

    try:
        run(cmd)
        if not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg tidak menghasilkan clip: {tmp_out}")
        tmp_out.replace(out_path)
    finally:
        tmp_out.unlink(missing_ok=True)


def concat_clips(clip_paths: List[Path], out_path: Path, workdir: Path) -> None:
    if not clip_paths:
        raise ValueError("Tidak ada clip untuk digabungkan.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = workdir / "concat_list.txt"

    with manifest.open("w", encoding="utf-8") as f:
        for clip in clip_paths:
            if not clip.is_file() or clip.stat().st_size == 0:
                raise FileNotFoundError(f"Clip tidak ditemukan atau kosong: {clip}")
            escaped = str(clip.resolve()).replace("\\", "\\\\").replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    tmp_out = out_path.with_name(out_path.stem + ".tmp.mp4")
    try:
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-c:v", "libx264", "-crf", "19", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            str(tmp_out),
        ])
        tmp_out.replace(out_path)
    finally:
        tmp_out.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    if not args.judul.strip():
        raise ValueError("Judul tidak boleh kosong.")

    if args.durasi != "otomatis":
        try:
            target = float(args.durasi)
        except ValueError as exc:
            raise ValueError("Durasi harus 'otomatis' atau angka detik.") from exc
        if target <= 0:
            raise ValueError("Durasi harus lebih dari 0.")
    else:
        target = None

    size = RATIO_TO_SIZE[args.rasio]
    sentences = split_sentences(args.narasi)

    workdir = Path(tempfile.mkdtemp(prefix="motionvid_"))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        clips: List[Path] = []

        title_img = workdir / "scene_000_title.png"
        build_scene_image(args.judul.strip(), size, title_img, palette_index=0, is_title=True, subtitle="CERITA DALAM GERAK")
        title_clip = workdir / "clip_000_title.mp4"
        render_clip(title_img, size, TITLE_DURATION, title_clip, zoom_in=True)
        clips.append(title_clip)

        total_narration = 0.0
        for idx, sentence in enumerate(sentences, start=1):
            audio_path = workdir / f"audio_{idx:03d}.mp3"
            print(f"[{idx}/{len(sentences)}] TTS: {sentence[:60]}...")
            synthesize_sentence(sentence, args.tts_voice, audio_path)
            scene_duration = max(get_audio_duration(audio_path) + AUDIO_PAD, 2.0)
            total_narration += scene_duration

            img_path = workdir / f"scene_{idx:03d}.png"
            build_scene_image(sentence, size, img_path, palette_index=idx)
            clip_path = workdir / f"clip_{idx:03d}.mp4"
            render_clip(img_path, size, scene_duration, clip_path, audio_path=audio_path, zoom_in=(idx % 2 == 1))
            clips.append(clip_path)

        outro_duration = OUTRO_DURATION
        current = TITLE_DURATION + total_narration + outro_duration
        if target is not None and current < target:
            outro_duration += target - current

        outro_img = workdir / "scene_999_outro.png"
        build_scene_image("TERIMA KASIH", size, outro_img, palette_index=len(sentences) + 1, is_title=True, subtitle="SUKAI • BAGIKAN • IKUTI")
        outro_clip = workdir / "clip_999_outro.mp4"
        render_clip(outro_img, size, outro_duration, outro_clip, zoom_in=False)
        clips.append(outro_clip)

        concat_clips(clips, output_path, workdir)
        print(f"Selesai! Video tersimpan di: {output_path.resolve()}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
