import os
import textwrap
import subprocess
from PIL import Image, ImageDraw, ImageFont
from config import FFMPEG_BIN, LOGO_PATH, OUTPUT_DIR

# Color palette matching VCF brand
BG_COLOR = (22, 35, 48)          # Deep Slate Navy #162330
ORANGE_BAR = (234, 100, 42)      # Warm Orange #EA642A
TITLE_COLOR = (255, 255, 255)    # Crisp White
PREACHER_COLOR = (247, 148, 104) # Warm Amber Gold #F79468
DATE_COLOR = (148, 174, 197)     # Soft Steel Blue #94AEC5

def get_font(size, bold=False):
    # Windows fonts
    win_fonts = r"C:\Windows\Fonts"
    if os.path.exists(win_fonts):
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
                except:
                    pass

    # Linux fonts (in cloud container)
    linux_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
    ]
    for p in linux_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
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
    "LOCAL_FELLOWSHIP": "holy_spirit.jpg",
    "CLASSIC_SLATE": None
}

def resolve_backdrop_image(visual_theme=None, custom_bg_path=None):
    """Resolves background image path from custom upload, theme name, or fallback"""
    if custom_bg_path and os.path.exists(custom_bg_path):
        return custom_bg_path

    theme_key = (visual_theme or "WORD_TEACHING").strip().upper()
    filename = THEME_BACKDROPS.get(theme_key, "bible_sunlight.jpg")
    if filename:
        p = os.path.join(BACKDROPS_DIR, filename)
        if os.path.exists(p):
            return p

    # Fallback to curated cinematic backdrops (never casual phone photos)
    for fb in ["bible_sunlight.jpg", "cross_grace.jpg", "faith_mountain.jpg"]:
        p = os.path.join(BACKDROPS_DIR, fb)
        if os.path.exists(p):
            return p
        p_static = os.path.join(os.path.dirname(BACKDROPS_DIR), fb)
        if os.path.exists(p_static):
            return p_static

    return None

def render_sermon_backdrop(title, preacher, date_str, out_image_path, scripture="", visual_theme="WORD_TEACHING", custom_bg_path=None, subtitle=""):
    """Generates rich 1920x1080 cinematic card for video playback and YouTube thumbnail in the exact style of modern high-impact sermon graphics"""
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

    # 1. Subtle dark vignette / scrim so top and bottom text pop with 100% contrast
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    for y in range(h):
        alpha = 0
        if y < 520:
            # Darker at top for title
            alpha = int(145 * (1.0 - (y / 520.0) ** 1.3))
        elif y > 750:
            # Darker at bottom for speaker and scripture banner
            alpha = int(165 * (((y - 750) / 330.0) ** 1.1))
        if alpha > 0:
            o_draw.line([(0, y), (w, y)], fill=(12, 16, 24, alpha))
            
    img.paste(overlay, (0, 0), mask=overlay)
    draw = ImageDraw.Draw(img)

    # Font definitions
    clean_title = (title or "Sunday Morning Message").strip()
    words = clean_title.split()
    if len(words) <= 3:
        lines = [" ".join(words)]
    elif len(words) <= 6:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = textwrap.wrap(clean_title.upper(), width=28)

    title_size = 84 if len(lines) <= 2 else 68
    title_font = get_font(title_size, bold=True)
    sub_font = get_font(42, bold=False)
    sans_font = get_font(36, bold=False)
    sans_bold_font = get_font(28, bold=True)

    # 2. Render Title Lines in Upper Half
    start_y = 120 if len(lines) > 2 else 150
    curr_y = start_y

    for idx, line in enumerate(lines):
        line_upper = line.upper()
        bbox = draw.textbbox((0, 0), line_upper, font=title_font)
        lw = bbox[2] - bbox[0]
        lx = (w - lw) // 2

        # Color: Top line(s) ivory white, bottom line warm radiant gold!
        if idx == len(lines) - 1 and len(lines) > 1:
            txt_color = (245, 197, 100) # Radiant warm gold
        else:
            txt_color = (252, 248, 242) # Pure ivory white

        # Soft drop shadow for crisp 3D embossed effect
        for offset in [(0, 3), (2, 2), (-2, 2), (0, 4)]:
            draw.text((lx + offset[0], curr_y + offset[1]), line_upper, fill=(0, 0, 0, 220), font=title_font)
        draw.text((lx, curr_y), line_upper, fill=txt_color, font=title_font)
        curr_y += title_size + 16

    # 3. Subtitle (if provided)
    clean_subtitle = (subtitle or "").strip()
    if clean_subtitle:
        s_bbox = draw.textbbox((0, 0), clean_subtitle, font=sub_font)
        sw = s_bbox[2] - s_bbox[0]
        sx = (w - sw) // 2
        draw.text((sx + 1, curr_y + 2), clean_subtitle, fill=(0, 0, 0, 200), font=sub_font)
        draw.text((sx, curr_y), clean_subtitle, fill=(238, 232, 222), font=sub_font)

    # 4. Speaker in Lower Third
    speaker_text = f"Speaker: {preacher}" if preacher else "Victory Christian Fellowship"
    p_bbox = draw.textbbox((0, 0), speaker_text, font=sans_font)
    pw = p_bbox[2] - p_bbox[0]
    px = (w - pw) // 2
    py = 835
    draw.text((px + 1, py + 2), speaker_text, fill=(0, 0, 0, 220), font=sans_font)
    draw.text((px, py), speaker_text, fill=(240, 240, 245), font=sans_font)

    # Subtle Warm Accent Line under Speaker
    line_w = min(pw + 60, 360)
    line_y = py + 52
    draw.line([((w - line_w) // 2, line_y), ((w + line_w) // 2, line_y)], fill=(234, 160, 60, 200), width=2)

    # 5. Scripture & Date Line (Spaced Upper Caps)
    ref_parts = []
    if scripture and scripture.strip():
        ref_parts.append(scripture.strip().upper())
    if date_str and date_str.strip():
        ref_parts.append(date_str.strip().upper())
    ref_text = "   •   ".join(ref_parts) if ref_parts else "VICTORY CHRISTIAN FELLOWSHIP"

    r_bbox = draw.textbbox((0, 0), ref_text, font=sans_bold_font)
    rw = r_bbox[2] - r_bbox[0]
    rx = (w - rw) // 2
    ry = line_y + 18
    draw.text((rx + 1, ry + 2), ref_text, fill=(0, 0, 0, 220), font=sans_bold_font)
    draw.text((rx, ry), ref_text, fill=(215, 222, 230), font=sans_bold_font)

    dir_name = os.path.dirname(out_image_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    img.save(out_image_path, "JPEG", quality=95)
    return out_image_path

def get_audio_duration_seconds(audio_path):
    """Accurately extracts audio length in seconds using ffprobe or mutagen"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        val = float(out)
        if val > 0:
            return int(val) + 1
    except:
        pass

    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(audio_path)
        if audio and audio.info and audio.info.length:
            return int(audio.info.length) + 1
    except:
        pass

    return None

def build_video_from_audio(audio_path, image_path, output_mp4_path, progress_callback=None):
    """Muxes static graphic image and raw audio file into 1080p MP4 video at lightning speed (under 10s!)"""
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
        "-crf", "32",
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
        except:
            pass
        print(f"FFmpeg error ({res.returncode}): {err_tail}")
        return False
    return os.path.exists(output_mp4_path) and os.path.getsize(output_mp4_path) > 1000
