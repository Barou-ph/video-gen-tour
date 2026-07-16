import streamlit as st
import os
import time
import shutil
import unicodedata
import re
from dotenv import load_dotenv

from modules.voice_gen import text_to_speech, clean_script, VOICES
from modules.script_gen import generate_script, parse_tour_info, generate_hook
from modules.video_builder import build_video
from modules.subtitle_gen import generate_subtitles, burn_subtitles, SUBTITLE_STYLES
from modules.utils import ensure_dirs, make_temp_dir, clean_temp, cleanup_old_outputs, cleanup_old_temps

load_dotenv()
ensure_dirs()
cleanup_old_outputs()
cleanup_old_temps()


def slugify(text: str) -> str: 
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:40]


st.set_page_config(page_title="Tour Video Generator", page_icon="🎬", layout="centered")

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Cài đặt")

    st.subheader("🔑 API Keys")
    st.caption("Nhập key — không lưu sau khi tắt app")

    openai_key = st.text_input(
        "OpenAI API Key", type="password",
        value=os.getenv("OPENAI_API_KEY", ""), placeholder="sk-...",
    )
    viettel_key = st.text_input(
        "Viettel AI Key", type="password",
        value=os.getenv("VIETTEL_API_KEY", ""),
        placeholder="Dán key Viettel AI vào đây",
    )

    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    if viettel_key:
        os.environ["VIETTEL_API_KEY"] = viettel_key

    st.divider()

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if os.getenv("OPENAI_API_KEY"):
            st.success("OpenAI ✅")
        else:
            st.error("OpenAI ❌")
    with col_s2:
        if os.getenv("VIETTEL_API_KEY"):
            st.success("Viettel AI ✅")
        else:
            st.error("Viettel AI ❌")

    st.divider()
    st.subheader("📖 Hướng dẫn")
    st.markdown("""
1. Nhập API keys bên trên
2. Dán thông tin tour vào ô chính
3. Upload ảnh/video tour
4. Bấm **Tạo Video**

💡 Để keys tự load, tạo file `.env`:
OPENAI_API_KEY=sk-...

VIETTEL_API_KEY=...
    """)

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
        col1, col2 = st.columns(2)
        with col1:
            # Tìm index của linhsan trong VOICES để set làm mặc định
            voice_keys = list(VOICES.keys())
            default_voice_idx = next(
                (i for i, k in enumerate(voice_keys) if "linhsan" in k),
                0  # fallback về index 0 nếu không tìm thấy
            )
            voice_label = st.selectbox(
                "Giọng đọc",
                options=voice_keys,
                index=default_voice_idx,
            )
        with col2:
            viettel_speed = st.select_slider(
                "Tốc độ giọng đọc",
                options=["0", "1", "2"],
                value="1",
                format_func=lambda x: {"0": "🐢 Chậm", "1": "😐 Bình thường", "2": "⚡ Nhanh"}[x],
            )

        max_words = st.slider(
            "Độ dài script (số từ)",
            min_value=80, max_value=200, value=130, step=10,
        )
        bg_music = st.file_uploader(
            "🎵 Nhạc nền (MP3, tuỳ chọn)",
            type=["mp3"],
            help="Tự động giảm xuống 15% volume",
        )
        
        st.divider()
        st.subheader("🎨 Giao diện & Hiệu ứng")
        
        col_ui1, col_ui2 = st.columns(2)
        with col_ui1:
            subtitle_style = st.selectbox(
                "Kiểu Subtitle",
                options=SUBTITLE_STYLES,
                index=0
            )
            filter_mode = st.selectbox(
                "Bộ lọc hình ảnh",
                options=[
                    "Gốc (Không lọc)",
                    "Ấm áp / Lung linh (Golden / Warm)",
                    "Huyền bí / Lạnh (Mysterious / Cool)",
                    "Cổ điển (Vintage / Retro)",
                    "Rực rỡ (Vibrant / Cinematic)"
                ],
                index=0
            )
        with col_ui2:
            transition_type = st.selectbox(
                "Hiệu ứng chuyển cảnh",
                options=["fade", "slideleft", "slideright", "slideup", "slidedown", "circlecrop", "zoomin"],
                format_func=lambda x: {
                    "fade": "Mờ dần (fade)",
                    "slideleft": "Trượt trái (slideleft)",
                    "slideright": "Trượt phải (slideright)",
                    "slideup": "Trượt lên (slideup)",
                    "slidedown": "Trượt xuống (slidedown)",
                    "circlecrop": "Vòng tròn (circlecrop)",
                    "zoomin": "Thu phóng (zoomin)"
                }[x],
                index=0
            )
            
        col_ui3, col_ui4 = st.columns(2)
        with col_ui3:
            add_subtitle = st.checkbox("Burn subtitle vào video", value=True)
        with col_ui4:
            use_chimes = st.checkbox("Tiếng cling cling chữ chạy", value=True)
            
        show_ending = st.checkbox("Thêm màn hình kết thúc (CTA Follow)", value=True)

    submitted = st.form_submit_button(
        "🚀 Tạo Video", use_container_width=True, type="primary"
    )

# ─── Xử lý ────────────────────────────────────────────────────────────────────
if submitted:
    if not tour_raw or len(tour_raw.strip()) < 10:
        st.error("Vui lòng nhập thông tin tour!")
        st.stop()
    if not uploaded_files:
        st.error("Vui lòng upload ít nhất 1 ảnh hoặc video!")
        st.stop()
    if not os.getenv("OPENAI_API_KEY"):
        st.error("Chưa nhập OpenAI API Key! Nhập vào sidebar bên trái.")
        st.stop()
    if not os.getenv("VIETTEL_API_KEY"):
        st.error("Chưa nhập Viettel AI Key! Nhập vào sidebar bên trái.")
        st.stop()

    for f in uploaded_files:
        size_mb = f.size / (1024 * 1024)
        if size_mb > 100:
            st.error(f"File '{f.name}' quá lớn ({size_mb:.0f}MB). Giới hạn 100MB/file.")
            st.stop()

    voice_id = VOICES[voice_label]
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

        # Bước 2: Script & Hook
        with status:
            st.write("✍️ AI đang đọc thông tin, viết script và tạo hook...")
        progress.progress(20)

        script = generate_script(tour_raw=tour_raw, max_words=max_words)
        script = clean_script(script)
        hook = generate_hook(tour_raw)   # Tạo hook ngắn gọn 1 dòng

        if not script or len(script) < 10:
            st.error("Script rỗng. Thử lại!")
            st.stop()

        with status:
            st.write("✅ Script & Hook xong!")
            with st.expander("📄 Xem chi tiết từ AI"):
                st.markdown(f"**Hook tiêu đề:** {hook}")
                st.markdown(f"**Bài đọc:**\n{script}")

        # Bước 3: TTS (Chuyển văn bản thành giọng đọc)
        with status:
            st.write(f"🎙️ VIETTEL AI đang tạo giọng ({voice_label})...")
        progress.progress(40)

        audio_path = os.path.join(temp_dir, "voice.mp3")
        text_to_speech(script, audio_path, voice=voice_id, speed=viettel_speed)

        # Bước 4: Tạo subtitle trước (nếu cần dùng cho hiệu ứng cling cling hoặc burn sub)
        srt_path = None
        if add_subtitle or use_chimes:
            with status:
                st.write("📝 Đang tạo subtitle từ script...")
            progress.progress(50)
            srt_path = os.path.join(temp_dir, "subtitle.srt")
            generate_subtitles(audio_path, srt_path, script=script)

        # Bước 5: Ghép video + chuyển cảnh + chèn hook + chèn tiếng chimes
        with status:
            st.write("🎬 Đang ghép video + chuyển cảnh + chèn hook...")
        progress.progress(65)

        logo_path = "assets/logo.png" if os.path.exists("assets/logo.png") else None
        draft_video = os.path.join(temp_dir, "draft.mp4")

        # Sử dụng biến `hook` để làm overlay text chạy trên video
        build_video(
            media_paths=media_paths,
            audio_path=audio_path,
            output_path=draft_video,
            logo_path=logo_path,
            bg_music_path=bg_music_path,
            script=hook,
            transition_type=transition_type,
            filter_mode=filter_mode,
            show_ending=show_ending,
            use_chimes=use_chimes,
            srt_path=srt_path,
        )

        # Bước 6: Burn Subtitle
        final_video = os.path.join(
            "output", f"{slugify(tour_raw[:30])}_{int(time.time())}.mp4"
        )
        srt_final = None

        if add_subtitle:
            with status:
                st.write("🔥 Đang burn subtitle vào video...")
            progress.progress(85)

            burn_subtitles(
                draft_video,
                srt_path,
                final_video,
                subtitle_style=subtitle_style,
            )
            srt_final = final_video.replace(".mp4", ".srt")
            shutil.copy(srt_path, srt_final)
        else:
            shutil.copy(draft_video, final_video)

        progress.progress(100)
        status.update(label="✅ Hoàn thành!", state="complete")

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