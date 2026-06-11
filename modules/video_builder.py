import subprocess
import os
import shutil
import tempfile
from PIL import Image


def _get_duration(path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", path
    ], capture_output=True, text=True)
    return float(result.stdout.strip())


def _crop_to_916(img: Image.Image) -> Image.Image:
    w, h = img.size
    target_ratio = 9 / 16
    if (w / h) > target_ratio:
        new_w = int(h * target_ratio)
        img = img.crop(((w - new_w) // 2, 0, (w + new_w) // 2, h))
    else:
        new_h = int(w / target_ratio)
        img = img.crop((0, (h - new_h) // 2, w, (h + new_h) // 2))
    return img


def _process_image(path: str, out_path: str):
    """Resize ảnh về 1080x1920."""
    img = Image.open(path)
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


def _process_video_clip(path: str, out_path: str, clip_duration: float = 4.0):
    """
    Xử lý video clip:
    - Crop về 9:16
    - Cắt tối đa clip_duration giây
    - Encode lại chuẩn 1080x1920 30fps
    """
    src_duration = _get_duration(path)
    use_duration = min(src_duration, clip_duration)

    subprocess.run([
        "ffmpeg", "-y",
        "-i", path,
        "-t", str(use_duration),
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "fps=30"
        ),
        "-c:v", "libx264", "-preset", "fast",
        "-an",                    # bỏ audio gốc, dùng voice FPT
        "-pix_fmt", "yuv420p",
        out_path
    ], check=True, capture_output=True)

    return use_duration


def _prepare_media(media_paths: list, temp_dir: str, audio_duration: float):
    """
    Xử lý hỗn hợp ảnh + video.
    Trả về list {"path": ..., "duration": ..., "is_video": ...}
    """
    if not media_paths:
        raise ValueError("Cần ít nhất 1 ảnh hoặc video!")

    # Chia thời gian đều cho số lượng media
    n = len(media_paths)
    duration_each = max(3.0, (audio_duration + 1.0) / n)
    # Video clip giới hạn tối đa 6 giây
    clip_max = min(duration_each, 6.0)

    result = []
    for i, path in enumerate(media_paths):
        ext = path.lower().rsplit(".", 1)[-1]
        is_video = ext in ("mp4", "mov", "avi", "mkv", "webm")

        if is_video:
            out_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
            actual_dur = _process_video_clip(path, out_path, clip_duration=clip_max)
            result.append({"path": out_path, "duration": actual_dur, "is_video": True})
            print(f"[VIDEO] Clip {i+1}: {actual_dur:.1f}s ← {os.path.basename(path)}")
        else:
            out_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
            _process_image(path, out_path)
            result.append({"path": out_path, "duration": duration_each, "is_video": False})
            print(f"[VIDEO] Ảnh {i+1}: {duration_each:.1f}s ← {os.path.basename(path)}")

    return result


def _build_concat_with_xfade(items: list, temp_dir: str, output: str):
    """
    Ghép hỗn hợp ảnh + video clip với crossfade mượt.
    Ảnh → chuyển thành clip ngắn trước, sau đó xfade tất cả.
    """
    fade = 0.4   # giây crossfade
    clips = []

    # Bước 1: chuyển ảnh → clip mp4 ngắn
    for i, item in enumerate(items):
        if item["is_video"]:
            clips.append({"path": item["path"], "duration": item["duration"]})
        else:
            clip_path = os.path.join(temp_dir, f"img_clip_{i:03d}.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", item["path"],
                "-vf", "scale=1080:1920,fps=30",
                "-c:v", "libx264", "-preset", "fast",
                "-t", str(item["duration"]),
                "-pix_fmt", "yuv420p",
                clip_path
            ], check=True, capture_output=True)
            clips.append({"path": clip_path, "duration": item["duration"]})

    n = len(clips)

    if n == 1:
        shutil.copy(clips[0]["path"], output)
        return

    # Bước 2: xfade từng đôi liên tiếp
    # Với n clip, cần n-1 lần xfade
    current = clips[0]["path"]
    current_dur = clips[0]["duration"]

    for i in range(1, n):
        next_clip = clips[i]["path"]
        next_dur  = clips[i]["duration"]
        offset    = max(0.1, current_dur - fade)

        if i < n - 1:
            out = os.path.join(temp_dir, f"xfade_{i:03d}.mp4")
        else:
            out = output

        subprocess.run([
            "ffmpeg", "-y",
            "-i", current,
            "-i", next_clip,
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}[v]",
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            out
        ], check=True, capture_output=True)

        current     = out
        current_dur = offset + next_dur


def _mix_audio(voice_path: str, music_path: str, duration: float, output: str):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", voice_path,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex",
        f"[1:a]volume=0.15,atrim=0:{duration}[music];"
        f"[0:a][music]amix=inputs=2:duration=first[aout]",
        "-map", "[aout]",
        "-c:a", "libmp3lame",
        "-t", str(duration),
        output
    ], check=True, capture_output=True)


def build_video(
    media_paths: list[str],
    audio_path: str,
    output_path: str,
    logo_path: str = None,
    bg_music_path: str = None,
    script: str = None,        # ← thêm dòng này
) -> str:

    temp_dir = tempfile.mkdtemp()

    try:
        audio_duration = _get_duration(audio_path)
        print(f"[VIDEO] Audio: {audio_duration:.1f}s | {len(media_paths)} media files")

        # Xử lý ảnh + video
        items = _prepare_media(media_paths, temp_dir, audio_duration)

        # Ghép với crossfade
        silent_video = os.path.join(temp_dir, "silent.mp4")
        _build_concat_with_xfade(items, temp_dir, silent_video)

        # Mix audio
        if bg_music_path and os.path.exists(bg_music_path):
            final_audio = os.path.join(temp_dir, "mixed_audio.mp3")
            _mix_audio(audio_path, bg_music_path, audio_duration, final_audio)
        else:
            final_audio = audio_path

        # Ghép audio vào video, cắt đúng theo audio
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", silent_video,
            "-i", final_audio,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-t", str(audio_duration),
            "-pix_fmt", "yuv420p",
            output_path
        ], check=True, capture_output=True)

        # Thêm hook overlay nếu có script
        if script:
            hook_text = script.split('.')[0].strip()  # Lấy câu đầu tiên
            if hook_text:
                hook_out = output_path.replace(".mp4", "_h.mp4")
                try:
                    _add_hook_overlay(output_path, hook_text, hook_out)
                    shutil.move(hook_out, output_path)
                    print(f"[VIDEO] Hook: {hook_text[:50]}...")
                except Exception as e:
                    print(f"[VIDEO] Hook overlay lỗi (bỏ qua): {e}")

        print(f"[VIDEO] Done → {output_path} ({_get_duration(output_path):.1f}s)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path

def _run_ffmpeg(cmd: list, step: str = ""):
    """Wrapper chạy FFmpeg với error message rõ ràng."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg lỗi ở bước '{step}':\n{result.stderr[-500:]}"
        )
    return result