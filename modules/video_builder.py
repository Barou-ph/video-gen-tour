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
    src_duration = _get_duration(path)
    use_duration = min(src_duration, clip_duration)
    subprocess.run([
        "ffmpeg", "-y", "-i", path,
        "-t", str(use_duration),
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,fps=30"
        ),
        "-c:v", "libx264", "-preset", "fast",
        "-an", "-pix_fmt", "yuv420p",
        out_path
    ], check=True, capture_output=True)
    return use_duration


def _prepare_media(media_paths: list, temp_dir: str, audio_duration: float):
    if not media_paths:
        raise ValueError("Cần ít nhất 1 ảnh hoặc video!")

    n = len(media_paths)
    duration_each = max(3.0, (audio_duration + 1.0) / n)
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
    fade = 0.4
    clips = []

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

    current = clips[0]["path"]
    current_dur = clips[0]["duration"]

    for i in range(1, n):
        next_clip = clips[i]["path"]
        next_dur  = clips[i]["duration"]
        offset    = max(0.1, current_dur - fade)
        out = os.path.join(temp_dir, f"xfade_{i:03d}.mp4") if i < n - 1 else output

        subprocess.run([
            "ffmpeg", "-y",
            "-i", current, "-i", next_clip,
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


def _get_hook_font(size: int):
    """
    Load font cho hook text theo thứ tự ưu tiên:
    1. Nunito-ExtraBold.ttf (tải thủ công vào assets/) — đẹp nhất
    2. BeVietnamPro-Bold.ttf (tự tải)
    3. Fallback Windows
    """
    from PIL import ImageFont
    import requests

    # Ưu tiên 1: Nunito ExtraBold — phải tải thủ công từ fonts.google.com
    nunito = "assets/Nunito-ExtraBold.ttf"
    if os.path.exists(nunito):
        try:
            return ImageFont.truetype(nunito, size)
        except Exception:
            pass

    # Ưu tiên 2: Be Vietnam Pro Bold — tự tải
    beviet = "assets/BeVietnamPro-Bold.ttf"
    if not os.path.exists(beviet):
        os.makedirs("assets", exist_ok=True)
        print("[FONT] Tải Be Vietnam Pro Bold...")
        for url in [
            "https://github.com/letteratic/be-vietnam-pro/raw/master/fonts/ttf/BeVietnamPro-Bold.ttf",
            "https://github.com/googlefonts/BeVietnamPro/raw/main/fonts/ttf/BeVietnamPro-Bold.ttf",
        ]:
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200 and len(r.content) > 50000:
                    with open(beviet, "wb") as f:
                        f.write(r.content)
                    print("[FONT] Be Vietnam Pro OK")
                    break
            except Exception:
                continue

    if os.path.exists(beviet):
        try:
            return ImageFont.truetype(beviet, size)
        except Exception:
            pass

    # Fallback Windows — có hỗ trợ tiếng Việt
    for fp in [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue

    return ImageFont.load_default()


def _add_logo(video: str, logo: str, output: str):
    """Logo góc trên trái, 300px, hiện suốt video."""
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video,
        "-i", logo,
        "-filter_complex",
        "[1:v]scale=300:-1[logo];"
        "[0:v][logo]overlay=32:32",
        "-c:a", "copy",
        output
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[VIDEO] Logo lỗi (bỏ qua): {result.stderr[-200:]}")
        shutil.copy(video, output)


def _add_hook_overlay(video_path: str, hook_text: str, output: str):
    """
    Hook text 3 giây đầu:
    - Font Nunito ExtraBold (hoặc Be Vietnam Pro Bold)
    - Size 82px, chữ vàng #FFD700
    - Nền pill đen mờ ôm sát chữ
    - Shadow 16 lớp cực đậm
    """
    from PIL import Image, ImageDraw
    import json

    probe = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", video_path
    ], capture_output=True, text=True)
    info   = json.loads(probe.stdout)
    vs     = next(s for s in info["streams"] if s["codec_type"] == "video")
    width  = int(vs["width"])
    height = int(vs["height"])

    tmp_dir  = tempfile.mkdtemp()
    hook_img = os.path.join(tmp_dir, "hook.png")

    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient tối phía trên mạnh
    for y in range(int(height * 0.50)):
        alpha = int(200 * (1 - y / (height * 0.50)))
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

    font_size = 82
    font = _get_hook_font(font_size)

    # Wrap text tối đa 2 dòng
    max_w = int(width * 0.84)
    words, lines, cur = hook_text.split(), [], ""
    for word in words:
        test = (cur + " " + word).strip()
        try:
            bbox   = draw.textbbox((0, 0), test, font=font)
            w_test = bbox[2] - bbox[0]
        except Exception:
            w_test = len(test) * 38
        if w_test > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    lines = lines[:2]

    line_h  = font_size + 24
    total_h = len(lines) * line_h
    y_start = int(height * 0.30) - total_h // 2

    # Đo chiều rộng thật của từng dòng để vẽ pill đúng kích thước
    line_widths = []
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_widths.append(bbox[2] - bbox[0])
        except Exception:
            line_widths.append(len(line) * 38)

    pad_x, pad_y = 44, 20
    block_w = max(line_widths) + pad_x * 2
    block_h = total_h + pad_y * 2
    block_x = (width - block_w) // 2
    block_y = y_start - pad_y

    # Nền pill đen mờ
    draw.rounded_rectangle(
        [block_x, block_y, block_x + block_w, block_y + block_h],
        radius=28,
        fill=(0, 0, 0, 140)
    )

    for i, line in enumerate(lines):
        x = (width - line_widths[i]) // 2
        y = y_start + i * line_h

        # Shadow 16 lớp cực đậm
        for dx, dy in [
            (-6,0),(6,0),(0,-6),(0,6),
            (-6,-6),(6,-6),(-6,6),(6,6),
            (-4,-4),(4,-4),(-4,4),(4,4),
            (-3,0),(3,0),(0,-3),(0,3),
        ]:
            draw.text((x+dx, y+dy), line, font=font, fill=(0, 0, 0, 255))

        # Chữ vàng đậm
        draw.text((x, y), line, font=font, fill=(255, 215, 0, 255))

    img.save(hook_img, "PNG")

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path, "-i", hook_img,
        "-filter_complex",
        "[0:v][1:v]overlay=0:0:enable='between(t,0,3)'[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy", "-pix_fmt", "yuv420p",
        output
    ], capture_output=True, text=True)

    shutil.rmtree(tmp_dir, ignore_errors=True)

    if result.returncode != 0:
        print(f"[VIDEO] Hook lỗi: {result.stderr[-200:]}")
        shutil.copy(video_path, output)


def build_video(
    media_paths: list[str],
    audio_path: str,
    output_path: str,
    logo_path: str = None,
    bg_music_path: str = None,
    script: str = None,
) -> str:

    temp_dir = tempfile.mkdtemp()

    try:
        audio_duration = _get_duration(audio_path)
        print(f"[VIDEO] Audio: {audio_duration:.1f}s | {len(media_paths)} media files")

        items = _prepare_media(media_paths, temp_dir, audio_duration)

        silent_video = os.path.join(temp_dir, "silent.mp4")
        _build_concat_with_xfade(items, temp_dir, silent_video)

        if bg_music_path and os.path.exists(bg_music_path):
            final_audio = os.path.join(temp_dir, "mixed_audio.mp3")
            _mix_audio(audio_path, bg_music_path, audio_duration, final_audio)
        else:
            final_audio = audio_path

        merged = os.path.join(temp_dir, "merged.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", silent_video,
            "-i", final_audio,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-t", str(audio_duration),
            "-pix_fmt", "yuv420p",
            merged
        ], check=True, capture_output=True)

        # Hook overlay 3 giây đầu
        after_hook = os.path.join(temp_dir, "after_hook.mp4")
        if script:
            try:
                _add_hook_overlay(merged, script, after_hook)
                print(f"[VIDEO] Hook OK: {script[:50]}...")
            except Exception as e:
                print(f"[VIDEO] Hook lỗi (bỏ qua): {e}")
                shutil.copy(merged, after_hook)
        else:
            shutil.copy(merged, after_hook)

        # Logo góc trên trái
        if logo_path and os.path.exists(logo_path):
            print(f"[VIDEO] Thêm logo: {logo_path}")
            _add_logo(after_hook, logo_path, output_path)
        else:
            shutil.copy(after_hook, output_path)

        print(f"[VIDEO] Done → {output_path} ({_get_duration(output_path):.1f}s)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path