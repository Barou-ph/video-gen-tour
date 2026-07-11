import requests
import re
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Danh sách giọng Viettel AI — dùng đúng voice code từ API docs
VOICES = {
    "Quỳnh Anh - Nữ Bắc (tự nhiên)":    "hn-quynhanh",
    "Phương Trang - Nữ Bắc (ấm áp)":    "hn-phuongtrang",
    "Thảo Chi - Nữ Bắc (nhẹ nhàng)":    "hn-thaochi",
    "Thanh Hà - Nữ Bắc (rõ ràng)":      "hn-thanhha",
    "Thanh Phương - Nữ Bắc (chuyên nghiệp)": "hn-thanhphuong",
    "Mai Ngọc - Nữ Trung (dịu dàng)":   "hue-maingoc",
    "Diễm My - Nữ Nam (ngọt ngào)":     "hcm-diemmy",
    "Phương Ly - Nữ Nam (trẻ trung)":   "hcm-phuongly",
    "Thùy Dung - Nữ Nam (mềm mại)":     "hcm-thuydung",
    "Thùy Duyên - Nữ Nam (tươi vui)":   "hcm-thuyduyen",
    "Thanh Tùng - Nam Bắc (trầm ấm)":   "hn-thanhtung",
    "Nam Khánh - Nam Bắc (mạnh mẽ)":    "hn-namkhanh",
    "Bảo Quốc - Nam Trung (đặc sắc)":   "hue-baoquoc",
    "Minh Quân - Nam Nam (năng động)":  "hcm-minhquan",
}

# Tốc độ map từ slider 0/1/2 sang float Viettel
SPEED_MAP = {
    "0": 0.8,
    "1": 1.0,
    "2": 1.2,
}

ABBREVIATIONS = {
    r'\b(\d+)N(\d+)Đ\b':   lambda m: f"{m.group(1)} ngày {m.group(2)} đêm",
    r'\bN(\d+)\b':          lambda m: f"ngày {m.group(1)}",
    r'\b(\d+)tr\b':         lambda m: f"{m.group(1)} triệu",
    r'\b(\d+)k\b':          lambda m: f"{m.group(1)} nghìn",
    r'\b(\d+)đ\b':          lambda m: f"{m.group(1)} đồng",
    r'(\d+)\.000đ':         lambda m: f"{m.group(1)} nghìn đồng",
    r'(\d+)\.000\.000đ':    lambda m: f"{m.group(1)} triệu đồng",
    r'\bT(\d)\b':           lambda m: f"thứ {m.group(1)}",
    r'\bCN\b':              "chủ nhật",
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
    r'\bpax\b':             "người",
    r'\b0(\d{9})\b':        lambda m: "0 " + " ".join(m.group(1)),
}


def normalize_script(text: str) -> str:
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
    text = normalize_script(text)
    return text


def text_to_speech(
    script: str,
    output_path: str,
    rate: str = "+0%",
    volume: str = "+0%",
    voice: str = "hn-quynhanh",
    speed: str = "1",
) -> str:
    api_token = os.getenv("VIETTEL_API_KEY")
    if not api_token:
        raise RuntimeError("Chưa có VIETTEL_API_KEY! Nhập vào sidebar hoặc file .env")

    script = clean_script(script)
    speed_float = SPEED_MAP.get(str(speed), 1.0)
    print(f"[TTS] Viettel AI — {len(script)} ký tự | voice={voice} | speed={speed_float}")

    # Chia script nếu quá dài (Viettel giới hạn ~500 ký tự/request)
    if len(script) > 500:
        mid_point = len(script) // 2
        split_pos = -1

        for punct in ['. ', '! ', '? ', '... ']:
            pos = script.rfind(punct, mid_point - 100, mid_point + 100)
            if pos != -1:
                split_pos = pos + len(punct)
                break

        if split_pos == -1:
            pos = script.rfind('. ', 0, mid_point)
            if pos != -1:
                split_pos = pos + 2

        if split_pos == -1:
            split_pos = script.rfind(' ', mid_point - 50, mid_point + 50)
            if split_pos == -1:
                split_pos = mid_point

        part1 = script[:split_pos].strip()
        part2 = script[split_pos:].strip()

        print(f"[TTS] Chia: part1={len(part1)} ký tự | part2={len(part2)} ký tự")

        if len(part1) < 10 or len(part2) < 10:
            _viettel_request(script, output_path, api_token, voice, speed_float)
        else:
            path1 = output_path.replace(".mp3", "_p1.mp3")
            path2 = output_path.replace(".mp3", "_p2.mp3")
            _viettel_request(part1, path1, api_token, voice, speed_float)
            time.sleep(1)
            _viettel_request(part2, path2, api_token, voice, speed_float)
            _concat_audio(path1, path2, output_path)
    else:
        _viettel_request(script, output_path, api_token, voice, speed_float)

    return output_path


def _viettel_request(text: str, output_path: str, token: str, voice: str, speed: float):
    """
    Gọi Viettel AI TTS API đúng theo docs:
    - token nằm trong body (không phải header)
    - trả về binary audio trực tiếp
    """
    payload = {
        "text":            text,
        "voice":           voice,
        "speed":           speed,
        "tts_return_option": 3,      # 3 = MP3
        "token":           token,
        "without_filter":  False,    # True = chất lượng cao hơn nhưng chậm hơn
    }

    response = requests.post(
        "https://viettelai.vn/tts/speech_synthesis",
        headers={
            "accept":       "*/*",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    # Kiểm tra lỗi
    if response.status_code != 200:
        try:
            err = response.json()
            msg = err.get("vi_message") or err.get("en_message") or response.text[:300]
        except Exception:
            msg = response.text[:300]
        raise RuntimeError(f"Viettel TTS lỗi {response.status_code}: {msg}")

    # Kiểm tra content — nếu là JSON thì lỗi, nếu là binary thì OK
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        raise RuntimeError(f"Viettel TTS trả về JSON thay vì audio: {response.text[:300]}")

    if len(response.content) < 1000:
        raise RuntimeError(
            f"Viettel TTS trả về file quá nhỏ ({len(response.content)} bytes). "
            f"Response: {response.text[:200]}"
        )

    with open(output_path, "wb") as f:
        f.write(response.content)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"[TTS] Viettel OK — {size_kb:.0f}KB → {output_path}")


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