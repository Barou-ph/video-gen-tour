# diag.py
from dotenv import load_dotenv

load_dotenv()

from modules.voice_gen import text_to_speech
from modules.video_builder import _get_duration, build_video
from PIL import Image
import os

# Tạo audio
text = "Đây là câu test. Xem audio có bị cắt không. Một hai ba bốn năm sáu bảy tám chín mười. Liên hệ ngay hôm nay để nhận ưu đãi đặc biệt!"
text_to_speech(text, "diag_audio.mp3")
print(f"Audio duration: {_get_duration('diag_audio.mp3'):.1f}s")

# Tạo 3 ảnh giả
os.makedirs("diag_imgs", exist_ok=True)
for i in range(3):
    img = Image.new("RGB", (1080, 1920), color=(i * 80, 100, 150))
    img.save(f"diag_imgs/img_{i}.jpg")

# Chạy build_video
print("\nChạy build_video...")
build_video(
    media_paths=[f"diag_imgs/img_{i}.jpg" for i in range(3)],
    audio_path="diag_audio.mp3",
    output_path="diag_output.mp4",
)

print(f"\nVideo duration: {_get_duration('diag_output.mp4'):.1f}s")
print(f"Audio duration: {_get_duration('diag_audio.mp3'):.1f}s")
print("=> Nếu 2 số này khớp nhau là OK")
