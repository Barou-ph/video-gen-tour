import subprocess
import os
from PIL import Image
import tempfile
import shutil

def build_video(
    media_paths: list[str],
    audio_path: str,
    output_path: str,
    logo_path: str = None
) -> str:
    """
    Ghép ảnh/video + audio thành video dọc 9:16.
    Mỗi ảnh hiển thị khoảng 4 giây, có hiệu ứng zoom nhẹ (Ken Burns).
    """
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Lấy thời lượng audio để tính số ảnh cần dùng
        audio_duration = _get_duration(audio_path)
        
        # Xử lý mỗi ảnh: resize về 1080x1920 (9:16)
        prepared = _prepare_media(media_paths, temp_dir, audio_duration)
        
        # Tạo file list cho FFmpeg concat
        list_file = os.path.join(temp_dir, "filelist.txt")
        with open(list_file, "w") as f:
            for item in prepared:
                f.write(f"file '{item['path']}'\n")
                f.write(f"duration {item['duration']}\n")
        
        # Bước 1: Ghép ảnh thành video câm
        raw_video = os.path.join(temp_dir, "raw.mp4")
        _concat_images(list_file, raw_video)
        
        # Bước 2: Ghép audio vào video
        video_with_audio = os.path.join(temp_dir, "with_audio.mp4")
        _merge_audio(raw_video, audio_path, video_with_audio)
        
        # Bước 3: Thêm logo (nếu có) ở 5 giây cuối
        if logo_path and os.path.exists(logo_path):
            _add_logo(video_with_audio, logo_path, audio_duration, output_path)
        else:
            shutil.copy(video_with_audio, output_path)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return output_path


def _get_duration(audio_path: str) -> float:
    """Lấy thời lượng file audio bằng FFprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path
    ], capture_output=True, text=True)
    return float(result.stdout.strip())


def _prepare_media(media_paths: list, temp_dir: str, total_duration: float) -> list:
    
    image_paths = [p for p in media_paths if p.lower().endswith(
        ('.jpg', '.jpeg', '.png', '.webp')
    )]
    
    if not image_paths:
        raise ValueError("Cần ít nhất 1 ảnh để tạo video!")
    
    duration_each = min(6.0, max(3.0, total_duration / len(image_paths)))
    
    prepared = []
    for i, img_path in enumerate(image_paths):
        out_path = os.path.join(temp_dir, f"frame_{i:03d}.jpg")
        
        img = Image.open(img_path)
        
        # ✅ Fix: chuyển RGBA/P/LA → RGB trước khi lưu JPEG
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])  # dùng alpha làm mask
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        img = _crop_to_916(img)
        img = img.resize((1080, 1920), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=95)
        
        prepared.append({"path": out_path, "duration": duration_each})
    
    return prepared


def _crop_to_916(img: Image.Image) -> Image.Image:
    """Crop ảnh vào giữa theo tỉ lệ 9:16."""
    w, h = img.size
    target_ratio = 9 / 16
    current_ratio = w / h
    
    if current_ratio > target_ratio:
        # Ảnh quá rộng → crop 2 bên
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        # Ảnh quá cao → crop trên dưới
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    
    return img


def _concat_images(list_file: str, output: str):
    """Ghép ảnh thành video bằng FFmpeg concat."""
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-vf", "scale=1080:1920,fps=30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        output
    ], check=True, capture_output=True)


def _merge_audio(video: str, audio: str, output: str):
    """Ghép audio vào video, cắt theo độ dài ngắn hơn."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video,
        "-i", audio,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",     # Cắt theo track ngắn hơn
        output
    ], check=True, capture_output=True)


def _add_logo(video: str, logo: str, duration: float, output: str):
    """Thêm logo vào 5 giây cuối video, căn góc phải dưới."""
    logo_start = max(0, duration - 5)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video,
        "-i", logo,
        "-filter_complex",
        (
            f"[1:v]scale=200:-1[logo];"  # Resize logo 200px chiều ngang
            f"[0:v][logo]overlay="
            f"W-w-30:H-h-30:"            # Vị trí: góc phải dưới, cách 30px
            f"enable='between(t,{logo_start},{duration})'"  # Chỉ hiện lúc cuối
        ),
        "-c:a", "copy",
        output
    ], check=True, capture_output=True)