# diag_fpt.py
import requests, time
from dotenv import load_dotenv
import os
load_dotenv()

FPT_API_KEY = os.getenv("FPT_API_KEY")

resp = requests.post(
    "https://api.fpt.ai/hmi/tts/v5",
    headers={"api-key": FPT_API_KEY, "voice": "linhsan", "speed": ""},
    data="Xin chào đây là test.".encode("utf-8")
)
data = resp.json()
print("Response:", data)

url = data["async"]
print(f"\nThử download {url}")

for i in range(10):
    time.sleep(3)
    r = requests.get(url)
    print(f"Lần {i+1}: status={r.status_code}, size={len(r.content)}B, type={r.headers.get('Content-Type')}")
    if len(r.content) > 2000:
        print("=> Thành công!")
        break