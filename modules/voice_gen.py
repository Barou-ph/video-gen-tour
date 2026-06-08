import requests
import re
import os
import time
from dotenv import load_dotenv

load_dotenv()
FPT_API_KEY = os.getenv("FPT_API_KEY")
VOICE = "linhsan"  # đổi giọng tại đây nếu muốn


def clean_script(text: str) -> str:
    text = re.sub(r"[*_#`~<>|\\]", "", text)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_to_speech(
    script: str, output_path: str, rate: str = "+0%", volume: str = "+0%"
) -> str:
    script = clean_script(script)
    print(f"[TTS] FPT AI — {len(script)} ký tự | voice={VOICE}")

    # Bước 1: Gửi script, nhận link async
    response = requests.post(
        "https://api.fpt.ai/hmi/tts/v5",
        headers={"api-key": FPT_API_KEY, "voice": VOICE, "speed": ""},
        data=script.encode("utf-8"),
    )

    data = response.json()
    if data.get("error") != 0:
        raise RuntimeError(f"FPT TTS lỗi: {data}")

    audio_url = data["async"]
    print(f"[TTS] Link audio: {audio_url}")

    # Bước 2: Chờ FPT xử lý rồi download (thường 2-5 giây)
    for attempt in range(10):
        time.sleep(3)
        audio_resp = requests.get(audio_url)
        if audio_resp.status_code == 200 and len(audio_resp.content) > 1000:
            break
        print(f"[TTS] Chờ FPT xử lý... lần {attempt+1}")
    else:
        raise RuntimeError("FPT TTS timeout sau 30s.")

    with open(output_path, "wb") as f:
        f.write(audio_resp.content)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"[TTS] OK — {size_kb:.0f}KB → {output_path}")
    return output_path
