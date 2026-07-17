import subprocess
import os
import shutil
import tempfile
from PIL import Image, ImageOps


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
    fade = 0.4
    est_duration_each = (audio_duration + (n - 1) * fade) / n
    clip_max = min(est_duration_each, 6.0)

    temp_items = []
    video_durations = []
    num_images = 0

    for i, path in enumerate(media_paths):
        ext = path.lower().rsplit(".", 1)[-1]
        is_video = ext in ("mp4", "mov", "avi", "mkv", "webm")
        if is_video:
            out_path = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
            actual_dur = _process_video_clip(path, out_path, clip_duration=clip_max, filter_mode=filter_mode)
            temp_items.append({"path": out_path, "duration": actual_dur, "is_video": True, "index": i, "orig_path": path})
            video_durations.append(actual_dur)
        else:
            temp_items.append({"path": None, "duration": 0.0, "is_video": False, "index": i, "orig_path": path})
            num_images += 1

    if num_images > 0:
        total_video_dur = sum(video_durations)
        duration_image = (audio_duration + (n - 1) * fade - total_video_dur) / num_images
        duration_image = max(2.5, duration_image)
    else:
        duration_image = 3.0

    result = []
    for item in temp_items:
        if item["is_video"]:
            result.append({"path": item["path"], "duration": item["duration"], "is_video": True})
            print(f"[VIDEO] Clip {item['index']+1}: {item['duration']:.1f}s ← {os.path.basename(item['orig_path'])}")
        else:
            out_path = os.path.join(temp_dir, f"frame_{item['index']:03d}.jpg")
            _process_image(item["orig_path"], out_path)
            result.append({"path": out_path, "duration": duration_image, "is_video": False})
            print(f"[VIDEO] Ảnh {item['index']+1}: {duration_image:.1f}s ← {os.path.basename(item['orig_path'])}")

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


# ─── Âm thanh chấm câu ──────────────────────────────────────────────────────
# 4 kiểu tổng hợp dự phòng (dùng khi không có file thật trong assets/chimes/)
CHIME_STYLES = {
    "soft_bell": "🔔 Chuông nhẹ (tổng hợp)",
    "wood_tap": "🪵 Gõ gỗ (tổng hợp)",
    "subtle_tick": "✨ Tinh tế (tổng hợp)",
    "marimba": "🎵 Marimba (tổng hợp)",
    "random_custom": "🎧 Random 4 file thật (assets/chimes/) — khuyên dùng",
}


def list_custom_chime_files(chimes_dir: str = "assets/chimes") -> dict:
    """Quét assets/chimes/ tìm file mp3/wav thật bạn đã tải về."""
    result = {}
    if not os.path.isdir(chimes_dir):
        return result
    for fname in sorted(os.listdir(chimes_dir)):
        if fname.lower().endswith((".mp3", ".wav", ".m4a", ".ogg")):
            label = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ").strip().title()
            result[f"file:{fname}"] = f"🎧 {label}"
    return result


def _generate_chime_sound_effect(filepath: str, style: str = "soft_bell"):
    """
    Tổng hợp âm thanh chấm câu (dùng làm fallback khi không có file thật).
    Không còn kiểu sóng vuông "tè tè" cũ — thay bằng sóng sin có bội âm, envelope mượt.
    """
    import math, struct, wave, random

    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    sample_rate = 44100
    samples = []

    if style == "wood_tap":
        duration = 0.09
        num_samples = int(sample_rate * duration)
        rnd = random.Random(42)
        prev = 0.0
        for i in range(num_samples):
            t = i / sample_rate
            env = math.exp(-55 * t)
            noise = rnd.random() * 2 - 1
            prev = prev * 0.7 + noise * 0.3
            tone = math.sin(2 * math.pi * 170 * t)
            val = (0.5 * prev + 0.5 * tone) * env
            samples.append(val * 0.85)

    elif style == "subtle_tick":
        duration = 0.05
        num_samples = int(sample_rate * duration)
        for i in range(num_samples):
            t = i / sample_rate
            env = math.exp(-90 * t)
            val = math.sin(2 * math.pi * 1500 * t) * env
            samples.append(val * 0.32)

    elif style == "marimba":
        duration = 0.32
        num_samples = int(sample_rate * duration)
        base_freq = 523.0
        for i in range(num_samples):
            t = i / sample_rate
            env1 = math.exp(-7 * t)
            env2 = math.exp(-16 * t)
            val = (
                0.65 * math.sin(2 * math.pi * base_freq * t) * env1 +
                0.35 * math.sin(2 * math.pi * base_freq * 2.76 * t) * env2
            )
            attack = min(1.0, t / 0.008)
            samples.append(val * attack)

    else:  # "soft_bell" mặc định
        duration = 0.28
        num_samples = int(sample_rate * duration)
        base_freq = 1100.0
        for i in range(num_samples):
            t = i / sample_rate
            env1 = math.exp(-9 * t)
            env2 = math.exp(-15 * t)
            env3 = math.exp(-22 * t)
            val = (
                0.55 * math.sin(2 * math.pi * base_freq * t) * env1 +
                0.25 * math.sin(2 * math.pi * base_freq * 2.01 * t) * env2 +
                0.15 * math.sin(2 * math.pi * base_freq * 3.02 * t) * env3
            )
            attack = min(1.0, t / 0.006)
            samples.append(val * attack)

    with wave.open(filepath, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for val in samples:
            v = max(-1.0, min(1.0, val))
            wav_file.writeframes(struct.pack('<h', int(v * 28000)))


def _prepare_chime_pool(chime_style: str, chimes_dir: str = "assets/chimes") -> list:
    """
    Trả về DANH SÁCH file .wav đã chuẩn hoá (mono, 44100Hz, ≤0.6s, fade-out nhẹ).
    - "random_custom": dùng TẤT CẢ file thật trong assets/chimes/ làm 1 "hồ" âm thanh,
      mỗi lần kêu sẽ chọn ngẫu nhiên 1 file trong hồ này → nghe đa dạng, chân thật
      hơn hẳn so với lặp lại đúng 1 âm.
    - "file:<name>": chỉ dùng đúng 1 file cụ thể.
    - kiểu tổng hợp (soft_bell/wood_tap/...): sinh 1 file duy nhất.
    """
    os.makedirs("assets", exist_ok=True)

    if chime_style == "random_custom":
        custom = list_custom_chime_files(chimes_dir)
        if not custom:
            print("[AUDIO] assets/chimes/ trống — dùng chuông tổng hợp mặc định thay thế.")
            out = "assets/_chime_fallback.wav"
            _generate_chime_sound_effect(out, style="soft_bell")
            return [out]
        pool = []
        for idx, key in enumerate(custom.keys()):
            fname = key[len("file:"):]
            src = os.path.join(chimes_dir, fname)
            out = f"assets/_chime_custom_{idx}.wav"
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", src,
                    "-ac", "1", "-ar", "44100",
                    "-t", "0.6",
                    "-af", "afade=t=out:st=0.45:d=0.15,volume=0.9",
                    out
                ], check=True, capture_output=True)
                pool.append(out)
            except Exception as e:
                print(f"[AUDIO] Lỗi xử lý {src}: {e}")
        if not pool:
            out = "assets/_chime_fallback.wav"
            _generate_chime_sound_effect(out, style="soft_bell")
            return [out]
        print(f"[AUDIO] Random pool: {len(pool)} âm thanh thật từ assets/chimes/")
        return pool

    if chime_style and chime_style.startswith("file:"):
        fname = chime_style[len("file:"):]
        src = os.path.join(chimes_dir, fname)
        out = "assets/_chime_single.wav"
        if os.path.exists(src):
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", src,
                    "-ac", "1", "-ar", "44100",
                    "-t", "0.6",
                    "-af", "afade=t=out:st=0.45:d=0.15,volume=0.9",
                    out
                ], check=True, capture_output=True)
                return [out]
            except Exception as e:
                print(f"[AUDIO] Lỗi xử lý {src}: {e}")
        _generate_chime_sound_effect(out, style="soft_bell")
        return [out]

    out = "assets/_chime_synth.wav"
    _generate_chime_sound_effect(out, style=chime_style or "soft_bell")
    return [out]


def _create_chime_track(timestamps: list, total_duration: float, chime_pool_paths: list,
                         output_path: str, every_n: int = 4):
    """
    Ghép các mốc chime vào 1 track im lặng.
    - `every_n`: GIÃN THƯA tiếng ting — chỉ kêu 1 lần sau mỗi `every_n` mốc câu, thay vì
      kêu ở MỌI câu như bản cũ (đúng ý: "3-4 nhịp đọc mới có 1 tiếng ting").
    - Mỗi lần kêu RANDOM 1 âm trong `chime_pool_paths` → đa dạng, không bị lặp đều đều.
    """
    import wave, struct, random

    pools = []
    sample_rate = 44100
    params_ref = None
    for p in chime_pool_paths:
        with wave.open(p, 'r') as w:
            params = w.getparams()
            frames = w.readframes(params.nframes)
            samples = list(struct.unpack(f"<{params.nframes}h", frames))
            pools.append(samples)
            sample_rate = params.framerate
            params_ref = params

    if not pools:
        return

    total_samples = int(total_duration * sample_rate)
    track_samples = [0] * total_samples

    rnd = random.Random()
    selected_ts = timestamps[::max(1, every_n)]

    for t in selected_ts:
        chime_samples = rnd.choice(pools)
        start = int(t * sample_rate)
        for idx, s in enumerate(chime_samples):
            ti = start + idx
            if ti < total_samples:
                track_samples[ti] = max(-32768, min(32767, track_samples[ti] + s))

    with wave.open(output_path, 'w') as w:
        w.setparams(params_ref)
        w.writeframes(struct.pack(f"<{len(track_samples)}h", *track_samples))


def _mix_audio(voice_path, music_path, chimes_path, voice_duration, total_duration, output):
    inputs        = ["-i", voice_path]
    filter_inputs = ["[0:a]volume=1.0[v]"]
    mix_inputs    = ["[v]"]

    if music_path and os.path.exists(music_path):
        inputs += ["-stream_loop", "-1", "-i", music_path]
        idx = len(inputs) // 2 - 1
        filter_inputs.append(f"[{idx}:a]volume=0.15,atrim=0:{total_duration}[music]")
        mix_inputs.append("[music]")

    if chimes_path and os.path.exists(chimes_path):
        inputs += ["-i", chimes_path]
        idx = len(inputs) // 2 - 1
        filter_inputs.append(f"[{idx}:a]volume=0.6[chimes]")
        mix_inputs.append("[chimes]")

    filter_complex = ";".join(filter_inputs)
    num = len(mix_inputs)
    if num > 1:
        filter_complex += f";{''.join(mix_inputs)}amix=inputs={num}:duration=longest:dropout_transition=0[aout]"
        map_arg = "[aout]"
    else:
        filter_complex += ";[v]apad[aout]"
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


def generate_ending_image(width, height, logo_path, output_path):
    """
    Tạo một bức ảnh nền đen 9:16 và chèn logo doanh nghiệp vào chính giữa làm outro.
    """
    print(f"[IMAGE] Đang tạo ảnh outro kết thúc ({width}x{height}) với logo...")
    bg_color = (17, 17, 17)
    ending_img = Image.new("RGB", (width, height), color=bg_color)

    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")

            max_logo_width = int(width * 0.4)
            logo_ratio = logo.width / logo.height
            new_logo_width = min(logo.width, max_logo_width)
            new_logo_height = int(new_logo_width / logo_ratio)
            logo = logo.resize((new_logo_width, new_logo_height), Image.Resampling.LANCZOS)

            position = (
                (width - logo.width) // 2,
                (height - logo.height) // 2
            )

            ending_img.paste(logo, position, logo)
        except Exception as e:
            print(f"[⚠️ Warning] Không thể chèn logo vào ảnh outro: {e}. Sẽ dùng nền đen trơn.")

    ending_img.save(output_path)
    print(f"[SUCCESS] Đã tạo xong ảnh outro tạm thời tại: {output_path}")


def _add_logo(video: str, logo: str, output: str, voice_duration: float = None):
    enable = f":enable='between(t,0,{voice_duration})'" if voice_duration else ""
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video, "-i", logo,
        "-filter_complex",
        f"[1:v]scale=300:-1[logo];[0:v][logo]overlay=32:32{enable}",
        "-c:a", "copy",
        output
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[VIDEO] Logo lỗi (bỏ qua): {result.stderr[-200:]}")
        shutil.copy(video, output)


def _append_outro(main_video: str, outro_path: str, output_path: str):
    """
    Nối video chính với outro.mp4 đã dựng sẵn (từ generate_outro.py), có sẵn
    audio im lặng bên trong. Dùng ffmpeg concat filter, chuẩn hoá codec/khung
    hình/tần số mẫu âm thanh giữa 2 clip để tránh lỗi ghép.
    """
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", main_video, "-i", outro_path,
        "-filter_complex",
        "[0:v]scale=1080:1920,setsar=1,fps=30[v0];"
        "[1:v]scale=1080:1920,setsar=1,fps=30[v1];"
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        output_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[VIDEO] Ghép outro dựng sẵn lỗi (bỏ qua, giữ video không outro): {result.stderr[-300:]}")
        shutil.copy(main_video, output_path)


def build_video(
    media_paths: list[str],
    audio_path: str,
    output_path: str,
    logo_path: str = None,
    bg_music_path: str = None,
    transition_type: str = "fade",
    filter_mode: str = "Gốc (Không lọc)",
    show_ending: bool = True,
    use_chimes: bool = True,
    chime_style: str = "random_custom",
    chime_every_n: int = 4,
    srt_path: str = None,
) -> str:
    """
    Lưu ý: KHÔNG còn tham số `script`/hook — hook đã bị bỏ hẳn theo yêu cầu,
    để người dùng tự làm tay trên TikTok cho đa dạng hơn.
    """

    temp_dir = tempfile.mkdtemp()
    outro_path = "assets/outro.mp4"
    use_prerendered_outro = show_ending and os.path.exists(outro_path)

    try:
        audio_duration = _get_duration(audio_path)
        # Nếu đã có outro dựng sẵn (assets/outro.mp4): video chính chỉ dài bằng
        # audio, outro được nối thêm riêng ở cuối (không cần xử lý PIL mỗi lần nữa).
        # Nếu chưa có: giữ hành vi cũ — tự vẽ màn hình đen + logo tĩnh 3s.
        if use_prerendered_outro:
            total_duration = audio_duration
        else:
            total_duration = audio_duration + 3.0 if show_ending else audio_duration
        print(f"[VIDEO] Audio: {audio_duration:.1f}s (Total: {total_duration:.1f}s) | {len(media_paths)} media files")

        items = _prepare_media(media_paths, temp_dir, audio_duration, filter_mode=filter_mode)

        if show_ending and not use_prerendered_outro:
            ending_img_path = os.path.join(temp_dir, "ending_screen.jpg")
            generate_ending_image(1080, 1920, logo_path, ending_img_path)
            items.append({"path": ending_img_path, "duration": 3.4, "is_video": False})

            silent_dur = sum(item["duration"] for item in items) - (len(items) - 1) * 0.4
            if silent_dur < total_duration:
                diff = total_duration - silent_dur
                items[-1]["duration"] += diff
                print(f"[VIDEO] Adjusting ending screen duration by +{diff:.2f}s to match total_duration exactly")

        silent_video = os.path.join(temp_dir, "silent.mp4")
        _build_concat_with_xfade(items, temp_dir, silent_video, transition_type=transition_type, filter_mode=filter_mode)

        chimes_track = None
        if use_chimes and srt_path and os.path.exists(srt_path):
            import pysrt
            try:
                pool = _prepare_chime_pool(chime_style)
                subs = pysrt.open(srt_path, encoding="utf-8")
                timestamps = [sub.start.ordinal / 1000.0 for sub in subs]

                chimes_track = os.path.join(temp_dir, "chimes_track.wav")
                _create_chime_track(timestamps, audio_duration, pool, chimes_track, every_n=chime_every_n)
                print(f"[AUDIO] Chime track OK: {len(timestamps[::max(1, chime_every_n)])} tiếng "
                      f"(giãn thưa mỗi {chime_every_n} câu, random trong {len(pool)} âm)")
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

        # Ghép outro dựng sẵn (nếu có) trước khi gắn logo — logo góc trên trái
        # chỉ hiện trong đoạn nội dung chính (voice_duration), không đè lên outro.
        if use_prerendered_outro:
            with_outro = os.path.join(temp_dir, "with_outro.mp4")
            _append_outro(merged, outro_path, with_outro)
            merged = with_outro
            print(f"[VIDEO] Đã ghép outro dựng sẵn: {outro_path}")

        # Không còn bước hook overlay — logo gắn thẳng lên video đã merge
        if logo_path and os.path.exists(logo_path):
            print(f"[VIDEO] Thêm logo: {logo_path}")
            _add_logo(merged, logo_path, output_path,
                      voice_duration=audio_duration if show_ending else None)
        else:
            shutil.copy(merged, output_path)

        print(f"[VIDEO] Done → {output_path} ({_get_duration(output_path):.1f}s)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path