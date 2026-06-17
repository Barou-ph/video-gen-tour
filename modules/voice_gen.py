import requests
import re
import os
import time
from dotenv import load_dotenv

load_dotenv()

VOICES = {
    "lannhi - Nữ Bắc (nhẹ nhàng)":  "lannhi",
    "myan - Nữ Bắc (trẻ trung)":     "myan",
    "leminh - Nam Bắc (trầm ấm)":    "leminh",
    "thanhthu - Nữ Nam (ngọt ngào)": "thanhthu",
    "giahuy - Nam Nam (năng động)":  "giahuy",
    "linhsan - Nữ Trung (dịu dàng)": "linhsan",
}

# Thêm vào voice_gen.py, trước clean_script

ABBREVIATIONS = {
    # Tour
    r'\b(\d+)N(\d+)Đ\b':   lambda m: f"{m.group(1)} ngày {m.group(2)} đêm",
    r'\bN(\d+)\b':          lambda m: f"ngày {m.group(1)}",

    # Đơn vị tiền
    r'\b(\d+)tr\b':         lambda m: f"{m.group(1)} triệu",
    r'\b(\d+)k\b':          lambda m: f"{m.group(1)} nghìn",
    r'\b(\d+)đ\b':          lambda m: f"{m.group(1)} đồng",
    r'(\d+)\.000đ':         lambda m: f"{m.group(1)} nghìn đồng",
    r'(\d+)\.000\.000đ':    lambda m: f"{m.group(1)} triệu đồng",

    # Thời gian
    r'\bT(\d)\b':           lambda m: f"thứ {m.group(1)}",
    r'\bCN\b':              "chủ nhật",
    r'\bSN\b':              "sinh nhật",

    # Du lịch phổ biến
    r'\bHDV\b':             "hướng dẫn viên",
    r'\bKS\b':              "khách sạn",
    r'\bVJ\b':              "Vietjet",
    r'\bVNA\b':             "Vietnam Airlines",
    r'\bTP\.HCM\b':         "thành phố Hồ Chí Minh",
    r'\bHN\b':              "Hà Nội",
    r'\bĐN\b':              "Đà Nẵng",
    r'\bĐL\b':              "Đà Lạt",
    r'\bNT\b':              "Nha Trang",
    r'\bPQ\b':              "Phú Quốc",
    r'\bHPG\b':             "Hạ Long",
    r'\bBB\b':              "Bắc Bộ",
    r'\bpax\b':             "người",
    r'\bvé\b':              "vé",
    r'\bpkg\b':             "gói",

    # Số điện thoại — đọc từng số
    r'\b0(\d{9})\b':        lambda m: "0 " + " ".join(m.group(1)),
}


def normalize_script(text: str) -> str:
    """Mở rộng viết tắt để AI TTS đọc tự nhiên hơn."""
    for pattern, replacement in ABBREVIATIONS.items():
        if callable(replacement):
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        else:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

def clean_script(text: str) -> str:
    text = re.sub(r'[*_#`~<>|\\]', '', text)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = normalize_script(text)   # ← thêm dòng này
    return text


def text_to_speech(
    script: str,
    output_path: str,
    rate: str = "+0%",
    volume: str = "+0%",
    voice: str = "lannhi",
    speed: str = "1",
) -> str:
    fpt_key = os.getenv("FPT_API_KEY")
    script  = clean_script(script)
    print(f"[TTS] FPT AI — {len(script)} ký tự | voice={voice} | speed={speed}")

    if len(script) > 500:
        mid   = script.rfind('. ', 0, len(script) // 2) + 2
        part1 = script[:mid].strip()
        part2 = script[mid:].strip()
        path1 = output_path.replace(".mp3", "_p1.mp3")
        path2 = output_path.replace(".mp3", "_p2.mp3")
        _fpt_request(part1, path1, fpt_key, voice, speed)
        _fpt_request(part2, path2, fpt_key, voice, speed)
        _concat_audio(path1, path2, output_path)
    else:
        _fpt_request(script, output_path, fpt_key, voice, speed)

    return output_path


def _fpt_request(text: str, output_path: str, api_key: str, voice: str, speed: str):
    response = requests.post(
        "https://api.fpt.ai/hmi/tts/v5",
        headers={"api-key": api_key, "voice": voice, "speed": speed},
        data=text.encode("utf-8"),
        timeout=30,
    )
    data = response.json()
    if data.get("error") != 0:
        raise RuntimeError(f"FPT TTS lỗi: {data}")

    audio_url = data["async"]
    print(f"[TTS] Link: {audio_url}")

    for attempt in range(20):
        time.sleep(2)
        try:
            r = requests.get(audio_url, timeout=15)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                print(f"[TTS] OK lần {attempt+1} — {len(r.content)//1024}KB")
                return
        except Exception as e:
            print(f"[TTS] Lỗi lần {attempt+1}: {e}")

    raise RuntimeError("FPT TTS timeout sau 40s.")


def _concat_audio(path1: str, path2: str, output: str):
    import subprocess, tempfile
    p1 = os.path.abspath(path1).replace("\\", "/")
    p2 = os.path.abspath(path2).replace("\\", "/")
    list_file = os.path.join(tempfile.gettempdir(), "audio_list.txt")
    with open(list_file, "w") as f:
        f.write(f"file '{p1}'\n")
        f.write(f"file '{p2}'\n")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Ghép audio thất bại: {result.stderr[-200:]}")
    print(f"[TTS] Ghép audio xong → {output}")