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


def _get_ffmpeg_filter_str(mode: str) -> str:
    if not mode:
        return ""
    if "Ấm áp" in mode or "Golden" in mode or "Warm" in mode:
        return "eq=contrast=1.05:saturation=1.2:brightness=0.02,colorbalance=rm=0.08:gm=0.02:bm=-0.06:rh=0.05:bh=-0.05"
    elif "Huyền bí" in mode or "Mysterious" in mode or "Cool" in mode:
        return "eq=contrast=1.1:brightness=-0.02:saturation=0.95,colorbalance=rm=-0.05:bm=0.1:rh=-0.05:bh=0.05"
    elif "Cổ điển" in mode or "Vintage" in mode or "Retro" in mode:
        return "eq=contrast=0.95:brightness=0.02:saturation=0.9,colorbalance=rm=0.05:gm=-0.02:bm=-0.05"
    elif "Rực rỡ" in mode or "Vibrant" in mode or "Cinematic" in mode:
        return "eq=contrast=1.12:saturation=1.35"
    return ""


def _process_video_clip(path: str, out_path: str, clip_duration: float = 4.0, filter_mode: str = None):
    src_duration = _get_duration(path)
    use_duration = min(src_duration, clip_duration)
    
    vf_filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "fps=30"
    ]
    filter_str = _get_ffmpeg_filter_str(filter_mode)
    if filter_str:
        vf_filters.append(filter_str)
        
    subprocess.run([
        "ffmpeg", "-y", "-i", path,
        "-t", str(use_duration),
        "-vf", ",".join(vf_filters),
        "-c:v", "libx264", "-preset", "fast",
        "-an", "-pix_fmt", "yuv420p",
        out_path
    ], check=True, capture_output=True)
    return use_duration


def _prepare_media(media_paths: list, temp_dir: str, audio_duration: float, filter_mode: str = None):
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
            actual_dur = _process_video_clip(path, out_path, clip_duration=clip_max, filter_mode=filter_mode)
            result.append({"path": out_path, "duration": actual_dur, "is_video": True})
            print(f"[VIDEO] Clip {i+1}: {actual_dur:.1f}s ← {os.path.basename(path)}")
        else:
            out_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
            _process_image(path, out_path)
            result.append({"path": out_path, "duration": duration_each, "is_video": False})
            print(f"[VIDEO] Ảnh {i+1}: {duration_each:.1f}s ← {os.path.basename(path)}")

    return result


def _build_concat_with_xfade(items: list, temp_dir: str, output: str, transition_type: str = "fade", filter_mode: str = None):
    fade = 0.4
    clips = []

    for i, item in enumerate(items):
        if item["is_video"]:
            clips.append({"path": item["path"], "duration": item["duration"]})
        else:
            clip_path = os.path.join(temp_dir, f"img_clip_{i:03d}.mp4")
            vf_filters = ["scale=1080:1920", "fps=30"]
            filter_str = _get_ffmpeg_filter_str(filter_mode)
            if filter_str:
                vf_filters.append(filter_str)
                
            subprocess.run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", item["path"],
                "-vf", ",".join(vf_filters),
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
            f"[0:v][1:v]xfade=transition={transition_type}:duration={fade}:offset={offset:.3f}[v]",
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            out
        ], check=True, capture_output=True)

        current     = out
        current_dur = offset + next_dur


def _generate_chime_sound_effect(filepath: str):
    import math
    import struct
    import wave
    import os

    if os.path.exists(filepath):
        return

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    sample_rate = 44100
    duration = 0.35  # seconds
    num_samples = int(sample_rate * duration)
    
    with wave.open(filepath, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)   # 16-bit
        wav_file.setframerate(sample_rate)
        
        # Crystal chime frequency 1500Hz with 3000Hz, 4500Hz overtones
        for i in range(num_samples):
            t = i / sample_rate
            decay = math.exp(-12 * t)  # quick fade-out
            
            val = (
                0.6 * math.sin(2 * math.pi * 1500 * t) +
                0.3 * math.sin(2 * math.pi * 3000 * t) +
                0.1 * math.sin(2 * math.pi * 4500 * t)
            ) * decay
            
            val = max(-1.0, min(1.0, val))
            sample = int(val * 32767)
            wav_file.writeframes(struct.pack('<h', sample))


def _create_chime_track(timestamps: list[float], total_duration: float, chime_path: str, output_path: str):
    import wave
    import struct
    
    with wave.open(chime_path, 'r') as w_chime:
        params = w_chime.getparams()
        chime_frames = w_chime.readframes(params.nframes)
        chime_samples = list(struct.unpack(f"<{params.nframes}h", chime_frames))
        
    sample_rate = params.framerate
    total_samples = int(total_duration * sample_rate)
    track_samples = [0] * total_samples
    
    for t in timestamps:
        start_sample = int(t * sample_rate)
        # overlay chime
        for idx, sample in enumerate(chime_samples):
            target_idx = start_sample + idx
            if target_idx < total_samples:
                track_samples[target_idx] = max(-32768, min(32767, track_samples[target_idx] + sample))
                
    with wave.open(output_path, 'w') as w_out:
        w_out.setparams(params)
        w_out.writeframes(struct.pack(f"<{len(track_samples)}h", *track_samples))


def _mix_audio(
    voice_path: str,
    music_path: str,
    chimes_path: str,
    voice_duration: float,
    total_duration: float,
    output: str
):
    inputs = ["-i", voice_path]
    filter_inputs = ["[0:a]volume=1.0[v]"]
    mix_inputs = ["[v]"]
    
    if music_path and os.path.exists(music_path):
        inputs += ["-stream_loop", "-1", "-i", music_path]
        music_idx = len(inputs) // 2 - 1
        filter_inputs += [f"[{music_idx}:a]volume=0.15,atrim=0:{total_duration}[music]"]
        mix_inputs += ["[music]"]
        
    if chimes_path and os.path.exists(chimes_path):
        inputs += ["-i", chimes_path]
        chimes_idx = len(inputs) // 2 - 1
        filter_inputs += [f"[{chimes_idx}:a]volume=0.6[chimes]"]
        mix_inputs += ["[chimes]"]
        
    filter_complex = ";".join(filter_inputs)
    num_inputs = len(mix_inputs)
    
    if num_inputs > 1:
        mix_str = "".join(mix_inputs)
        filter_complex += f";{mix_str}amix=inputs={num_inputs}:duration=longest:dropout_transition=0[aout]"
        map_arg = "[aout]"
    else:
        filter_complex += f";[v]apad[aout]"
        map_arg = "[aout]"
        
    subprocess.run([
        "ffmpeg", "-y"
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", map_arg,
        "-c:a", "libmp3lame",
        "-t", str(total_duration),
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


def _add_logo(video: str, logo: str, output: str, voice_duration: float = None):
    """Logo góc trên trái, 300px, hiện suốt phần video chính."""
    if voice_duration is not None:
        overlay_filter = f"[0:v][logo]overlay=32:32:enable='between(t,0,{voice_duration})'"
    else:
        overlay_filter = "[0:v][logo]overlay=32:32"
        
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video,
        "-i", logo,
        "-filter_complex",
        f"[1:v]scale=300:-1[logo];{overlay_filter}",
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


def generate_ending_image(width: int, height: int, logo_path: str, output_path: str):
    from PIL import Image, ImageDraw
    import os
    
    # Create white canvas
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # 1. Logo at the top
    logo_y = 200
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path)
            logo_w = 400
            # Keep aspect ratio
            logo_h = int(logo_img.height * (logo_w / logo_img.width))
            logo_img = logo_img.resize((logo_w, logo_h), Image.LANCZOS)
            
            # If logo has alpha channel, paste with mask
            if logo_img.mode in ("RGBA", "P", "LA"):
                if logo_img.mode == "P":
                    logo_img = logo_img.convert("RGBA")
                img.paste(logo_img, ((width - logo_w) // 2, logo_y), mask=logo_img.split()[-1])
            else:
                img.paste(logo_img, ((width - logo_w) // 2, logo_y))
            logo_y += logo_h + 120
        except Exception as e:
            print(f"[ENDING] Lỗi load logo: {e}")
            logo_y += 200
    else:
        logo_y += 200
        
    # 2. "follow" button
    btn_w = 450
    btn_h = 130
    btn_x = (width - btn_w) // 2
    btn_y = logo_y
    
    draw.rounded_rectangle(
        [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
        radius=45,
        fill=(230, 159, 36) # E69F24
    )
    
    # Text "follow" in red
    font_follow = _get_hook_font(60)
    try:
        bbox = draw.textbbox((0, 0), "follow", font=font_follow)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = 200, 60
    
    draw.text(
        (btn_x + (btn_w - tw) // 2, btn_y + (btn_h - th) // 2 - 8),
        "follow",
        font=font_follow,
        fill=(196, 28, 36) # red
    )
    
    # Draw arrow / cursor clicking on follow button
    arrow_x = btn_x + 90
    arrow_y = btn_y - 60
    draw.polygon(
        [(arrow_x, arrow_y), (arrow_x + 35, arrow_y + 15), (arrow_x + 15, arrow_y + 35)],
        fill=(0, 0, 0)
    )
    draw.line(
        [(arrow_x - 10, arrow_y - 10), (arrow_x + 15, arrow_y + 15)],
        fill=(0, 0, 0),
        width=8
    )
    
    # 3. Text: "để cập nhật những thông tin\nDU LỊCH HOT NHẤT!!!"
    text_y = btn_y + btn_h + 100
    font_text = _get_hook_font(42)
    lines = [
        "để cập nhật những thông tin",
        "DU LỊCH HOT NHẤT!!!"
    ]
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font_text)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 20
        color = (196, 28, 36) if "HOT NHẤT" in line else (128, 20, 24)
        draw.text(
            ((width - tw) // 2, text_y),
            line,
            font=font_text,
            fill=color
        )
        text_y += 75
        
    # 4. Illustration at the bottom
    ill_path = "assets/ending_illustration.png"
    if os.path.exists(ill_path):
        try:
            ill_img = Image.open(ill_path)
            ill_w = 900
            ill_h = int(ill_img.height * (ill_w / ill_img.width))
            ill_img = ill_img.resize((ill_w, ill_h), Image.LANCZOS)
            ill_y = height - ill_h - 120
            
            if ill_img.mode in ("RGBA", "P", "LA"):
                if ill_img.mode == "P":
                    ill_img = ill_img.convert("RGBA")
                img.paste(ill_img, ((width - ill_w) // 2, ill_y), mask=ill_img.split()[-1])
            else:
                img.paste(ill_img, ((width - ill_w) // 2, ill_y))
        except Exception as e:
            print(f"[ENDING] Lỗi load minh họa: {e}")
            
    img.save(output_path, "JPEG", quality=95)


def build_video(
    media_paths: list[str],
    audio_path: str,
    output_path: str,
    logo_path: str = None,
    bg_music_path: str = None,
    script: str = None,
    transition_type: str = "fade",
    filter_mode: str = "Gốc (Không lọc)",
    show_ending: bool = True,
    use_chimes: bool = True,
    srt_path: str = None,
) -> str:

    temp_dir = tempfile.mkdtemp()

    try:
        audio_duration = _get_duration(audio_path)
        total_duration = audio_duration + 3.0 if show_ending else audio_duration
        print(f"[VIDEO] Audio: {audio_duration:.1f}s (Total: {total_duration:.1f}s) | {len(media_paths)} media files")

        items = _prepare_media(media_paths, temp_dir, audio_duration, filter_mode=filter_mode)
        
        if show_ending:
            ending_img_path = os.path.join(temp_dir, "ending_screen.jpg")
            generate_ending_image(1080, 1920, logo_path, ending_img_path)
            items.append({"path": ending_img_path, "duration": 3.4, "is_video": False})

        silent_video = os.path.join(temp_dir, "silent.mp4")
        _build_concat_with_xfade(items, temp_dir, silent_video, transition_type=transition_type, filter_mode=filter_mode)

        chimes_track = None
        if use_chimes and srt_path and os.path.exists(srt_path):
            import pysrt
            try:
                chime_wav = "assets/chime.wav"
                _generate_chime_sound_effect(chime_wav)
                
                subs = pysrt.open(srt_path, encoding="utf-8")
                timestamps = [sub.start.ordinal / 1000.0 for sub in subs]
                
                chimes_track = os.path.join(temp_dir, "chimes_track.wav")
                _create_chime_track(timestamps, audio_duration, chime_wav, chimes_track)
                print(f"[AUDIO] Chime track OK: {len(timestamps)} dings")
            except Exception as e:
                print(f"[AUDIO] Lỗi tạo chime track: {e}")

        final_audio = os.path.join(temp_dir, "final_audio.mp3")
        _mix_audio(
            voice_path=audio_path,
            music_path=bg_music_path,
            chimes_path=chimes_track,
            voice_duration=audio_duration,
            total_duration=total_duration,
            output=final_audio
        )

        merged = os.path.join(temp_dir, "merged.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", silent_video,
            "-i", final_audio,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-t", str(total_duration),
            "-pix_fmt", "yuv420p",
            merged
        ], check=True, capture_output=True)

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

        if logo_path and os.path.exists(logo_path):
            print(f"[VIDEO] Thêm logo: {logo_path}")
            _add_logo(after_hook, logo_path, output_path, voice_duration=audio_duration if show_ending else None)
        else:
            shutil.copy(after_hook, output_path)

        print(f"[VIDEO] Done → {output_path} ({_get_duration(output_path):.1f}s)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path