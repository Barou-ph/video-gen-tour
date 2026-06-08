# test_tts.py — đặt ở thư mục gốc project
# Chạy: python test_tts.py
import subprocess
import sys
import os

def test_tts_subprocess():
    """
    Chạy Edge TTS trong subprocess riêng — tránh hoàn toàn conflict asyncio với Streamlit.
    Đây cũng chính là fix cho voice_gen.py.
    """
    script = "Đà Lạt đang gọi tên bạn! Tour 3 ngày 2 đêm chỉ từ 2 triệu 9. Thác Datanla hùng vĩ, đồi chè Cầu Đất xanh mướt, và chợ đêm lung linh đang chờ bạn khám phá. Đặt tour ngay hôm nay để nhận ưu đãi đặc biệt!"
    output  = "test_tts_output.mp3"

    print(f"Script ({len(script)} ký tự): {script[:80]}...")

    # Dùng edge-tts CLI thay vì Python API — không bị asyncio conflict
    cmd = [
        sys.executable, "-m", "edge_tts",
        "--voice", "vi-VN-HoaiMyNeural",
        "--rate",  "+0%",
        "--text",  script,
        "--write-media", output,
    ]

    print("Chạy edge-tts CLI...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print("THẤT BẠI")
    else:
        size = os.path.getsize(output) if os.path.exists(output) else 0
        print(f"THÀNH CÔNG — {output} ({size//1024}KB)")

if __name__ == "__main__":
    test_tts_subprocess()