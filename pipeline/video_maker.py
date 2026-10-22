import os
import textwrap
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import FFMPEG_BIN, LOGO_PATH, OUTPUT_DIR

# Color palette matching VCF brand
BG_COLOR = (22, 35, 48)          # Deep Slate Navy #162330
ORANGE_BAR = (234, 100, 42)      # Warm Orange #EA642A
TITLE_COLOR = (255, 255, 255)    # Crisp White
PREACHER_COLOR = (247, 148, 104) # Warm Amber Gold #F79468
DATE_COLOR = (148, 174, 197)     # Soft Steel Blue #94AEC5

def get_font(size, bold=False, sans=False):
    # Windows fonts
    win_fonts = r"C:\Windows\Fonts"
    if os.path.exists(win_fonts):
        if sans:
            candidates = [
                "segoeuib.ttf" if bold else "segoeui.ttf",
                "arialbd.ttf" if bold else "arial.ttf",
                "calibrib.ttf" if bold else "calibri.ttf"
            ]
        else:
            candidates = [
                "georgiab.ttf" if bold else "georgia.ttf",
                "timesbd.ttf" if bold else "times.ttf",
                "arialbd.ttf" if bold else "arial.ttf"
            ]
        for cand in candidates:
            p = os.path.join(win_fonts, cand)
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass

    # Linux fonts (in cloud container)
    if sans:
        linux_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    else:
        linux_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for p in linux_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass

    return ImageFont.load_default()

BACKDROPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "backdrops")

THEME_BACKDROPS = {
    "WORD_TEACHING": "bible_sunlight.jpg",
    "BIBLE_SUNLIGHT": "bible_sunlight.jpg",
    "CROSS_GRACE": "cross_grace.jpg",
    "FAITH_MOUNTAIN": "faith_mountain.jpg",
    "PEACE_SHEPHERD": "peace_shepherd.jpg",
    "STORM_DELIVERANCE": "storm_deliverance.jpg",
    "HOLY_SPIRIT": "holy_spirit.jpg",
    "LOCAL_FELLOWSHIP": "local_williamsburg.jpg",
    "CLASSIC_SLATE": None
}

def resolve_backdrop_image(visual_theme=None, custom_bg_path=None):
    """Resolves background image path from custom upload, theme name, or fallback"""
    if custom_bg_path and os.path.exists(custom_bg_path):
        return custom_bg_path

    theme_key = (visual_theme or "WORD_TEACHING").strip().upper()
    if theme_key == "CLASSIC_SLATE":
        return None

    filename = THEME_BACKDROPS.get(theme_key, "bible_sunlight.jpg")
    if filename:
        p = os.path.join(BACKDROPS_DIR, filename)
        if os.path.exists(p):
            return p

    for fb in ["bible_sunlight.jpg", "cross_grace.jpg", "faith_mountain.jpg", "peace_shepherd.jpg"]:
        p = os.path.join(BACKDROPS_DIR, fb)
        if os.path.exists(p):
            return p

    return None

def render_sermon_backdrop(title, preacher, date_str, out_image_path, scripture="", visual_theme="WORD_TEACHING", custom_bg_path=None, subtitle=""):
    """
    Generates an ultra-crisp 1920x1080 Full HD sermon thumbnail and video backdrop.
    Uses 2x supersampled (3840x2160) typography rendering with multi-layer Gaussian drop shadows
    and warm metallic gold highlights for studio-quality visual clarity.
    """
    w, h = 1920, 1080
    bg_file = resolve_backdrop_image(visual_theme, custom_bg_path)

    if bg_file and os.path.exists(bg_file):
        try:
            img = Image.open(bg_file).convert("RGB")
            if img.size != (w, h):
                img = img.resize((w, h), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Notice: Failed to load background {bg_file}: {e}. Using classic solid navy.")
            img = Image.new("RGB", (w, h), BG_COLOR)
    else:
        img = Image.new("RGB", (w, h), BG_COLOR)

    # 1. Cinematic Top & Bottom Gradient Scrim for 100% Text Readability
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    for y in range(h):
        alpha = 0
        if y < 540:
            alpha = int(165 * (1.0 - (y / 540.0) ** 1.25))
        elif y > 720:
            alpha = int(185 * (((y - 720) / 360.0) ** 1.15))
        if alpha > 0:
            o_draw.line([(0, y), (w, y)], fill=(10, 14, 22, alpha))

    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)

    # 2. Supersampled 2x (3840x2160) Typography Layer for Razor-Sharp Edges & Smooth Gaussian Glow
    scale = 2
    sw, sh = w * scale, h * scale
    shadow_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    text_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    t_draw = ImageDraw.Draw(text_layer)

    clean_title = (title or "Biblical Message").strip()
    words = clean_title.split()
    if len(words) <= 3 and len(clean_title) <= 22:
        lines = [" ".join(words)]
    elif len(words) <= 6 and len(clean_title) <= 42:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = textwrap.wrap(clean_title.upper(), width=24)
        if len(lines) > 3:
            lines = textwrap.wrap(clean_title.upper(), width=30)[:3]

    base_title_size = 90 if len(lines) == 1 else (82 if len(lines) == 2 else 68)
    title_size = base_title_size * scale
    title_font = get_font(title_size, bold=True, sans=False)
    sub_font = get_font(40 * scale, bold=False, sans=False)
    speaker_font = get_font(40 * scale, bold=True, sans=True)

    # Upper Title Block
    start_y = (115 if len(lines) > 2 else (140 if len(lines) == 2 else 175)) * scale
    curr_y = start_y

    for idx, line in enumerate(lines):
        line_upper = line.upper()
        bbox = t_draw.textbbox((0, 0), line_upper, font=title_font)
        lw = bbox[2] - bbox[0]
        # Shrink font slightly if a single line is wider than 90% of screen
        cur_font = title_font
        if lw > int(sw * 0.90):
            shrunk_size = int(title_size * (sw * 0.88) / lw)
            cur_font = get_font(shrunk_size, bold=True, sans=False)
            bbox = t_draw.textbbox((0, 0), line_upper, font=cur_font)
            lw = bbox[2] - bbox[0]

        lx = (sw - lw) // 2

        if (idx == len(lines) - 1 and len(lines) > 1):
            txt_color = (248, 204, 108, 255) # Warm Radiant Gold
        else:
            txt_color = (255, 252, 246, 255) # Crisp Ivory White

        # Draw soft ambient shadow + crisp offset shadow onto shadow_layer
        s_draw.text((lx, curr_y + 8 * scale), line_upper, fill=(0, 0, 0, 235), font=cur_font)
        s_draw.text((lx + 4 * scale, curr_y + 6 * scale), line_upper, fill=(0, 0, 0, 210), font=cur_font)
        # Draw crisp foreground text onto text_layer
        t_draw.text((lx, curr_y), line_upper, fill=txt_color, font=cur_font)
        curr_y += int(title_size * 1.18)

    # Optional Subtitle
    clean_subtitle = (subtitle or "").strip()
    if clean_subtitle:
        s_bbox = t_draw.textbbox((0, 0), clean_subtitle, font=sub_font)
        sub_w = s_bbox[2] - s_bbox[0]
        sx = (sw - sub_w) // 2
        s_draw.text((sx, curr_y + 5 * scale), clean_subtitle, fill=(0, 0, 0, 220), font=sub_font)
        t_draw.text((sx, curr_y), clean_subtitle, fill=(238, 232, 222, 255), font=sub_font)

    # Lower Third: Speaker Name
    speaker_text = f"Speaker: {preacher}" if preacher else "Victory Christian Fellowship"
    p_bbox = t_draw.textbbox((0, 0), speaker_text, font=speaker_font)
    pw = p_bbox[2] - p_bbox[0]
    px = (sw - pw) // 2
    py = 825 * scale
    s_draw.text((px, py + 5 * scale), speaker_text, fill=(0, 0, 0, 230), font=speaker_font)
    t_draw.text((px, py), speaker_text, fill=(248, 248, 252, 255), font=speaker_font)

    # Golden Accent Divider Line under Speaker
    line_w = min(pw + 140 * scale, 480 * scale)
    line_y = py + 58 * scale
    t_draw.line([((sw - line_w) // 2, line_y), ((sw + line_w) // 2, line_y)], fill=(242, 182, 80, 235), width=3 * scale)
    # Diamond center ornament on divider line
    cx = sw // 2
    d_rad = 6 * scale
    t_draw.polygon([(cx, line_y - d_rad), (cx + d_rad, line_y), (cx, line_y + d_rad), (cx - d_rad, line_y)], fill=(248, 204, 108, 255))

    # Scripture & Date Line (Auto-scales if multiple scriptures are listed)
    ref_parts = []
    if scripture and scripture.strip():
        ref_parts.append(scripture.strip().upper())
    if date_str and date_str.strip():
        ref_parts.append(date_str.strip().upper())
    ref_text = "   •   ".join(ref_parts) if ref_parts else "VICTORY CHRISTIAN FELLOWSHIP"

    ref_font_size = 30 * scale
    ref_font = get_font(ref_font_size, bold=True, sans=True)
    r_bbox = t_draw.textbbox((0, 0), ref_text, font=ref_font)
    rw = r_bbox[2] - r_bbox[0]
    if rw > int(sw * 0.90):
        ref_font_size = max(18 * scale, int(ref_font_size * (sw * 0.88) / rw))
        ref_font = get_font(ref_font_size, bold=True, sans=True)
        r_bbox = t_draw.textbbox((0, 0), ref_text, font=ref_font)
        rw = r_bbox[2] - r_bbox[0]

    rx = (sw - rw) // 2
    ry = line_y + 22 * scale
    s_draw.text((rx, ry + 4 * scale), ref_text, fill=(0, 0, 0, 230), font=ref_font)
    t_draw.text((rx, ry), ref_text, fill=(228, 234, 242, 255), font=ref_font)

    # Blur shadow layer for smooth studio drop-shadow, composite with crisp text, and downsample 4K -> 1080p
    blurred_shadow = shadow_layer.filter(ImageFilter.GaussianBlur(radius=9 * scale))
    combined_4k = Image.alpha_composite(blurred_shadow, text_layer)
    combined_1080p = combined_4k.resize((w, h), Image.Resampling.LANCZOS)

    final_img = Image.alpha_composite(img, combined_1080p).convert("RGB")

    dir_name = os.path.dirname(out_image_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    # Save with quality=96 and 4:4:4 chroma (subsampling=0) so golden text & fine details are 100% razor sharp
    final_img.save(out_image_path, "JPEG", quality=96, subsampling=0)
    return out_image_path

def get_audio_duration_seconds(audio_path):
    """Accurately extracts audio length in seconds using mutagen, ffprobe, or ffmpeg"""
    from pipeline.audio_analyzer import get_audio_duration_seconds as _get_dur
    val = _get_dur(audio_path)
    return (val + 1) if val else None

def build_video_from_audio(audio_path, image_path, output_mp4_path, progress_callback=None):
    """Muxes static graphic image and raw audio file into 1080p MP4 video at lightning speed"""
    dur = get_audio_duration_seconds(audio_path)
    print(f"Detected audio duration: {dur}s")

    ext = os.path.splitext(audio_path)[1].lower()
    can_copy_audio = ext in ['.mp3', '.m4a', '.aac']

    cmd = [
        FFMPEG_BIN, "-y",
        "-loop", "1",
        "-framerate", "1",
        "-i", image_path,
        "-i", audio_path,
    ]

    if dur:
        cmd.extend(["-t", str(dur)])

    cmd.extend([
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-preset", "ultrafast",
        "-crf", "24",
        "-r", "1",
        "-g", "60",
        "-pix_fmt", "yuv420p"
    ])

    if can_copy_audio:
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    if not dur:
        cmd.append("-shortest")

    cmd.append(output_mp4_path)

    print(f"Running FFmpeg: {' '.join(cmd)}")
    log_path = os.path.join(os.path.dirname(output_mp4_path), "ffmpeg.log")
    with open(log_path, "w") as log_f:
        res = subprocess.run(cmd, stdout=log_f, stderr=subprocess.STDOUT)

    if res.returncode != 0:
        err_tail = ""
        try:
            with open(log_path, "r") as log_f:
                err_tail = log_f.read()[-500:]
        except Exception:
            pass
        print(f"FFmpeg error ({res.returncode}): {err_tail}")
        return False
    return os.path.exists(output_mp4_path) and os.path.getsize(output_mp4_path) > 1000
