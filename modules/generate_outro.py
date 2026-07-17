"""
Render 1 lần duy nhất ra assets/outro.mp4 — outro động (xe chạy, cây cối,
người đi bộ, bầu trời gradient, logo fade-in) để dùng lại cho mọi video sau
này, không cần xử lý PIL lại mỗi lần build video nữa.

CÁCH DÙNG:
    python generate_outro.py

Chạy tại thư mục gốc project (nơi có thư mục assets/ chứa logo.png).
Sau khi chạy xong sẽ có file assets/outro.mp4 — video_builder.py sẽ tự
động dùng file này làm outro nếu nó tồn tại.

Có thể chỉnh các biến trong phần CONFIG bên dưới rồi chạy lại để đổi
màu sắc / thời lượng / vị trí cây, người, xe...
"""

import os
import math
import random
import subprocess
import tempfile
import shutil
from PIL import Image, ImageDraw, ImageFont

# ─── CONFIG ─────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1080, 1920
FPS = 30
DURATION = 3.6                      # giây
NUM_FRAMES = int(FPS * DURATION)

LOGO_PATH = "assets/logo.png"       # để trống/không tồn tại vẫn chạy được (bỏ qua logo)
OUTPUT_PATH = "assets/outro.mp4"

SKY_TOP = (18, 18, 42)              # xanh navy đậm
SKY_BOTTOM = (52, 28, 58)           # tím than
ROAD_Y = int(HEIGHT * 0.74)
ROAD_H = 130
ROAD_COLOR = (32, 32, 36)
LANE_COLOR = (235, 235, 235)

TAGLINE = "Theo dõi để khám phá thêm hành trình mới!"
# ────────────────────────────────────────────────────────────────────────────


def _get_font(size: int, bold: bool = True):
    candidates = [
        "assets/RobotoBold.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _ease_in_out(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _draw_sky(draw: ImageDraw.ImageDraw, stars: list, frame_idx: int):
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(SKY_TOP[0] + (SKY_BOTTOM[0] - SKY_TOP[0]) * t)
        g = int(SKY_TOP[1] + (SKY_BOTTOM[1] - SKY_TOP[1]) * t)
        b = int(SKY_TOP[2] + (SKY_BOTTOM[2] - SKY_TOP[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    for (sx, sy, base_alpha, phase) in stars:
        twinkle = 0.6 + 0.4 * math.sin(frame_idx * 0.15 + phase)
        alpha = int(base_alpha * twinkle)
        draw.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=(255, 255, 255, alpha))


def _draw_road(draw: ImageDraw.ImageDraw, frame_idx: int):
    draw.rectangle([0, ROAD_Y, WIDTH, ROAD_Y + ROAD_H], fill=ROAD_COLOR)
    # vạch kẻ đường đứt nét, chạy dần để tạo cảm giác chuyển động
    dash_w, dash_gap = 46, 30
    offset = (frame_idx * 14) % (dash_w + dash_gap)
    y_mid = ROAD_Y + ROAD_H // 2
    x = -offset
    while x < WIDTH:
        draw.rectangle([x, y_mid - 5, x + dash_w, y_mid + 5], fill=LANE_COLOR)
        x += dash_w + dash_gap


def _draw_tree(draw: ImageDraw.ImageDraw, x: int, base_y: int, scale: float, sway: float):
    trunk_w = int(10 * scale)
    trunk_h = int(34 * scale)
    draw.rectangle(
        [x - trunk_w // 2, base_y - trunk_h, x + trunk_w // 2, base_y],
        fill=(40, 26, 20)
    )
    top_y = base_y - trunk_h
    leaf_color = (24, 58, 34)
    for i, r in enumerate([int(46 * scale), int(36 * scale), int(26 * scale)]):
        cy = top_y - i * int(28 * scale)
        cx = x + int(sway * (i + 1))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=leaf_color)


def _draw_person(draw: ImageDraw.ImageDraw, x: int, base_y: int, scale: float, walk_phase: float, color):
    head_r = int(9 * scale)
    body_h = int(30 * scale)
    leg_h = int(22 * scale)
    head_cy = base_y - leg_h - body_h - head_r
    draw.ellipse([x - head_r, head_cy - head_r, x + head_r, head_cy + head_r], fill=color)

    body_top = head_cy + head_r
    body_bottom = body_top + body_h
    draw.line([(x, body_top), (x, body_bottom)], fill=color, width=int(6 * scale))

    swing = math.sin(walk_phase) * 10 * scale
    draw.line([(x, body_bottom), (x - 8 * scale + swing, base_y)], fill=color, width=int(5 * scale))
    draw.line([(x, body_bottom), (x + 8 * scale - swing, base_y)], fill=color, width=int(5 * scale))

    arm_swing = math.sin(walk_phase + math.pi) * 8 * scale
    arm_y = body_top + body_h * 0.3
    draw.line([(x, arm_y), (x - 7 * scale + arm_swing, arm_y + 14 * scale)], fill=color, width=int(4 * scale))
    draw.line([(x, arm_y), (x + 7 * scale - arm_swing, arm_y + 14 * scale)], fill=color, width=int(4 * scale))


def _draw_bus(draw: ImageDraw.ImageDraw, x: int, base_y: int, scale: float, wheel_phase: float):
    bus_w = int(190 * scale)
    bus_h = int(90 * scale)
    top = base_y - bus_h
    body_color = (206, 60, 52)      # đỏ, hợp tông thương hiệu du lịch
    window_color = (196, 226, 235)

    draw.rounded_rectangle([x, top, x + bus_w, base_y], radius=int(14 * scale), fill=body_color)

    win_pad = int(10 * scale)
    win_w = int((bus_w - win_pad * 5) / 4)
    win_h = int(bus_h * 0.4)
    win_y = top + int(bus_h * 0.18)
    for i in range(4):
        wx = x + win_pad + i * (win_w + win_pad)
        draw.rounded_rectangle([wx, win_y, wx + win_w, win_y + win_h], radius=4, fill=window_color)

    wheel_r = int(16 * scale)
    wheel_y = base_y
    for wx in [x + int(bus_w * 0.22), x + int(bus_w * 0.78)]:
        spin = wheel_phase
        draw.ellipse([wx - wheel_r, wheel_y - wheel_r, wx + wheel_r, wheel_y + wheel_r], fill=(15, 15, 15))
        # 1 chi tiết nhỏ xoay trên bánh để gợi cảm giác đang lăn
        dx = int(math.cos(spin) * wheel_r * 0.6)
        dy = int(math.sin(spin) * wheel_r * 0.6)
        draw.line([(wx, wheel_y), (wx + dx, wheel_y + dy)], fill=(90, 90, 90), width=2)


def main():
    os.makedirs("assets", exist_ok=True)
    tmp_dir = tempfile.mkdtemp()
    frames_dir = os.path.join(tmp_dir, "frames")
    os.makedirs(frames_dir)

    rnd = random.Random(7)
    stars = [
        (rnd.randint(0, WIDTH), rnd.randint(0, int(HEIGHT * 0.55)),
         rnd.randint(120, 255), rnd.uniform(0, math.pi * 2))
        for _ in range(60)
    ]

    tree_positions = [
        (60, 0.75, -0.6), (150, 0.55, 0.4), (930, 0.8, 0.6), (1020, 0.5, -0.4),
        (250, 0.4, 0.3), (830, 0.42, -0.3),
    ]

    logo_img = None
    if os.path.exists(LOGO_PATH):
        try:
            logo_img = Image.open(LOGO_PATH).convert("RGBA")
        except Exception as e:
            print(f"[OUTRO] Không đọc được logo ({e}), bỏ qua logo.")

    font_tagline = _get_font(38)

    bus_start_x = -260
    bus_end_x = WIDTH + 60

    print(f"[OUTRO] Render {NUM_FRAMES} frames...")
    for f in range(NUM_FRAMES):
        t = f / (NUM_FRAMES - 1)
        img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        _draw_sky(draw, stars, f)
        _draw_road(draw, f)

        for (tx, tscale, tsway) in tree_positions:
            sway = math.sin(f * 0.05 + tsway * 3) * 2
            _draw_tree(draw, tx, ROAD_Y, tscale, sway)

        walk_phase = f * 0.35
        _draw_person(draw, 130, ROAD_Y - 6, 1.6, walk_phase, (28, 28, 30))
        _draw_person(draw, 950, ROAD_Y - 6, 1.5, walk_phase + 1.4, (28, 28, 30))

        bus_t = _ease_in_out(min(1.0, t / 0.75))
        bus_x = int(bus_start_x + (bus_end_x - bus_start_x) * bus_t)
        _draw_bus(draw, bus_x, ROAD_Y + int(ROAD_H * 0.85), 1.5, f * 0.5)

        # Logo fade-in + scale bounce, xuất hiện từ ~35% animation
        if logo_img is not None:
            logo_t = max(0.0, min(1.0, (t - 0.30) / 0.35))
            ease = _ease_in_out(logo_t)
            alpha = int(255 * ease)
            base_w = int(WIDTH * 0.42)
            bounce = 1.0 + 0.06 * math.sin(ease * math.pi) * (1 - ease * 0.3)
            logo_w = max(1, int(base_w * (0.85 + 0.15 * ease) * bounce))
            logo_ratio = logo_img.height / max(1, logo_img.width)
            logo_h = max(1, int(logo_w * logo_ratio))
            logo_resized = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

            if alpha < 255:
                a = logo_resized.split()[-1].point(lambda p: int(p * alpha / 255))
                logo_resized.putalpha(a)

            lx = (WIDTH - logo_w) // 2
            ly = int(HEIGHT * 0.42) - logo_h // 2
            img.paste(logo_resized, (lx, ly), logo_resized)

            # Tagline fade-in sau logo
            tag_t = max(0.0, min(1.0, (t - 0.55) / 0.3))
            if tag_t > 0 and TAGLINE:
                tag_alpha = int(255 * _ease_in_out(tag_t))
                bbox = draw.textbbox((0, 0), TAGLINE, font=font_tagline)
                tw = bbox[2] - bbox[0]
                tx_pos = (WIDTH - tw) // 2
                ty_pos = ly + logo_h + 36
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                odraw.text((tx_pos, ty_pos), TAGLINE, font=font_tagline,
                           fill=(255, 255, 255, tag_alpha))
                img = Image.alpha_composite(img, overlay)

        img.convert("RGB").save(os.path.join(frames_dir, f"f_{f:04d}.jpg"), quality=95)

    silent_audio = os.path.join(tmp_dir, "silence.wav")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(DURATION), silent_audio
    ], check=True, capture_output=True)

    print("[OUTRO] Encode video...")
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frames_dir, "f_%04d.jpg"),
        "-i", silent_audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p",
        OUTPUT_PATH
    ], check=True, capture_output=True)

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"[OUTRO] Xong → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()