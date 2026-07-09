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


def _generate_chime_sound_effect(filepath: str):
    import math, struct, wave
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    sample_rate = 44100
    duration    = 0.12
    num_samples = int(sample_rate * duration)
    with wave.open(filepath, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(num_samples):
            t          = i / sample_rate
            phase_pop  = 2 * math.pi * (800 * t - 350 * (t ** 2) / duration)
            decay_pop  = math.exp(-25 * t)
            val_pop    = math.sin(phase_pop) * decay_pop
            if t < 0.03:
                phase_click = 2 * math.pi * (3000 * t - 40000 * (t ** 2))
                decay_click = math.exp(-150 * t)
                val_click   = math.sin(phase_click) * decay_click
            else:
                val_click = 0.0
            val    = max(-1.0, min(1.0, 0.6 * val_pop + 0.4 * val_click))
            sample = int(val * 32767)
            wav_file.writeframes(struct.pack('<h', sample))


def _create_chime_track(timestamps: list, total_duration: float, chime_path: str, output_path: str):
    import wave, struct
    with wave.open(chime_path, 'r') as w:
        params        = w.getparams()
        chime_frames  = w.readframes(params.nframes)
        chime_samples = list(struct.unpack(f"<{params.nframes}h", chime_frames))
    sample_rate   = params.framerate
    total_samples = int(total_duration * sample_rate)
    track_samples = [0] * total_samples
    for t in timestamps:
        start = int(t * sample_rate)
        for idx, s in enumerate(chime_samples):
            ti = start + idx
            if ti < total_samples:
                track_samples[ti] = max(-32768, min(32767, track_samples[ti] + s))
    with wave.open(output_path, 'w') as w:
        w.setparams(params)
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

        if logo_path and os.path.exists(logo_path):
            print(f"[VIDEO] Thêm logo: {logo_path}")
            _add_logo(merged, logo_path, output_path, voice_duration=audio_duration if show_ending else None)
        else:
            shutil.copy(merged, output_path)

        print(f"[VIDEO] Done → {output_path} ({_get_duration(output_path):.1f}s)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path