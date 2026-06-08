import whisper
import subprocess
import os


def generate_subtitles(audio_path: str, srt_path: str) -> str:
    """Dùng Whisper nhận dạng audio → tạo file .srt."""

    # Load model nhỏ nhất để chạy nhanh (base hoặc small)
    model = whisper.load_model("base")

    result = model.transcribe(
        audio_path,
        language="vi",  # Chỉ định tiếng Việt để tăng độ chính xác
        task="transcribe",
    )

    # Chuyển kết quả Whisper sang định dạng SRT
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(result["segments"], start=1):
            start = _seconds_to_srt_time(segment["start"])
            end = _seconds_to_srt_time(segment["end"])
            text = segment["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    return srt_path


def _seconds_to_srt_time(seconds: float) -> str:
    """Chuyển số giây thành định dạng HH:MM:SS,mmm của SRT."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def burn_subtitles(video_path: str, srt_path: str, output_path: str) -> str:
    """Burn subtitle vào video dùng moviepy — tránh lỗi FFmpeg path trên Windows."""
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
    import pysrt

    video = VideoFileClip(video_path)
    subs = pysrt.open(srt_path, encoding="utf-8")

    clips = [video]
    for sub in subs:
        start = sub.start.ordinal / 1000
        end = sub.end.ordinal / 1000
        txt = (
            TextClip(
                sub.text,
                fontsize=45,
                font="Arial",
                color="white",
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(video.w - 80, None),
            )
            .set_start(start)
            .set_end(end)
            .set_position(("center", 0.80), relative=True)
        )
        clips.append(txt)

    final = CompositeVideoClip(clips)
    final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
    return output_path
