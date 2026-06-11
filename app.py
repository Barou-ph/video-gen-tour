import streamlit as st
import os
import time
import shutil
import unicodedata
import re
from dotenv import load_dotenv

from modules.voice_gen import text_to_speech, clean_script
from modules.script_gen import generate_script
from modules.video_builder import build_video
from modules.subtitle_gen import generate_subtitles, burn_subtitles
from modules.utils import ensure_dirs, make_temp_dir, clean_temp

load_dotenv()
ensure_dirs()


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:40]


st.set_page_config(page_title="Tour Video Generator", page_icon="🎬", layout="centered")
st.title("🎬 Tour Video Generator")
st.caption("Tự động tạo video Shorts/Reels quảng bá tour du lịch")

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
        height=80,
    )
    description = st.text_area(
        "Mô tả ngắn",
        placeholder="Tour khởi hành mỗi thứ 6, bao gồm xe, khách sạn 3 sao, ăn sáng...",
        height=100,
    )

    st.subheader("Ảnh / Video tour")
    uploaded_files = st.file_uploader(
        "Upload ảnh hoặc video *",
        type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "avi"],
        accept_multiple_files=True,
        help="Upload 5-15 ảnh JPG/PNG hoặc video clip MP4. Tự động crop về 9:16.",
    )

    with st.expander("⚙️ Tuỳ chỉnh nâng cao"):
        col3, col4 = st.columns(2)
        with col3:
            voice_speed = st.select_slider(
                "Tốc độ giọng đọc",
                options=["-20%", "-10%", "+0%", "+10%", "+20%"],
                value="+0%",
            )
        with col4:
            max_words = st.slider(
                "Giới hạn số từ script",
                min_value=80, max_value=200, value=130, step=10,
                help="Ít từ hơn = video ngắn hơn, nhịp nhanh hơn",
            )

        bg_music = st.file_uploader(
            "🎵 Nhạc nền (MP3, tuỳ chọn)",
            type=["mp3"],
            help="Nhạc nền tự động giảm xuống 15% volume",
        )
        add_subtitle = st.checkbox(
            "Burn subtitle vào video (Whisper, chậm hơn ~1 phút)", value=True
        )

    submitted = st.form_submit_button(
        "🚀 Tạo Video", use_container_width=True, type="primary"
    )

if submitted:
    if not tour_name or not price or not highlights:
        st.error("Vui lòng điền đầy đủ Tên tour, Giá và Điểm nổi bật!")
        st.stop()

    if not uploaded_files:
        st.error("Vui lòng upload ít nhất 1 ảnh!")
        st.stop()

    temp_dir = make_temp_dir()

    try:
        progress = st.progress(0)
        status = st.status("Đang khởi động...", expanded=True)

        # Bước 1: Lưu ảnh
        with status:
            st.write("📁 Đang lưu ảnh...")
        progress.progress(10)

        image_paths = []
        for f in uploaded_files:
            path = os.path.join(temp_dir, f.name)
            with open(path, "wb") as fp:
                fp.write(f.read())
            image_paths.append(path)

        # Lưu nhạc nền nếu có
        bg_music_path = None
        if bg_music:
            bg_music_path = os.path.join(temp_dir, "bg_music.mp3")
            with open(bg_music_path, "wb") as f:
                f.write(bg_music.read())

        # Bước 2: Script
        with status:
            st.write("✍️ AI đang viết script...")
        progress.progress(20)

        script = generate_script(tour_name, price, highlights, description, max_words=max_words)
        script = clean_script(script)

        if not script or len(script) < 10:
            st.error("Script rỗng. Thử lại!")
            st.stop()

        with status:
            st.write("✅ Script xong!")
            with st.expander("📄 Xem script"):
                st.write(script)

        # Bước 3: TTS
        with status:
            st.write("🎙️ FPT AI đang tạo giọng đọc...")
        progress.progress(40)

        audio_path = os.path.join(temp_dir, "voice.mp3")
        text_to_speech(script, audio_path, rate=voice_speed)

        # Bước 4: Ghép video
        with status:
            st.write("🎬 FFmpeg đang ghép ảnh + audio...")
        progress.progress(55)

        logo_path = "assets/logo.png" if os.path.exists("assets/logo.png") else None
        draft_video = os.path.join(temp_dir, "draft.mp4")

        build_video(
            media_paths=image_paths,
            audio_path=audio_path,
            output_path=draft_video,
            logo_path=logo_path,
            bg_music_path=bg_music_path,
        )

        # Bước 5: Subtitle + xuất file cuối
        final_video = os.path.join("output", f"{slugify(tour_name)}_{int(time.time())}.mp4")
        srt_final = None

        if add_subtitle:
            with status:
                st.write("📝 Whisper đang nhận dạng giọng nói...")
            progress.progress(70)

            srt_path = os.path.join(temp_dir, "subtitle.srt")
            generate_subtitles(audio_path, srt_path, script=script)

            with status:
                st.write("🔥 Đang burn subtitle vào video...")
            progress.progress(85)

            burn_subtitles(draft_video, srt_path, final_video)

            # Lưu SRT kèm để upload TikTok nếu muốn
            srt_final = final_video.replace(".mp4", ".srt")
            shutil.copy(srt_path, srt_final)
        else:
            shutil.copy(draft_video, final_video)

        progress.progress(100)
        status.update(label="✅ Hoàn thành!", state="complete")

        # Kết quả
        st.success("🎉 Video tạo thành công!")
        st.video(final_video)

        col_a, col_b = st.columns(2)
        with col_a:
            with open(final_video, "rb") as f:
                st.download_button(
                    label="⬇️ Tải video MP4",
                    data=f,
                    file_name=os.path.basename(final_video),
                    mime="video/mp4",
                    use_container_width=True,
                )
        with col_b:
            if srt_final and os.path.exists(srt_final):
                with open(srt_final, "rb") as f:
                    st.download_button(
                        label="⬇️ Tải subtitle .SRT",
                        data=f,
                        file_name=os.path.basename(srt_final),
                        mime="text/plain",
                        use_container_width=True,
                    )

        if srt_final:
            st.info("💡 TikTok: Chọn 'Captions' → Upload file .srt khi đăng video.")

        with st.expander("📁 Đường dẫn file"):
            st.code(final_video)
            if srt_final:
                st.code(srt_final)

    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")
        st.exception(e)

    finally:
        clean_temp(temp_dir)