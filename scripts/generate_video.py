#!/usr/bin/env python3
"""Generate a motion-graphics video using Pillow, edge-tts, and ffmpeg."""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scene_builder import build_scene_image  # noqa: E402
from tts import get_audio_duration, synthesize_sentence  # noqa: E402

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
    parser = argparse.ArgumentParser(
        description="Generate a motion-graphics video from narration."
    )
    parser.add_argument("--judul", required=True)
    parser.add_argument("--narasi", required=True)
    parser.add_argument(
        "--durasi",
        default="otomatis",
        help="'otomatis' atau durasi minimum dalam detik",
    )
    parser.add_argument("--rasio", default="9:16", choices=list(RATIO_TO_SIZE))
    parser.add_argument("--tts-voice", default="id-ID-ArdiNeural")
    parser.add_argument("--output", default="output/video.mp4")
    return parser.parse_args()


def split_sentences(narasi: str) -> List[str]:
    """Split narration at line breaks and sentence punctuation."""
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
        print("Command gagal:", " ".join(cmd), file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Perintah gagal: {cmd[0]} (exit {result.returncode})")


def verify_video(path: Path) -> None:
    """Check that the generated MP4 contains readable audio and video streams."""
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"File video tidak ada atau kosong: {path}")

    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"ffprobe gagal memeriksa video: {result.stderr.strip()}")

    streams = json.loads(result.stdout or "{}").get("streams", [])
    stream_types = {stream.get("codec_type") for stream in streams}
    if "video" not in stream_types or "audio" not in stream_types:
        raise RuntimeError("Video final harus berisi stream video dan audio.")


def render_clip(
    image_path: Path,
    size: Tuple[int, int],
    duration: float,
    out_path: Path,
    audio_path: Path | None = None,
    zoom_in: bool = True,
) -> None:
    """Render a scene with gentle zoom, fade-in/out, and narration or silence."""
    duration = max(float(duration), 0.5)
    width, height = size
    frame_count = max(round(duration * FPS), 1)
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
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(FPS), "-i", str(image_path),
    ]
    if audio_path is not None:
        cmd += ["-i", str(audio_path)]
    else:
        cmd += [
            "-f", "lavfi", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]

    audio_filter = f"apad,atrim=duration={duration:.3f}"
    cmd += [
        "-frames:v", str(frame_count),
        "-vf", video_filter,
        "-af", audio_filter,
        "-ar", "44100", "-ac", "2",
        "-c:v", "libx264", "-crf", "19", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k",
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
    """Join rendered clips using a concat manifest and re-encode final MP4."""
    if not clip_paths:
        raise ValueError("Tidak ada clip untuk digabungkan.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = workdir / "concat_list.txt"

    with manifest.open("w", encoding="utf-8") as file_list:
        for clip in clip_paths:
            if not clip.is_file() or clip.stat().st_size == 0:
                raise FileNotFoundError(f"Clip tidak ditemukan atau kosong: {clip}")
            escaped_path = str(clip.resolve()).replace("\\", "\\\\").replace("'", "'\\''")
            file_list.write(f"file '{escaped_path}'\n")

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
        verify_video(tmp_out)
        tmp_out.replace(out_path)
    finally:
        tmp_out.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()

    if not args.judul.strip():
        raise ValueError("Judul tidak boleh kosong.")

    if args.durasi == "otomatis":
        target_duration = None
    else:
        try:
            target_duration = float(args.durasi)
        except ValueError as exc:
            raise ValueError("Durasi harus 'otomatis' atau angka dalam detik.") from exc
        if not math.isfinite(target_duration) or target_duration <= 0:
            raise ValueError("Durasi target harus lebih besar dari nol.")

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg dan ffprobe wajib terpasang dan tersedia pada PATH.")

    size = RATIO_TO_SIZE[args.rasio]
    sentences = split_sentences(args.narasi)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="motionvid_"))

    try:
        clips: List[Path] = []
        print(f"Jumlah scene narasi: {len(sentences)}")

        # Intro/title scene.
        title_image = workdir / "scene_000_title.png"
        build_scene_image(
            args.judul.strip(),
            size,
            title_image,
            palette_index=0,
            is_title=True,
            subtitle="CERITA DALAM GERAK",
        )
        title_clip = workdir / "clip_000_title.mp4"
        render_clip(title_image, size, TITLE_DURATION, title_clip, zoom_in=True)
        clips.append(title_clip)

        narration_duration = 0.0
        for index, sentence in enumerate(sentences, start=1):
            audio_path = workdir / f"audio_{index:03d}.mp3"
            print(f"[{index}/{len(sentences)}] TTS: {sentence[:60]}...")
            synthesize_sentence(sentence, args.tts_voice, audio_path)

            scene_duration = max(get_audio_duration(audio_path) + AUDIO_PAD, 2.0)
            narration_duration += scene_duration

            image_path = workdir / f"scene_{index:03d}.png"
            build_scene_image(
                sentence,
                size,
                image_path,
                palette_index=index,
            )

            clip_path = workdir / f"clip_{index:03d}.mp4"
            render_clip(
                image_path,
                size,
                scene_duration,
                clip_path,
                audio_path=audio_path,
                zoom_in=(index % 2 == 1),
            )
            clips.append(clip_path)

        # The requested duration is a minimum; never cut narration mid-sentence.
        outro_duration = OUTRO_DURATION
        current_duration = TITLE_DURATION + narration_duration + outro_duration
        if target_duration is not None and current_duration < target_duration:
            outro_duration += target_duration - current_duration

        outro_image = workdir / "scene_999_outro.png"
        build_scene_image(
            "TERIMA KASIH",
            size,
            outro_image,
            palette_index=len(sentences) + 1,
            is_title=True,
            subtitle="SUKAI  •  BAGIKAN  •  IKUTI",
        )
        outro_clip = workdir / "clip_999_outro.mp4"
        render_clip(outro_image, size, outro_duration, outro_clip, zoom_in=False)
        clips.append(outro_clip)

        estimate = TITLE_DURATION + narration_duration + outro_duration
        print(f"Perkiraan durasi video: {estimate:.1f} detik")

        concat_clips(clips, output_path, workdir)
        verify_video(output_path)
        print(f"Selesai! Video tersimpan di: {output_path.resolve()}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
