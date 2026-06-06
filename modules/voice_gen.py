import asyncio
import edge_tts
import os
import re
import subprocess

VOICE_VI = "vi-VN-HoaiMyNeural"

def clean_script(text: str) -> str:
    import re
    # Xóa ký tự markdown
    text = re.sub(r'[*_#`~<>|\\]', '', text)
    # Xóa số thứ tự đầu dòng
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    # Xóa ký tự điều khiển ẩn (zero-width space, BOM, v.v.)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
    # Thay xuống dòng bằng dấu chấm để TTS đọc tự nhiên
    text = re.sub(r'\n+', '. ', text)
    # Chuẩn hóa khoảng trắng
    text = re.sub(r'\s+', ' ', text).strip()
    # Giới hạn độ dài
    if len(text) > 2000:
        text = text[:2000]
    return text


def text_to_speech(script: str, output_path: str, rate: str = "+0%", volume: str = "+0%") -> str:
    """Chuyển script thành file audio .mp3."""

    script = clean_script(script)

    # Đảm bảo rate đúng định dạng
    rate = rate.strip()
    if not rate.startswith(("+", "-")):
        rate = "+" + rate

    print(f"[TTS] Độ dài script: {len(script)} ký tự")
    print(f"[TTS] Rate: {rate}")
    print(f"[TTS] Xem trước: {script[:100]}...")

    async def _synthesize():
        communicate = edge_tts.Communicate(
            text=script,
            voice=VOICE_VI,
            rate=rate,
            volume="+0%",
        )
        await communicate.save(output_path)

    asyncio.run(_synthesize())

    # Kiểm tra file có được tạo và có dữ liệu không
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError(
            f"Edge TTS tạo file thất bại hoặc file rỗng.\n"
            f"Thử chạy lệnh test này trong terminal:\n"
            f'  python -c "import asyncio, edge_tts; asyncio.run(edge_tts.Communicate(\'Xin chào\', voice=\'vi-VN-HoaiMyNeural\').save(\'test.mp3\'))"'
        )

    size_kb = os.path.getsize(output_path) / 1024
    print(f"[TTS] OK — {size_kb:.0f}KB → {output_path}")
    return output_path