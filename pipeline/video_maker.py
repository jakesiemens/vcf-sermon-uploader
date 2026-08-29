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

BACKGROUND_PATH = os.path.join(STATIC_DIR, "background.jpg")

def render_sermon_backdrop(title, preacher, date_str, out_image_path):
    """Generates stunning 1920x1080 graphic card with sunset backdrop and high-contrast typography"""
    w, h = 1920, 1080
    
    if os.path.exists(BACKGROUND_PATH):
        try:
            base_bg = Image.open(BACKGROUND_PATH).convert("RGBA")
            if base_bg.size != (w, h):
                base_bg = base_bg.resize((w, h), Image.Resampling.LANCZOS)
            
            # Smooth dark vignette overlay so white and gold text pops
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw_over = ImageDraw.Draw(overlay)
            for y in range(h):
                if 230 <= y <= 980:
                    dist = abs(y - 590) / 380.0
                    alpha = int(140 * (1.0 - (dist ** 2) * 0.45))
                    draw_over.line([(0, y), (w, y)], fill=(10, 18, 30, max(0, min(165, alpha))))
                elif y > 980:
                    alpha = int(140 * (1.0 - (y - 980) / 100.0))
                    if alpha > 0:
                        draw_over.line([(0, y), (w, y)], fill=(10, 18, 30, alpha))
                elif y < 230:
                    alpha = int(85 * (1.0 - y / 230.0))
                    draw_over.line([(0, y), (w, y)], fill=(10, 18, 30, alpha))
            
            img = Image.alpha_composite(base_bg, overlay).convert("RGB")
        except Exception as e:
            print(f"Background load notice: {e}")
            img = Image.new("RGB", (w, h), BG_COLOR)
    else:
        img = Image.new("RGB", (w, h), BG_COLOR)

    draw = ImageDraw.Draw(img)

    # Logo
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo.thumbnail((500, 145), Image.Resampling.LANCZOS)
            lw, lh = logo.size
            img.paste(logo, ((w - lw) // 2, 115), mask=logo)
        except Exception as e:
            print(f"Logo notice: {e}")

    # Orange accent line
    line_w = 380
    line_y = 295
    draw.rectangle([((w - line_w) // 2, line_y), ((w + line_w) // 2, line_y + 4)], fill=ORANGE_BAR)

    # Title
    font_size = 64 if len(title) > 30 else 72
    title_font = get_font(font_size, bold=True)
    wrap_width = 30 if font_size == 72 else 36
    title_lines = textwrap.wrap(title.upper(), width=wrap_width)

    total_title_h = len(title_lines) * (font_size + 18)
    title_start_y = 450 + (120 - total_title_h) // 2
    curr_y = title_start_y

    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_w = bbox[2] - bbox[0]
        tx = (w - text_w) // 2
        # Soft shadow for maximum contrast
        draw.text((tx + 3, curr_y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((tx, curr_y), line, fill=TITLE_COLOR, font=title_font)
        curr_y += font_size + 18

    # Preacher
    preacher_font = get_font(44, bold=True)
    preacher_text = f"Preacher: {preacher}" if preacher else "Victory Christian Fellowship"
    p_bbox = draw.textbbox((0, 0), preacher_text, font=preacher_font)
    pw = p_bbox[2] - p_bbox[0]
    px = (w - pw) // 2
    py = 760
    draw.text((px + 2, py + 2), preacher_text, fill=(0, 0, 0), font=preacher_font)
    draw.text((px, py), preacher_text, fill=PREACHER_COLOR, font=preacher_font)

    # Date
    date_font = get_font(36, bold=False)
    d_bbox = draw.textbbox((0, 0), date_str, font=date_font)
    dw = d_bbox[2] - d_bbox[0]
    dx = (w - dw) // 2
    dy = 840
    draw.text((dx + 2, dy + 2), date_str, fill=(0, 0, 0), font=date_font)
    draw.text((dx, dy), date_str, fill=(226, 232, 240), font=date_font)

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
        "-g", "1",
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
