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
    """Sinh 1 câu hook cực kỳ thu hút, tò mò, không chứa số thô, mượt mà (tối đa 8-10 từ) theo style TikTok Travel Vlog."""
    prompt = f"""Bạn là một TikTok Creator triệu view chuyên sáng tạo vlog du lịch phong cách cinematic/đời sống.
Hãy viết đúng 1 câu hook (tiêu đề hiển thị 3 giây đầu) cực kỳ cuốn hút, mượt mà và tự nhiên về chuyến du lịch dưới đây.

THÔNG TIN TOUR:
{tour_raw}

YÊU CẦU CỦA CÂU HOOK:
1. Độ dài: Tối đa 8-10 từ, viết gọn trên 1 dòng.
2. Tuyệt đối KHÔNG DÙNG SỐ THÔ (như 3, 2, 2.9, 2tr9, 3N2Đ, 2.490.000, 2 triệu rưỡi, chỉ 2 triệu 4).
3. Văn phong: Sử dụng phong cách tự sự (POV), câu hỏi gợi mở hoặc gợi cảm xúc mượt mà của vlog du lịch xịn.
   - Ví dụ tốt: 
     + "POV: Bạn quyết định đi trốn nóng Đà Lạt"
     + "Đà Lạt mùa này đẹp bình yên đến lạ"
     + "Góc bình yên nhất bạn phải ghé ở Đà Lạt"
     + "Chuyến trốn nóng lý tưởng nhất mùa hè này"
     + "Lý do bạn phải xách balo đi Đà Lạt ngay"
     + "Đà Lạt đang gọi tên bạn"
4. Định dạng: Không dùng emoji, không ký tự đặc biệt, không viết dấu chấm ở cuối câu.

CHỈ trả về duy nhất 1 câu hook tiếng Việt, không giải thích gì thêm."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=40,
    )
    return response.choices[0].message.content.strip().strip('."\'')