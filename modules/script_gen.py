# modules/script_gen.py — dùng OpenAI thay Gemini
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_script(tour_name: str, price: str, highlights: str, description: str) -> str:
    """Dùng GPT-4o-mini tạo script video ngắn tiếng Việt."""

    prompt = f"""Bạn là chuyên gia marketing du lịch. Hãy viết script cho video Shorts/Reels 45 giây.

THÔNG TIN TOUR:
- Tên tour: {tour_name}
- Giá: {price}
- Điểm nổi bật: {highlights}
- Mô tả: {description}

YÊU CẦU SCRIPT:
1. Hook 3 giây đầu: câu hỏi hoặc tuyên bố gây tò mò, KHÔNG bắt đầu bằng "Bạn có muốn"
2. Nội dung chính 35 giây: 3 điểm nổi bật ngắn gọn, hấp dẫn
3. CTA 7 giây cuối: kêu gọi liên hệ/đặt tour ngay

QUY TẮC:
- Viết thuần tiếng Việt, giọng tự nhiên như đang nói chuyện
- Không dùng ký tự đặc biệt, emoji trong script
- Mỗi câu ngắn, dễ đọc to
- Tổng khoảng 120-150 từ
- Kết thúc bằng: "Liên hệ ngay hôm nay để nhận ưu đãi đặc biệt!"

CHỈ trả về nội dung script, không có tiêu đề hay giải thích."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # Rẻ nhất, đủ dùng cho task này (~$0.001/script)
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=500,
    )

    return response.choices[0].message.content.strip()