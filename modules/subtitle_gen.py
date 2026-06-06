import whisper
import subprocess
import os

def generate_subtitles(audio_path: str, srt_path: str) -> str:
    """Dùng Whisper nhận dạng audio → tạo file .srt."""
    
    # Load model nhỏ nhất để chạy nhanh (base hoặc small)
    model = whisper.load_model("base")
    
    result = model.transcribe(
        audio_path,
        language="vi",          # Chỉ định tiếng Việt để tăng độ chính xác
        task="transcribe"
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
    """Dùng FFmpeg burn subtitle vào video."""
    
    # Style chữ: trắng, viền đen, font lớn, ở dưới màn hình
    subtitle_style = (
        "FontName=Arial,"
        "FontSize=18,"
        "PrimaryColour=&HFFFFFF,"   # Màu chữ: trắng
        "OutlineColour=&H000000,"   # Viền: đen
        "Outline=2,"
        "Alignment=2,"              # Căn giữa dưới
        "MarginV=40"                # Cách đáy 40px
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
        "-c:a", "copy",
        output_path
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path