import streamlit as st
import os
import time
import shutil
import unicodedata
import re
from dotenv import load_dotenv

from modules.voice_gen import text_to_speech, clean_script
from modules.script_gen import generate_script, parse_tour_info
from modules.video_builder import build_video
from modules.subtitle_gen import generate_subtitles, burn_subtitles
from modules.utils import ensure_dirs, make_temp_dir, clean_temp, cleanup_old_outputs, cleanup_old_temps

load_dotenv()
ensure_dirs()
cleanup_old_outputs()   # Xóa video cũ hơn 7 ngày
cleanup_old_temps()     # Xóa temp cũ hơn 2 tiếng


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:40]


st.set_page_config(page_title="Tour Video Generator", page_icon="🎬", layout="centered")

# ─── Sidebar API Keys ─────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("⚙️ Cài đặt API")
    st.caption("Nhập key của bạn — không lưu lại sau khi tắt app")

    openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=os.getenv("OPENAI_API_KEY", ""),
        placeholder="sk-...",
    )
    fpt_key = st.text_input(
        "FPT AI Key",
        type="password",
        value=os.getenv("FPT_API_KEY", ""),
        placeholder="FPT API key",
    )

    # Apply key ngay khi nhập — trước khi form submit
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    if fpt_key:
        os.environ["FPT_API_KEY"] = fpt_key

    # Hiển thị trạng thái key
    st.divider()
    if os.getenv("OPENAI_API_KEY"):
        st.success("✅ OpenAI key đã set")
    else:
        st.error("❌ Chưa có OpenAI key")

    if os.getenv("FPT_API_KEY"):
        st.success("✅ FPT AI key đã set")
    else:
        st.error("❌ Chưa có FPT key")

    st.divider()
    st.caption("💡 Để key tự động load, tạo file `.env` với:\n```\nOPENAI_API_KEY=sk-...\nFPT_API_KEY=...\n```")

# ─── Main UI ──────────────────────────────────────────────────────────────────
st.title("🎬 Tour Video Generator")
st.caption("Tự động tạo video Shorts/Reels quảng bá tour du lịch")

with st.form("tour_form"):
    st.subheader("📋 Thông tin tour")
    tour_raw = st.text_area(
        "Dán thông tin tour vào đây *",
        placeholder="""Ví dụ — dán thoải mái, AI tự lọc:

Tour Đà Lạt 3N2Đ
Giá: 2.990.000đ/người
Khởi hành: Thứ 6 hàng tuần
Điểm nổi bật: Thác Datanla, Đồi Chè Cầu Đất, Làng Cù Lần, Chợ Đêm
Bao gồm: Xe limousine, khách sạn 3 sao, ăn sáng, HDV""",
        height=200,
    )

    st.subheader("🎬 Ảnh / Video tour")
    uploaded_files = st.file_uploader(
        "Upload ảnh hoặc video *",
        type=["jpg", "jpeg", "png", "webp", "mp4", "mov"],
        accept_multiple_files=True,
        help="Upload 5-15 file. Ảnh JPG/PNG hoặc video MP4/MOV đều được.",
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
                "Độ dài script (số từ)",
                min_value=80, max_value=200, value=130, step=10,
            )
        bg_music = st.file_uploader(
            "🎵 Nhạc nền (MP3, tuỳ chọn)",
            type=["mp3"],
            help="Tự động giảm xuống 15% volume",
        )
        add_subtitle = st.checkbox("Burn subtitle vào video", value=True)

    submitted = st.form_submit_button(
        "🚀 Tạo Video", use_container_width=True, type="primary"
    )

# ─── Xử lý ────────────────────────────────────────────────────────────────────
if submitted:
    # Validate
    if not tour_raw or len(tour_raw.strip()) < 10:
        st.error("Vui lòng nhập thông tin tour!")
        st.stop()
    if not uploaded_files:
        st.error("Vui lòng upload ít nhất 1 ảnh hoặc video!")
        st.stop()
    if not os.getenv("OPENAI_API_KEY"):
        st.error("Chưa nhập OpenAI API Key! Nhập vào sidebar bên trái.")
        st.stop()
    if not os.getenv("FPT_API_KEY"):
        st.error("Chưa nhập FPT AI Key! Nhập vào sidebar bên trái.")
        st.stop()

    # Kiểm tra file size
    for f in uploaded_files:
        size_mb = f.size / (1024 * 1024)
        if size_mb > 100:
            st.error(f"File '{f.name}' quá lớn ({size_mb:.0f}MB). Giới hạn 100MB/file.")
            st.stop()

    temp_dir = make_temp_dir()

    try:
        progress = st.progress(0)
        status = st.status("Đang khởi động...", expanded=True)

        # Bước 1: Lưu media
        with status:
            st.write("📁 Đang lưu media...")
        progress.progress(10)

        media_paths = []
        for f in uploaded_files:
            path = os.path.join(temp_dir, f.name)
            with open(path, "wb") as fp:
                fp.write(f.read())
            media_paths.append(path)

        bg_music_path = None
        if bg_music:
            bg_music_path = os.path.join(temp_dir, "bg_music.mp3")
            with open(bg_music_path, "wb") as f:
                f.write(bg_music.read())

        # Bước 2: AI parse + viết script
        with status:
            st.write("✍️ AI đang đọc thông tin và viết script...")
        progress.progress(20)

        script = generate_script(tour_raw=tour_raw, max_words=max_words)
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
            st.write("🎬 Đang ghép video + chuyển cảnh + hook...")
        progress.progress(55)

        logo_path   = "assets/logo.png" if os.path.exists("assets/logo.png") else None
        draft_video = os.path.join(temp_dir, "draft.mp4")

        build_video(
            media_paths=media_paths,
            audio_path=audio_path,
            output_path=draft_video,
            logo_path=logo_path,
            bg_music_path=bg_music_path,
            script=script,
        )

        # Bước 5: Subtitle
        final_video = os.path.join(
            "output", f"{slugify(tour_raw[:30])}_{int(time.time())}.mp4"
        )
        srt_final = None

        if add_subtitle:
            with status:
                st.write("📝 Đang tạo subtitle từ script...")
            progress.progress(75)

            srt_path = os.path.join(temp_dir, "subtitle.srt")
            generate_subtitles(audio_path, srt_path, script=script)

            with status:
                st.write("🔥 Đang burn subtitle vào video...")
            progress.progress(88)

            burn_subtitles(draft_video, srt_path, final_video)
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

    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")
        st.exception(e)

    finally:
        clean_temp(temp_dir)