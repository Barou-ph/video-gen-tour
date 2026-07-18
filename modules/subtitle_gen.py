import subprocess
import os


def generate_subtitles(audio_path: str, srt_path: str, script: str = None) -> str:
    """
    Tạo SRT từ script text — chia theo tỉ lệ số từ mỗi câu để khớp giọng đọc.
    Chính xác 100% vì dùng script gốc, không qua Whisper.
    """
    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", audio_path
    ], capture_output=True, text=True)
    total_duration = float(probe.stdout.strip())

    sentences = _split_sentences(script)
    print(f"[SUB] {len(sentences)} câu / {total_duration:.1f}s")

    word_counts = [max(1, len(s.split())) for s in sentences]
    total_words = sum(word_counts)

    with open(srt_path, "w", encoding="utf-8") as f:
        cursor = 0.0
        for i, (sent, wc) in enumerate(zip(sentences, word_counts)):
            dur = total_duration * (wc / total_words)
            start = cursor
            end   = min(cursor + dur, total_duration)
            f.write(f"{i+1}\n")
            f.write(f"{_to_srt_time(start)} --> {_to_srt_time(end)}\n")
            f.write(f"{sent}\n\n")
            cursor = end

    return srt_path


# Liên từ tiếng Việt dùng làm điểm ngắt tự nhiên, ưu tiên hơn cắt cứng theo số từ
_NATURAL_BREAK_WORDS = {
    "và", "nhưng", "mà", "rồi", "hoặc", "hay", "vì", "nên",
    "để", "khi", "nếu", "còn", "với", "cùng", "tại",
}

_MIN_CHUNK_WORDS = 5  # mỗi câu SRT tối thiểu 5 từ, tránh mảnh vụn kiểu "vĩ,"


def _split_sentences(text: str) -> list:
    """
    Tách text thành các cụm để hiển thị phụ đề, ưu tiên ngắt tại điểm nghỉ tự
    nhiên (dấu phẩy, liên từ) thay vì cắt cứng theo số từ cố định — tránh kiểu
    ngắt cắt lìa 1 cụm từ để lại mảnh mồ côi ở đầu câu sau (vd: "vĩ, Vườn...").
    """
    import re

    raw = re.split(r'(?<=[.!?])\s+', text.strip())

    result = []
    for sent in raw:
        result.extend(_split_long_clause(sent.strip()))

    return [s for s in result if s]


def _split_long_clause(sent: str, target_max: int = 10) -> list:
    words = sent.split()
    if len(words) <= target_max:
        return [sent] if sent else []

    if "," in sent:
        parts = [p.strip() for p in sent.split(",") if p.strip()]
        out = []
        for p in parts:
            out.extend(_split_long_clause(p, target_max))
        return _merge_short_fragments(out)

    mid = len(words) // 2
    best_idx, best_dist = None, None
    for idx, w in enumerate(words):
        if w.lower().strip(".,!?") in _NATURAL_BREAK_WORDS:
            dist = abs(idx - mid)
            if best_dist is None or dist < best_dist:
                best_dist, best_idx = dist, idx
    if best_idx is not None and 1 <= best_idx <= len(words) - 1:
        left  = " ".join(words[:best_idx])
        right = " ".join(words[best_idx:])
        if left and right:
            return _split_long_clause(left, target_max) + _split_long_clause(right, target_max)

    n = len(words)
    num_chunks = max(2, round(n / 8))
    base = n // num_chunks
    chunks, idx = [], 0
    for c in range(num_chunks):
        remaining_chunks = num_chunks - c
        remaining_words = n - idx
        size = base if c < num_chunks - 1 else remaining_words
        if remaining_chunks == 1 and remaining_words < _MIN_CHUNK_WORDS and chunks:
            chunks[-1] += " " + " ".join(words[idx:])
            idx = n
            break
        chunks.append(" ".join(words[idx:idx + size]))
        idx += size
    return [c.strip() for c in chunks if c.strip()]


def _merge_short_fragments(parts: list, min_words: int = _MIN_CHUNK_WORDS) -> list:
    """
    Gộp các mảnh quá ngắn (sau khi tách theo dấu phẩy) vào mảnh liền kề,
    tránh để lại 1-2 từ mồ côi đứng riêng thành 1 câu SRT.
    """
    if not parts:
        return parts
    merged = [parts[0]]
    for p in parts[1:]:
        if len(p.split()) < min_words:
            merged[-1] = merged[-1] + ", " + p
        else:
            merged.append(p)
    if len(merged) >= 2 and len(merged[0].split()) < min_words:
        merged[1] = merged[0] + ", " + merged[1]
        merged.pop(0)
    return merged


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


# Các kiểu subtitle có thể chọn trong app.py (dùng đúng chuỗi này cho selectbox).
# "Trắng (Không nền)" đặt ĐẦU TIÊN -> mặc định index 0: chỉ chữ trắng viền đen,
# KHÔNG có khung nền vàng/đen gì cả — đúng yêu cầu khách.
SUBTITLE_STYLES = [
    "Trắng (Không nền)",
    "Badge Vàng (Đồng nhất)",
    "Badge (Khung chữ Vàng/Đỏ)",
    "Standard (Nền đen mờ)",
    "Neon (Viền phát sáng)",
    "Gradient (Khung liền)",
    "Pill Vàng (Bo tròn hoàn toàn)",
    "Outline Vàng (Viền, nền trong suốt)",
]


def _wrap_natural(draw, text: str, font, max_w: int, min_words_per_line: int = 4) -> list:
    """
    Bọc dòng chữ sao cho mỗi dòng có TỐI THIỂU min_words_per_line từ, tránh
    kiểu bọc tham lam (greedy) hay để lại 1 từ mồ côi ở dòng cuối. QUAN TRỌNG:
    khi gộp dòng cuối quá ngắn vào dòng trước, LUÔN kiểm tra dòng gộp có vượt
    max_w hay không — nếu vượt thì KHÔNG gộp (thà để dòng ngắn còn hơn tràn
    khỏi màn hình).
    """
    import math

    words = text.split()
    if len(words) <= min_words_per_line:
        return [text] if text else []

    def line_w(s):
        bbox = draw.textbbox((0, 0), s, font=font)
        return bbox[2] - bbox[0]

    full_w = line_w(text)
    if full_w <= max_w:
        return [text]

    num_lines = max(2, math.ceil(full_w / max_w))

    while True:
        target_w = full_w / num_lines * 1.08
        lines, cur = [], ""
        for word in words:
            test = (cur + " " + word).strip()
            if line_w(test) > target_w and cur:
                lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)

        fits = all(line_w(l) <= max_w for l in lines)
        counts = [len(l.split()) for l in lines]
        min_ok = min(counts) >= min_words_per_line or sum(counts) < min_words_per_line * 2

        if fits and min_ok:
            return lines

        num_lines += 1
        if num_lines >= len(words):
            lines, cur = [], ""
            for word in words:
                test = (cur + " " + word).strip()
                if line_w(test) > max_w and cur:
                    lines.append(cur)
                    cur = word
                else:
                    cur = test
            if cur:
                lines.append(cur)
            if len(lines) >= 2 and len(lines[-1].split()) < min_words_per_line:
                merged_candidate = lines[-2] + " " + lines[-1]
                if line_w(merged_candidate) <= max_w:
                    lines[-2] = merged_candidate
                    lines.pop()
            return lines


def _enforce_max_width(draw, lines: list, font, max_w: int) -> list:
    """
    Lớp bảo hiểm cuối cùng: đảm bảo TUYỆT ĐỐI không dòng nào vượt quá max_w —
    chặn triệt để lỗi tràn chữ khỏi khung hình.
    """
    def line_w(s):
        bbox = draw.textbbox((0, 0), s, font=font)
        return bbox[2] - bbox[0]

    result = []
    for line in lines:
        if line_w(line) <= max_w:
            result.append(line)
            continue
        words = line.split()
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if line_w(test) > max_w and cur:
                result.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            result.append(cur)
    return result


def burn_subtitles(video_path: str, srt_path: str, output_path: str, subtitle_style: str = "Trắng (Không nền)") -> str:
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
            lines = _wrap_natural(draw, sub_text, font, max_w, min_words_per_line=4)
            lines = _enforce_max_width(draw, lines, font, max_w)

            line_widths = []
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_widths.append(bbox[2] - bbox[0])
            common_tw = max(line_widths) if line_widths else 0
            common_tw = min(common_tw, max_w)

            if "Không nền" in subtitle_style:
                # MẶC ĐỊNH: chỉ chữ trắng viền đen, KHÔNG có khung nền gì cả
                gap = 16
                box_h  = ascent + descent
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2

                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = (width - tw) // 2
                    bbox = draw.textbbox((0, 0), line, font=font)
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255),
                              stroke_width=4, stroke_fill=(0, 0, 0))
                    y_cur += line_h

            elif "Đồng nhất" in subtitle_style:
                # 1 màu vàng nhạt DUY NHẤT cho mọi dòng, không xen kẽ đậm/nhạt
                pad_x = 24
                pad_y = 16
                gap   = 14
                box_h  = ascent + descent + pad_y * 2
                box_w  = min(common_tw + pad_x * 2, width - 20)
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2

                solid_yellow = (250, 200, 60, 255)  # vàng nhạt

                for line_idx, line in enumerate(lines):
                    tw = min(line_widths[line_idx], box_w - pad_x * 2)
                    text_x = x_box + (box_w - tw) // 2

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x_box, y_cur, x_box + box_w, y_cur + box_h],
                        radius=12,
                        fill=solid_yellow
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    bbox = draw.textbbox((0, 0), line, font=font)
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(35, 26, 4))
                    y_cur += line_h

            elif "Badge" in subtitle_style:
                # Bản gốc: Vàng/Đỏ xen kẽ — giữ nguyên không đổi
                pad_x = 24
                pad_y = 16
                gap   = 14
                box_h  = ascent + descent + pad_y * 2
                box_w  = min(common_tw + pad_x * 2, width - 20)
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2

                for line_idx, line in enumerate(lines):
                    tw = min(line_widths[line_idx], box_w - pad_x * 2)
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
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255))
                    y_cur += line_h

            elif "Pill" in subtitle_style:
                pad_x = 30
                pad_y = 14
                gap   = 16
                box_h  = ascent + descent + pad_y * 2
                box_w  = min(common_tw + pad_x * 2, width - 20)
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2
                pill_radius = box_h // 2

                for line_idx, line in enumerate(lines):
                    tw = min(line_widths[line_idx], box_w - pad_x * 2)
                    text_x = x_box + (box_w - tw) // 2

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x_box, y_cur, x_box + box_w, y_cur + box_h],
                        radius=pill_radius,
                        fill=(247, 195, 30, 255)
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    bbox = draw.textbbox((0, 0), line, font=font)
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(35, 26, 4))
                    y_cur += line_h

            elif "Outline" in subtitle_style:
                pad_x = 22
                pad_y = 14
                gap   = 16
                box_h  = ascent + descent + pad_y * 2
                box_w  = min(common_tw + pad_x * 2, width - 20)
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2
                outline_color = (247, 195, 30, 255)

                for line_idx, line in enumerate(lines):
                    tw = min(line_widths[line_idx], box_w - pad_x * 2)
                    text_x = x_box + (box_w - tw) // 2

                    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ov_draw = ImageDraw.Draw(overlay)
                    ov_draw.rounded_rectangle(
                        [x_box, y_cur, x_box + box_w, y_cur + box_h],
                        radius=12,
                        fill=(0, 0, 0, 90),
                        outline=outline_color,
                        width=3
                    )
                    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(img)

                    bbox = draw.textbbox((0, 0), line, font=font)
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255),
                              stroke_width=2, stroke_fill=(0, 0, 0))
                    y_cur += line_h

            elif "Neon" in subtitle_style:
                gap = 16
                box_h  = ascent + descent
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2

                neon_colors = [(255, 60, 180), (60, 220, 255)]

                for line_idx, line in enumerate(lines):
                    tw = line_widths[line_idx]
                    text_x = (width - tw) // 2
                    glow_color = neon_colors[line_idx % 2]

                    bbox = draw.textbbox((0, 0), line, font=font)
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]

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
                pad_x = 28
                pad_y = 18
                line_gap = 8
                box_h_each = ascent + descent
                total_text_h = len(lines) * box_h_each + (len(lines) - 1) * line_gap
                box_w = min(common_tw + pad_x * 2, width - 20)
                box_h_full = total_text_h + pad_y * 2
                x_box = (width - box_w) // 2
                y_box = int(height * 0.84) - box_h_full // 2

                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                grad = Image.new("RGBA", (box_w, box_h_full), (0, 0, 0, 0))
                top_color = (124, 58, 237)
                bottom_color = (236, 72, 153)
                for gy in range(box_h_full):
                    t = gy / max(1, box_h_full - 1)
                    r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
                    g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
                    b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
                    for gx in range(box_w):
                        grad.putpixel((gx, gy), (r, g, b, 235))

                mask = Image.new("L", (box_w, box_h_full), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, box_w, box_h_full], radius=16, fill=255)
                overlay.paste(grad, (x_box, y_box), mask)

                img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                draw = ImageDraw.Draw(img)

                y_cur = y_box + pad_y
                for line_idx, line in enumerate(lines):
                    tw = min(line_widths[line_idx], box_w - pad_x * 2)
                    text_x = x_box + (box_w - tw) // 2
                    bbox = draw.textbbox((0, 0), line, font=font)
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h_each - real_h) // 2 - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=(255, 255, 255))
                    y_cur += box_h_each + line_gap

            else:
                # "Standard (Nền đen mờ)"
                gap = 10
                box_h  = ascent + descent + 12
                box_w  = min(common_tw + 24, width - 20)
                line_h = box_h + gap
                total_h = len(lines) * line_h - gap
                y_cur = int(height * 0.84) - total_h // 2
                x_box = (width - box_w) // 2

                for line_idx, line in enumerate(lines):
                    tw = min(line_widths[line_idx], box_w - 24)
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
                    real_h = bbox[3] - bbox[1]
                    text_y = y_cur + (box_h - real_h) // 2 - bbox[1]
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