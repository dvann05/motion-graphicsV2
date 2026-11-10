#!/usr/bin/env python3
"""
generate_video.py
Orkestrator utama: narasi -> TTS -> scene image -> klip ffmpeg -> gabung jadi 1 video.

Dipanggil dari GitHub Actions (lihat .github/workflows/generate-video.yml) tapi
bisa juga dijalankan manual:

    python scripts/generate_video.py \
        --judul "Judul video" \
        --narasi "Kalimat pertama. Kalimat kedua. Kalimat ketiga." \
        --durasi otomatis \
        --rasio 9:16 \
        --tts-voice id-ID-ArdiNeural \
        --output output/video.mp4
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
from tts import synthesize_sentence, get_audio_duration  # noqa: E402

FPS = 30
TITLE_DURATION = 2.6
TRANSITION = 0.4  # durasi fade in/out tiap scene (detik)
AUDIO_PAD = 0.35  # jeda kecil di akhir tiap kalimat sebelum scene berikutnya

RATIO_TO_SIZE = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate motion graphics video dari narasi teks.")
    parser.add_argument("--judul", required=True)
    parser.add_argument("--narasi", required=True)
    parser.add_argument("--durasi", default="otomatis", help="'otomatis' atau jumlah detik (30/60/90/120)")
    parser.add_argument("--rasio", default="9:16", choices=list(RATIO_TO_SIZE.keys()))
    parser.add_argument("--tts-voice", default="id-ID-ArdiNeural")
    parser.add_argument("--output", default="output/video.mp4")
    return parser.parse_args()


def split_sentences(narasi: str) -> List[str]:
    """Pecah narasi jadi kalimat per baris/titik, buang yang kosong."""
    raw_lines = re.split(r"[\n\r]+", narasi.strip())
    sentences: List[str] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        # pecah per kalimat kalau satu baris berisi beberapa kalimat
        parts = re.split(r"(?<=[.!?])\s+", line)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)
    if not sentences:
        raise ValueError("Narasi kosong setelah diproses.")
    return sentences


def run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("CMD:", " ".join(cmd), file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Perintah gagal: {cmd[0]}")


def render_zoompan_clip(
    image_path: Path,
    size: Tuple[int, int],
    duration: float,
    out_path: Path,
    audio_path: Path = None,
    zoom_in: bool = True,
) -> None:
    """Render satu scene (gambar diam + efek zoom pelan + fade) jadi mp4."""
    width, height = size
    total_frames = max(int(duration * FPS), 1)
    fade_out_start = max(duration - TRANSITION, 0)

    zoom_expr = "min(zoom+0.0006,1.12)" if zoom_in else "max(zoom-0.0006,1.0)"
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
        "18",
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
    list_file = workdir / "concat_list.txt"
    with open(list_file, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{clip.resolve()}'\n")

    tmp_out = out_path.with_suffix(".tmp.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)
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

    # --- Scene judul ---
    title_img = workdir / "scene_000_title.png"
    build_scene_image(
        text=args.judul,
        size=size,
        out_path=title_img,
        palette_index=0,
        is_title=True,
        subtitle="",
    )
    title_clip = workdir / "clip_000_title.mp4"
    render_zoompan_clip(title_img, size, TITLE_DURATION, title_clip, audio_path=None, zoom_in=True)
    clip_paths.append(title_clip)

    # --- Scene narasi, satu per kalimat ---
    total_narration_duration = 0.0
    for i, sentence in enumerate(sentences, start=1):
        audio_path = workdir / f"audio_{i:03d}.mp3"
        print(f"[{i}/{len(sentences)}] TTS: {sentence[:60]}...")
        synthesize_sentence(sentence, args.tts_voice, audio_path)
        audio_duration = get_audio_duration(audio_path)
        scene_duration = audio_duration + AUDIO_PAD
        total_narration_duration += scene_duration

        img_path = workdir / f"scene_{i:03d}.png"
        build_scene_image(
            text=sentence,
            size=size,
            out_path=img_path,
            palette_index=i,
            is_title=False,
        )

        clip_path = workdir / f"clip_{i:03d}.mp4"
        render_zoompan_clip(
            img_path,
            size,
            scene_duration,
            clip_path,
            audio_path=audio_path,
            zoom_in=(i % 2 == 1),
        )
        clip_paths.append(clip_path)

    total_duration = TITLE_DURATION + total_narration_duration
    print(f"Total durasi (mengikuti narasi): {total_duration:.1f} detik")

    if args.durasi != "otomatis":
        target = float(args.durasi)
        if total_duration < target:
            extra = target - total_duration
            print(f"Durasi target {target}s lebih panjang dari narasi, menambah {extra:.1f}s di scene terakhir.")
            last_img = workdir / f"scene_{len(sentences):03d}.png"
            pad_clip = workdir / "clip_999_pad.mp4"
            render_zoompan_clip(last_img, size, extra, pad_clip, audio_path=None, zoom_in=False)
            clip_paths.append(pad_clip)
        elif total_duration > target:
            print(
                f"PERINGATAN: narasi ({total_duration:.1f}s) lebih panjang dari durasi target "
                f"{target}s. Video tidak dipotong di tengah kalimat — pertimbangkan "
                f"mempersingkat narasi atau pilih durasi 'otomatis'."
            )

    output_path = Path(args.output)
    concat_clips(clip_paths, output_path, workdir)

    shutil.rmtree(workdir, ignore_errors=True)
    print(f"Selesai! Video tersimpan di: {output_path.resolve()}")


if __name__ == "__main__":
    main()
