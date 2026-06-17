import re
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_script(tour_raw: str, max_words: int = 130) -> str:
    prompt = f"""Bạn là chuyên gia marketing du lịch Việt Nam.

Dưới đây là thông tin thô về một tour du lịch:
---
{tour_raw}
---

Nhiệm vụ: Viết script video Shorts/Reels 30-45 giây từ thông tin trên.

CẤU TRÚC BẮT BUỘC:
1. Hook 2-3 giây: 1 câu ngắn gây sốc/tò mò, liên quan trực tiếp đến tour. Ví dụ: "Chỉ 3 triệu cho 3 ngày thiên đường!" hoặc "Đà Lạt đang gọi tên bạn!"
2. Nội dung 25-35 giây: 3-4 điểm nổi bật ngắn gọn, hình ảnh rõ ràng
3. CTA cuối: "Liên hệ ngay để nhận ưu đãi đặc biệt!"

QUY TẮC:
- Tiếng Việt tự nhiên, như người nói chuyện
- KHÔNG dùng markdown, emoji, ký tự đặc biệt
- Mỗi câu ngắn, dễ đọc to
- Tổng KHÔNG QUÁ {max_words} từ
- Nhắc đến giá nếu có trong thông tin
- Dùng dấu chấm than (!) cho câu nhấn mạnh
- Dùng dấu chấm lửng (...) cho chỗ ngừng tự nhiên
- Câu hook PHẢI có dấu chấm than
- Xen kẽ câu ngắn và câu dài để tạo nhịp điệu
- KHÔNG dùng viết tắt: viết "3 ngày 2 đêm" thay vì "3N2Đ", "2 triệu 9" thay vì "2.9tr", "thứ Sáu" thay vì "T6"
- Số tiền viết bằng chữ: "hai triệu chín trăm nghìn đồng" hoặc "chỉ 2 triệu 9"

CHỈ trả về script, không giải thích."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_tokens=600,
    )

    return response.choices[0].message.content.strip()


def parse_tour_info(tour_raw: str) -> dict:
    """Parse thông tin tour từ raw text — dùng nếu cần extract riêng."""
    prompt = f"""Extract thông tin từ text sau thành JSON:
{tour_raw}

Trả về JSON với keys: tour_name, price, highlights, description.
Nếu không tìm thấy field nào thì để chuỗi rỗng.
CHỈ trả về JSON, không markdown."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
    )

    try:
        text = response.choices[0].message.content.strip()
        text = re.sub(r"```json|```", "", text).strip()
        import json
        return json.loads(text)
    except Exception:
        return {"tour_name": "", "price": "", "highlights": tour_raw, "description": ""}