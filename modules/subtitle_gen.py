import subprocess
import os


def generate_subtitles(audio_path: str, srt_path: str, script: str = None) -> str:
    """
    Tạo SRT từ script text — chia đều theo thời lượng audio.
    Chính xác 100% vì dùng script gốc, không qua Whisper.
    """
    # Lấy thời lượng audio
    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", audio_path
    ], capture_output=True, text=True)
    total_duration = float(probe.stdout.strip())

    # Tách script thành các câu ngắn
    sentences = _split_sentences(script)
    print(f"[SUB] {len(sentences)} câu / {total_duration:.1f}s")

    # Chia thời gian đều cho từng câu
    dur_each = total_duration / len(sentences)

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, sent in enumerate(sentences):
            start = i * dur_each
            end   = min((i + 1) * dur_each, total_duration)
            f.write(f"{i+1}\n")
            f.write(f"{_to_srt_time(start)} --> {_to_srt_time(end)}\n")
            f.write(f"{sent}\n\n")

    return srt_path


def _split_sentences(text: str) -> list:
    """Tách text thành câu ngắn ~8-12 từ mỗi câu."""
    import re

    # Tách theo dấu câu trước
    raw = re.split(r'(?<=[.!?])\s+', text.strip())

    # Với câu dài hơn 12 từ, chia tiếp
    result = []
    for sent in raw:
        words = sent.split()
        if len(words) <= 12:
            result.append(sent.strip())
        else:
            # Chia thành chunks ~8 từ
            chunk_size = 8
            for j in range(0, len(words), chunk_size):
                chunk = " ".join(words[j:j+chunk_size])
                if chunk.strip():
                    result.append(chunk.strip())

    return [s for s in result if s]


def _to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _get_font(size: int):
    from PIL import ImageFont
    import requests

    font_path = "assets/RobotoBold.ttf"
    if not os.path.exists(font_path):
        os.makedirs("assets", exist_ok=True)
        print("[SUB] Tải font Roboto Bold...")
        url = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf"
        r = requests.get(url, timeout=15)
        with open(font_path, "wb") as f:
            f.write(r.content)

    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        for p in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
        return ImageFont.load_default()


def burn_subtitles(video_path: str, srt_path: str, output_path: str, subtitle_style: str = "Badge (Khung chữ Vàng/Đỏ)") -> str:
    """Burn subtitle vào video dùng Pillow + FFmpeg."""
    import tempfile, shutil, json
    from PIL import Image, ImageDraw

    tmp_dir = tempfile.mkdtemp()

    try:
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", video_path
        ], capture_output=True, text=True)
        info   = json.loads(probe.stdout)
        vs     = next(s for s in info["streams"] if s["codec_type"] == "video")
        width  = int(vs["width"])
        height = int(vs["height"])
        num, den = map(int, vs["r_frame_rate"].split("/"))
        fps    = num / den

        import pysrt
        subs = pysrt.open(srt_path, encoding="utf-8")

        print(f"[SUB] Xuất frames ({width}x{height} @ {fps:.0f}fps)...")
        frames_dir = os.path.join(tmp_dir, "frames")
        os.makedirs(frames_dir)
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, "-q:v", "2",
            os.path.join(frames_dir, "frame_%06d.jpg")
        ], check=True, capture_output=True)

        font = _get_font(54)
        # Metrics thật của font — dùng để tính chiều cao badge cố định,
        # không phụ thuộc vào việc chữ có dấu (ạ/ệ/ộ...) hay không.
        ascent, descent = font.getmetrics()

        frame_files = sorted(os.listdir(frames_dir))
        print(f"[SUB] Vẽ subtitle lên {len(frame_files)} frames...")

        for i, fname in enumerate(frame_files):
            frame_time = i / fps
            sub_text   = ""
            for sub in subs:
                if sub.start.ordinal / 1000 <= frame_time <= sub.end.ordinal / 1000:
                    sub_text = sub.text.strip()
                    break

            if not sub_text:
                continue

            fpath = os.path.join(frames_dir, fname)
            img   = Image.open(fpath).convert("RGB")
            draw  = ImageDraw.Draw(img)

            max_w = int(width * 0.85)
            words, lines, cur = sub_text.split(), [], ""
            for word in words:
                test = (cur + " " + word).strip()
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] > max_w and cur:
                    lines.append(cur)
                    cur = word
                else:
                    cur = test
            if cur:
                lines.append(cur)

            if "Badge" in subtitle_style:
                pad_x = 24
                pad_y = 16
                gap   = 14  # khoảng cách giữa các badge, để không dính/đè nhau
                box_h  = ascent + descent + pad_y * 2
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2

                for line_idx, line in enumerate(lines):
                    bbox = draw.textbbox((0, 0), line, font=font)
                    tw   = bbox[2] - bbox[0]
                    x    = (width - tw) // 2

                    # Alternating colors: even -> yellow, odd -> red
                    if line_idx % 2 == 0:
                        bg_color = (229, 184, 44, 255)  # E5B82C
                    else:
                        bg_color = (196, 28, 36, 255)   # C41C24

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x - pad_x, y_cur, x + tw + pad_x, y_cur + box_h],
                        radius=12,
                        fill=bg_color
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    # Căn chữ theo baseline thật của font (ascent) để luôn nằm giữa box theo chiều dọc
                    text_y = y_cur + pad_y - bbox[1]
                    draw.text((x, text_y), line, font=font, fill=(255, 255, 255))
                    y_cur += line_h
            else:
                gap = 10
                box_h  = ascent + descent + 12  # pad
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2

                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    tw   = bbox[2] - bbox[0]
                    x    = (width - tw) // 2
                    pad  = 12

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x - pad, y_cur, x + tw + pad, y_cur + box_h],
                        radius=8,
                        fill=(0, 0, 0, 140)
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    text_y = y_cur + (pad // 2) - bbox[1]
                    draw.text((x, text_y), line, font=font, fill=(255, 255, 255),
                              stroke_width=3, stroke_fill=(0, 0, 0))
                    y_cur += line_h

            img.save(fpath, "JPEG", quality=95)

        print("[SUB] Ghép frames thành video cuối...")
        subprocess.run([
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%06d.jpg"),
            "-i", video_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy", "-pix_fmt", "yuv420p",
            output_path
        ], check=True, capture_output=True)

        print(f"[SUB] Done → {output_path}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path