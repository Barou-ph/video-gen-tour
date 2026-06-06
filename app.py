import streamlit as st
import os
import time
from dotenv import load_dotenv

from modules.voice_gen import text_to_speech, clean_script  # thêm clean_script vào import
from modules.script_gen import generate_script
from modules.voice_gen import text_to_speech
from modules.video_builder import build_video
from modules.subtitle_gen import generate_subtitles, burn_subtitles
from modules.utils import ensure_dirs, make_temp_dir, clean_temp

load_dotenv()
ensure_dirs()

# ─── Cấu hình trang ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tour Video Generator",
    page_icon="🎬",
    layout="centered"
)

st.title("🎬 Tour Video Generator")
st.caption("Tự động tạo video Shorts/Reels quảng bá tour du lịch")

# ─── Form nhập thông tin ──────────────────────────────────────────────────────
with st.form("tour_form"):
    st.subheader("Thông tin tour")
    
    col1, col2 = st.columns(2)
    with col1:
        tour_name = st.text_input("Tên tour *", placeholder="Tour Đà Lạt 3N2Đ")
    with col2:
        price = st.text_input("Giá tour *", placeholder="2.990.000đ/người")
    
    highlights = st.text_area(
        "Điểm nổi bật *",
        placeholder="Thác Datanla, Đồi Chè Cầu Đất, Làng Cù Lần, ...",
        height=80
    )
    
    description = st.text_area(
        "Mô tả ngắn",
        placeholder="Tour khởi hành mỗi thứ 6, bao gồm xe, khách sạn 3 sao, ăn sáng...",
        height=100
    )
    
    st.subheader("Ảnh/Video tour")
    uploaded_files = st.file_uploader(
        "Upload ảnh (JPG, PNG) *",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        help="Nên upload 8-15 ảnh đẹp. Ảnh sẽ tự động được crop về tỉ lệ 9:16."
    )
    
    with st.expander("⚙️ Tuỳ chỉnh nâng cao"):
        voice_speed = st.select_slider(
            "Tốc độ giọng đọc",
            options=["-20%", "-10%", "+0%", "+10%", "+20%"],
            value="+0%"
        )
        add_subtitle = st.checkbox("Thêm subtitle tự động (chậm hơn ~1 phút)", value=True)
    
    submitted = st.form_submit_button("🚀 Tạo Video", use_container_width=True, type="primary")

# ─── Xử lý tạo video ──────────────────────────────────────────────────────────
if submitted:
    # Validate input
    if not tour_name or not price or not highlights:
        st.error("Vui lòng điền đầy đủ Tên tour, Giá và Điểm nổi bật!")
        st.stop()
    
    if not uploaded_files:
        st.error("Vui lòng upload ít nhất 1 ảnh!")
        st.stop()
    
    temp_dir = make_temp_dir()
    
    try:
        # Thanh tiến trình
        progress = st.progress(0)
        status = st.status("Đang khởi động...", expanded=True)
        
        # Bước 1: Lưu ảnh upload vào temp
        with status:
            st.write("📁 Đang lưu ảnh...")
        progress.progress(10)
        
        image_paths = []
        for f in uploaded_files:
            path = os.path.join(temp_dir, f.name)
            with open(path, "wb") as fp:
                fp.write(f.read())
            image_paths.append(path)
        
        # Bước 2: Tạo script
        with status:
            st.write("✍️ AI đang viết script...")
        progress.progress(25)
        
        script = generate_script(tour_name, price, highlights, description)
        script = clean_script(script) 

        # Kiểm tra script không rỗng sau khi clean
        if not script or len(script) < 10:
            st.error("Script sau khi làm sạch bị rỗng. Thử generate lại.")
            st.stop()

        with status:
            st.write("✅ Script đã xong!")
            with st.expander("Xem script"):
                st.write(script)
        
        # Bước 3: Text to Speech
        with status:
            st.write("🎙️ Đang tạo giọng đọc tiếng Việt...")
        progress.progress(45)
        
        audio_path = os.path.join(temp_dir, "voice.mp3")

        print("=== DEBUG SCRIPT ===")
        print(repr(script))  # repr() sẽ hiện ký tự ẩn như \n \t \u200b
        print("=== END DEBUG ===")
        text_to_speech(script, audio_path, rate=voice_speed)
        


        # Bước 4: Ghép video
        with status:
            st.write("🎬 Đang ghép ảnh và âm thanh...")
        progress.progress(65)
        
        logo_path = "assets/logo.png" if os.path.exists("assets/logo.png") else None
        draft_video = os.path.join(temp_dir, "draft.mp4")
        
        build_video(image_paths, audio_path, draft_video, logo_path)
        
        # Bước 5: Subtitle (tuỳ chọn)
        final_video = os.path.join("output", f"{tour_name.replace(' ', '_')}_{int(time.time())}.mp4")
        
        if add_subtitle:
            with status:
                st.write("📝 Đang tạo subtitle (Whisper)...")
            progress.progress(80)
            
            srt_path = os.path.join(temp_dir, "subtitle.srt")
            generate_subtitles(audio_path, srt_path)
            burn_subtitles(draft_video, srt_path, final_video)
        else:
            import shutil
            shutil.copy(draft_video, final_video)
        
        progress.progress(100)
        status.update(label="✅ Video đã hoàn thành!", state="complete")
        
        # Hiển thị kết quả
        st.success("🎉 Video tạo thành công!")
        st.video(final_video)
        
        with open(final_video, "rb") as f:
            st.download_button(
                label="⬇️ Tải video MP4",
                data=f,
                file_name=os.path.basename(final_video),
                mime="video/mp4",
                use_container_width=True
            )
        
        st.info(f"File đã lưu tại: `{final_video}`")
    
    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")
        st.exception(e)  # Hiện traceback khi debug
    
    finally:
        clean_temp(temp_dir)