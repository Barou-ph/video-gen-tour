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


# Các kiểu subtitle có thể chọn trong app.py (dùng đúng chuỗi này cho selectbox)
SUBTITLE_STYLES = [
    "Badge (Khung chữ Vàng/Đỏ)",
    "Standard (Nền đen mờ)",
    "Neon (Viền phát sáng)",
    "Gradient (Khung liền)",
    "Minimal (Trắng viền đen)",
]


def burn_subtitles(video_path: str, srt_path: str, output_path: str, subtitle_style: str = "Badge (Khung chữ Vàng/Đỏ)") -> str:
    """Burn subtitle vào video dùng Pillow + FFmpeg."""
    import tempfile, shutil, json
    from PIL import Image, ImageDraw, ImageFilter

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

            # Bề rộng khung dùng CHUNG cho mọi dòng trong cùng 1 subtitle
            # (theo dòng dài nhất) để các badge canh thẳng hàng, không lệch cỡ.
            line_widths = []
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_widths.append(bbox[2] - bbox[0])
            common_tw = max(line_widths) if line_widths else 0

            if "Badge" in subtitle_style:
                pad_x = 24
                pad_y = 16
                gap   = 14
                box_h  = ascent + descent + pad_y * 2
                box_w  = common_tw + pad_x * 2
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2

                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = x_box + (box_w - tw) // 2

                    if line_idx % 2 == 0:
                        bg_color = (229, 184, 44, 255)  # E5B82C
                    else:
                        bg_color = (196, 28, 36, 255)   # C41C24

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x_box, y_cur, x_box + box_w, y_cur + box_h],
                        radius=12,
                        fill=bg_color
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_y = y_cur + pad_y - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255))
                    y_cur += line_h

            elif "Neon" in subtitle_style:
                # Không có nền — chữ trắng với viền phát sáng (glow) màu tím/hồng xen kẽ
                gap = 16
                box_h  = ascent + descent
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2

                neon_colors = [(255, 60, 180), (60, 220, 255)]  # hồng neon / xanh cyan neon

                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = (width - tw) // 2
                    glow_color = neon_colors[line_idx % 2]

                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_y = y_cur - bbox[1]

                    # Lớp glow: vẽ chữ màu neon mờ dần ra ngoài bằng blur, rồi chồng chữ trắng sắc nét lên trên
                    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    glow_draw = ImageDraw.Draw(glow_layer)
                    glow_draw.text((text_x, text_y), line, font=font, fill=(*glow_color, 255))
                    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(6))

                    img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255),
                              stroke_width=2, stroke_fill=glow_color)
                    y_cur += line_h

            elif "Gradient" in subtitle_style:
                # Một khung DUY NHẤT bao trọn tất cả các dòng, nền gradient tím -> hồng
                pad_x = 28
                pad_y = 18
                line_gap = 8
                box_h_each = ascent + descent
                total_text_h = len(lines) * box_h_each + (len(lines) - 1) * line_gap
                box_w = common_tw + pad_x * 2
                box_h = total_text_h + pad_y * 2
                x_box = (width - box_w) // 2
                y_box = int(height * 0.84) - box_h // 2

                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                grad = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
                top_color = (124, 58, 237)     # tím
                bottom_color = (236, 72, 153)  # hồng
                for gy in range(box_h):
                    t = gy / max(1, box_h - 1)
                    r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
                    g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
                    b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
                    for gx in range(box_w):
                        grad.putpixel((gx, gy), (r, g, b, 235))

                mask = Image.new("L", (box_w, box_h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, box_w, box_h], radius=16, fill=255)
                overlay.paste(grad, (x_box, y_box), mask)

                img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                draw = ImageDraw.Draw(img)

                y_cur = y_box + pad_y
                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = x_box + (box_w - tw) // 2
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_y = y_cur - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255))
                    y_cur += box_h_each + line_gap

            elif "Minimal" in subtitle_style:
                # Không nền, chỉ chữ trắng đậm viền đen — phong cách caption gọn của Shorts/Reels
                gap = 16
                box_h  = ascent + descent
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2

                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = (width - tw) // 2
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_y = y_cur - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255),
                              stroke_width=4, stroke_fill=(0, 0, 0))
                    y_cur += line_h

            else:
                # "Standard (Nền đen mờ)"
                gap = 10
                box_h  = ascent + descent + 12
                box_w  = common_tw + 24
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2

                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = x_box + (box_w - tw) // 2

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x_box, y_cur, x_box + box_w, y_cur + box_h],
                        radius=8,
                        fill=(0, 0, 0, 140)
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_y = y_cur + 6 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255),
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