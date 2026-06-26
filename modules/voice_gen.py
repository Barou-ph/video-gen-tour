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
    r'\bHPG\b':             "Hạ Long",
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
    voice: str = "lannhi",
    speed: str = "1",
) -> str:
    fpt_key = os.getenv("FPT_API_KEY")
    script  = clean_script(script)
    print(f"[TTS] FPT AI — {len(script)} ký tự | voice={voice} | speed={speed}")

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

        print(f"[TTS] Chia script: part1={len(part1)} ký tự | part2={len(part2)} ký tự")

        if len(part1) < 10 or len(part2) < 10:
            print("[TTS] Phần chia quá ngắn — gửi nguyên 1 lần")
            _fpt_request(script, output_path, fpt_key, voice, speed)
        else:
            path1 = output_path.replace(".mp3", "_p1.mp3")
            path2 = output_path.replace(".mp3", "_p2.mp3")
            _fpt_request(part1, path1, fpt_key, voice, speed)
            time.sleep(3)
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

    # Poll lần đầu sau 3 giây
    time.sleep(3)
    for attempt in range(40):
        try:
            r = requests.get(audio_url, timeout=15)
            # File âm thanh thật sự sẽ có kích thước lớn (> 2KB), lỗi hoặc xử lý thường có dạng JSON/XML dung lượng nhỏ
            if r.status_code == 200 and len(r.content) > 2000:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                print(f"[TTS] OK lần {attempt+1} — {len(r.content)//1024}KB")
                return
            status_desc = f"status={r.status_code}, size={len(r.content)}B"
            print(f"[TTS] Chờ... lần {attempt+1} ({status_desc})")
        except Exception as e:
            print(f"[TTS] Request lỗi lần {attempt+1}: {e}")
        time.sleep(3)

    raise RuntimeError("FPT TTS timeout sau 120s. Vui lòng kiểm tra lại kết nối mạng hoặc thử lại sau ít phút.")


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