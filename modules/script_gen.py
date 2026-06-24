import re
import json
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Thông tin công ty — chỉnh tại đây nếu cần ────────────────────────────────
COMPANY_NAME    = "Đại lý Du lịch Khanh"
COMPANY_SLOGAN  = "chi phí minh bạch, không phát sinh phụ phí, dịch vụ tận tâm từ đầu đến cuối"
COMPANY_CTA     = f"Hãy để {COMPANY_NAME} đồng hành cùng bạn trên mọi hành trình!"


def generate_script(tour_raw: str, max_words: int = 130) -> str:
    prompt = f"""Bạn là chuyên gia marketing du lịch Việt Nam.

Dưới đây là thông tin thô về một tour du lịch:
---
{tour_raw}
---

THÔNG TIN CÔNG TY (bắt buộc nhắc đến ở CTA cuối):
- Tên: {COMPANY_NAME}
- Cam kết: {COMPANY_SLOGAN}

Nhiệm vụ: Viết script video Shorts/Reels 30-45 giây từ thông tin trên.

CẤU TRÚC BẮT BUỘC:
1. Hook 2-3 giây: 1 câu ngắn gây sốc/tò mò, liên quan trực tiếp đến tour.
   Ví dụ tốt: "Chỉ 3 triệu cho 3 ngày thiên đường!" hoặc "Đà Lạt đang gọi tên bạn!"
   KHÔNG được bắt đầu bằng "Hôm nay mình", "Xin chào", "Bạn có muốn"

2. Nội dung 25-35 giây: 3-4 điểm nổi bật ngắn gọn, hình ảnh rõ ràng

3. CTA cuối: nhắc tên "{COMPANY_NAME}" + 1 cam kết ngắn + gợi ý liên hệ.
   Ví dụ: "Muốn một chuyến đi {COMPANY_SLOGAN}? Hãy để {COMPANY_NAME} đồng hành cùng bạn!"
   hoặc: "Liên hệ {COMPANY_NAME} để được tư vấn miễn phí và giá tốt nhất!"

QUY TẮC:
- Tiếng Việt tự nhiên, như người nói chuyện thật
- KHÔNG dùng markdown, emoji, ký tự đặc biệt
- Mỗi câu ngắn, dễ đọc to
- Tổng KHÔNG QUÁ {max_words} từ
- Nhắc đến giá nếu có trong thông tin
- Dùng dấu chấm than (!) cho câu nhấn mạnh
- Dùng dấu chấm lửng (...) cho chỗ ngừng tự nhiên
- Câu hook PHẢI có dấu chấm than
- Xen kẽ câu ngắn và câu dài để tạo nhịp điệu
- KHÔNG dùng viết tắt: "3 ngày 2 đêm" thay vì "3N2Đ", "thứ Sáu" thay vì "T6"
- Số tiền viết bằng chữ: "hai triệu chín" thay vì "2.9tr"

CHỈ trả về script, không giải thích, không tiêu đề."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_tokens=600,
    )

    return response.choices[0].message.content.strip()


def parse_tour_info(tour_raw: str) -> dict:
    """Parse thông tin tour từ raw text."""
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
        return json.loads(text)
    except Exception:
        return {"tour_name": "", "price": "", "highlights": tour_raw, "description": ""}

def generate_hook(tour_raw: str) -> str:
    """Sinh 1 câu hook ngắn gọn tối đa 8 từ cho overlay video."""
    prompt = f"""Từ thông tin tour sau, viết đúng 1 câu hook cực ngắn (tối đa 8 từ) 
bằng tiếng Việt để hiển thị 3 giây đầu video TikTok.

THÔNG TIN:
{tour_raw}

YÊU CẦU:
- Tối đa 8 từ, không dấu chấm cuối
- Gây tò mò hoặc cảm xúc mạnh ngay lập tức
- Không dùng emoji, ký tự đặc biệt
- Ví dụ tốt: "Đà Lạt đang gọi tên bạn" / "3 ngày 2 đêm chỉ từ 2 triệu 9"

CHỈ trả về câu hook, không giải thích."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=30,
    )
    return response.choices[0].message.content.strip().strip('."\'')