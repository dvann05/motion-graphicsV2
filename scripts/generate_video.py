#!/usr/bin/env python3
"""
generate_video.py
Orkestrator utama: narasi -> TTS -> scene image -> klip ffmpeg -> gabung jadi 1 video.
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

from scene_builder import build_scene_image  # noqa: E402
from tts import get_audio_duration, synthesize_sentence  # noqa: E402

FPS = 30
TITLE_DURATION = 2.8
TRANSITION = 0.45
AUDIO_PAD = 0.35

RATIO_TO_SIZE = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate motion graphics video from narration text.")
    parser.add_argument("--judul", required=True)
    parser.add_argument("--narasi", required=True)
    parser.add_argument("--durasi", default="otomatis", help="'otomatis' atau durasi dalam detik")
    parser.add_argument("--rasio", default="9:16", choices=list(RATIO_TO_SIZE.keys()))
    parser.add_argument("--tts-voice", default="id-ID-ArdiNeural")
    parser.add_argument("--output", default="output/video.mp4")
    return parser.parse_args()


def split_sentences(narasi: str) -> List[str]:
    """Pecah narasi menjadi kalimat per baris atau tanda baca."""
    raw_lines = re.split(r"[\n\r]+", (narasi or "").strip())
    sentences: List[str] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)
    if not sentences:
        raise ValueError("Narasi kosong setelah pemrosesan.")
    return sentences


def run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print("CMD:", " ".join(cmd), file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Perintah gagal: {cmd[0]}")


def render_zoompan_clip(
    image_path: Path,
    size: Tuple[int, int],
    duration: float,
    out_path: Path,
    audio_path: Path | None = None,
    zoom_in: bool = True,
) -> None:
    """Render clip dengan zoom subtle dan fade in/out."""
    width, height = size
    duration = max(float(duration), 0.5)
    total_frames = max(int(duration * FPS), 1)
    fade_out_start = max(duration - TRANSITION, 0.0)

    zoom_expr = "min(zoom+0.0009,1.18)" if zoom_in else "max(zoom-0.0008,1.0)"
    vf = (
        f"scale={width}:{height},"
        f"zoompan=z='{zoom_expr}':d={total_frames}:s={width}x{height}:fps={FPS},"
        f"fade=t=in:st=0:d={TRANSITION},"
        f"fade=t=out:st={fade_out_start}:d={TRANSITION},"
        f"format=yuv420p"
    )

    tmp_out = out_path.with_suffix(".tmp.mp4")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path)]

    if audio_path is not None:
        cmd += ["-i", str(audio_path)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    cmd += [
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-af",
        "apad",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(tmp_out),
    ]
    run(cmd)
    tmp_out.rename(out_path)


def concat_clips(clip_paths: List[Path], out_path: Path, workdir: Path) -> None:
    """Gabungkan semua clip ke video final."""
    if not clip_paths:
        raise ValueError("Tidak ada clip untuk digabungkan.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = workdir / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for clip in clip_paths:
            if not clip.exists():
                raise FileNotFoundError(f"Clip tidak ditemukan sebelum concat: {clip}")
            f.write(f"file '{clip.resolve()}\n'")
            f.write("\n")

    tmp_out = out_path.with_suffix(".tmp.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(tmp_out),
    ]
    run(cmd)
    tmp_out.rename(out_path)


def main() -> None:
    args = parse_args()
    size = RATIO_TO_SIZE[args.rasio]
    sentences = split_sentences(args.narasi)

    workdir = Path(tempfile.mkdtemp(prefix="motionvid_"))
    print(f"Workdir sementara: {workdir}")
    print(f"Jumlah scene narasi: {len(sentences)}")

    clip_paths: List[Path] = []

    title_img = workdir / "scene_000_title.png"
    build_scene_image(
        text=args.judul,
        size=size,
        out_path=title_img,
        palette_index=0,
        is_title=True,
        subtitle="Motion Graphics Automatis",
    )
    title_clip = workdir / "clip_000_title.mp4"
    render_zoompan_clip(title_img, size, TITLE_DURATION, title_clip, audio_path=None, zoom_in=True)
    clip_paths.append(title_clip)

    total_narration_duration = 0.0
    for idx, sentence in enumerate(sentences, start=1):
        audio_path = workdir / f"audio_{idx:03d}.mp3"
        print(f"[{idx}/{len(sentences)}] TTS: {sentence[:60]}...")
        synthesize_sentence(sentence, args.tts_voice, audio_path)
        audio_duration = get_audio_duration(audio_path)
        scene_duration = max(audio_duration + AUDIO_PAD, 2.0)
        total_narration_duration += scene_duration

        img_path = workdir / f"scene_{idx:03d}.png"
        build_scene_image(
            text=sentence,
            size=size,
            out_path=img_path,
            palette_index=idx,
            is_title=False,
        )

        clip_path = workdir / f"clip_{idx:03d}.mp4"
        render_zoompan_clip(
            img_path,
            size,
            scene_duration,
            clip_path,
            audio_path=audio_path,
            zoom_in=(idx % 2 == 1),
        )
        clip_paths.append(clip_path)

    total_duration = TITLE_DURATION + total_narration_duration
    print(f"Total durasi (mengikuti narasi): {total_duration:.1f} detik")

    if args.durasi != "otomatis":
        target = float(args.durasi)
        if total_duration < target:
            extra = target - total_duration
            print(f"Durasi target {target}s lebih panjang dari narasi, menambah {extra:.1f}s pada scene terakhir.")
            last_img = workdir / f"scene_{len(sentences):03d}.png"
            pad_clip = workdir / "clip_999_pad.mp4"
            render_zoompan_clip(last_img, size, extra, pad_clip, audio_path=None, zoom_in=False)
            clip_paths.append(pad_clip)
        elif total_duration > target:
            print(
                f"PERINGATAN: narasi ({total_duration:.1f}s) lebih panjang dari target "
                f"{target}s. Video tidak dipotong di tengah kalimat."
            )

    output_path = Path(args.output)
    concat_clips(clip_paths, output_path, workdir)

    shutil.rmtree(workdir, ignore_errors=True)
    print(f"Selesai! Video tersimpan di: {output_path.resolve()}")


if __name__ == "__main__":
    main()
