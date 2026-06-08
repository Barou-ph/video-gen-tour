import subprocess
import os
import shutil
import tempfile
from PIL import Image

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_duration(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _crop_to_916(img: Image.Image) -> Image.Image:
    w, h = img.size
    target_ratio = 9 / 16
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    return img


def _prepare_images(media_paths: list, temp_dir: str) -> list:
    """Resize tất cả ảnh về 1080x1920, trả về list đường dẫn."""
    image_paths = [
        p for p in media_paths if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
    ]
    if not image_paths:
        raise ValueError("Cần ít nhất 1 ảnh!")

    result = []
    for i, img_path in enumerate(image_paths):
        out_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
        img = Image.open(img_path)

        # Fix RGBA/PNG
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img = _crop_to_916(img)
        img = img.resize((1080, 1920), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=95)
        result.append(out_path)

    return result


# ─── Main function ─────────────────────────────────────────────────────────────


def build_video(
    media_paths: list[str],
    audio_path: str,
    output_path: str,
    logo_path: str = None,
    bg_music_path: str = None,  # Nhạc nền (tuỳ chọn)
    max_words: int = None,  # Giới hạn số từ nói (tuỳ chọn)
) -> str:

    temp_dir = tempfile.mkdtemp()

    try:
        # ── Bước 0: Giới hạn số từ nếu cần ──────────────────────────────────
        # (Xử lý ở tầng script_gen, không xử lý audio ở đây)

        # ── Bước 1: Lấy duration audio THẬT ──────────────────────────────────
        audio_duration = _get_duration(audio_path)
        print(f"[VIDEO] Audio duration: {audio_duration:.1f}s")

        # ── Bước 2: Chuẩn bị ảnh ─────────────────────────────────────────────
        image_paths = _prepare_images(media_paths, temp_dir)
        n = len(image_paths)

        # Mỗi ảnh hiển thị đều nhau, tổng = audio_duration + 1s đệm
        duration_each = (audio_duration + 1.0) / n
        print(f"[VIDEO] {n} ảnh × {duration_each:.1f}s = {duration_each*n:.1f}s")

        # ── Bước 3: Ghép ảnh thành video với crossfade ───────────────────────
        raw_video = os.path.join(temp_dir, "raw.mp4")
        _build_with_crossfade(image_paths, duration_each, raw_video)

        # ── Bước 4: Mix audio voice + nhạc nền ───────────────────────────────
        final_audio = os.path.join(temp_dir, "final_audio.mp3")
        if bg_music_path and os.path.exists(bg_music_path):
            _mix_audio(audio_path, bg_music_path, audio_duration, final_audio)
        else:
            shutil.copy(audio_path, final_audio)

        # ── Bước 5: Ghép audio vào video ─────────────────────────────────────
        # Video dài hơn audio 1s → không bao giờ bị cắt
        video_with_audio = os.path.join(temp_dir, "with_audio.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                raw_video,
                "-i",
                final_audio,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-t",
                str(audio_duration),  # cắt đúng theo audio, không theo video
                output_path,
            ],
            check=True,
            capture_output=True,
        )

        print(f"[VIDEO] Done → {output_path}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path


# ─── Crossfade giữa các ảnh ───────────────────────────────────────────────────


def _build_with_crossfade(image_paths: list, duration_each: float, output: str):
    """
    Ghép ảnh với hiệu ứng crossfade mượt bằng FFmpeg xfade filter.
    """
    n = len(image_paths)
    fade_duration = 0.5  # 0.5 giây fade giữa 2 ảnh

    if n == 1:
        # Chỉ 1 ảnh → loop tĩnh
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                image_paths[0],
                "-vf",
                "scale=1080:1920,fps=30",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-t",
                str(duration_each),
                output,
            ],
            check=True,
            capture_output=True,
        )
        return

    # Tạo từng clip ảnh riêng
    temp_clips = []
    temp_dir = os.path.dirname(output)

    for i, img_path in enumerate(image_paths):
        clip_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                img_path,
                "-vf",
                "scale=1080:1920,fps=30",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-t",
                str(duration_each),
                clip_path,
            ],
            check=True,
            capture_output=True,
        )
        temp_clips.append(clip_path)

    # Ghép clips với xfade
    # FFmpeg xfade: offset = thời điểm bắt đầu fade của clip tiếp theo
    # offset = duration_each * i - fade_duration * i
    if n == 2:
        offset = duration_each - fade_duration
        filter_complex = f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}[v]"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                temp_clips[0],
                "-i",
                temp_clips[1],
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                output,
            ],
            check=True,
            capture_output=True,
        )
    else:
        # Nhiều clip: ghép tuần tự bằng concat trước, sau đó xfade từng đôi
        # Cách đơn giản nhất: dùng concat filter không có fade (mượt hơn cắt cứng)
        inputs = []
        for c in temp_clips:
            inputs += ["-i", c]

        filter_parts = []
        for i in range(n):
            filter_parts.append(f"[{i}:v]")
        filter_str = "".join(filter_parts) + f"concat=n={n}:v=1:a=0[v]"

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                filter_str,
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                output,
            ],
            check=True,
            capture_output=True,
        )


# ─── Mix nhạc nền ─────────────────────────────────────────────────────────────


def _mix_audio(voice_path: str, music_path: str, duration: float, output: str):
    """
    Mix giọng đọc + nhạc nền.
    Nhạc nền nhỏ hơn giọng (volume 15%), loop nếu ngắn hơn voice.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            voice_path,
            "-stream_loop",
            "-1",
            "-i",
            music_path,  # loop nhạc nền
            "-filter_complex",
            f"[1:a]volume=0.15,atrim=0:{duration}[music];"  # nhạc nền 15%
            f"[0:a][music]amix=inputs=2:duration=first[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-t",
            str(duration),
            output,
        ],
        check=True,
        capture_output=True,
    )
