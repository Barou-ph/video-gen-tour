# diag.py
import requests, time, os
from dotenv import load_dotenv
load_dotenv()

KEY = os.getenv("FPT_API_KEY")

resp = requests.post(
    "https://api.fpt.ai/hmi/tts/v5",
    headers={"api-key": KEY, "voice": "lannhi", "speed": "1"},
    data="Xin chào đây là test.".encode("utf-8")
)
print("Status:", resp.status_code)
data = resp.json()
print("Response:", data)

if data.get("error") == 0:
    url = data["async"]
    print(f"\nDownload thử: {url}")
    for i in range(5):
        time.sleep(3)
        r = requests.get(url)
        print(f"Lần {i+1}: status={r.status_code} size={len(r.content)}B")
        if len(r.content) > 1000:
            print("=> OK!")
            break