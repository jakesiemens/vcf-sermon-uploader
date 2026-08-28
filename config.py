import os
import glob
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Unpack environment secrets if provided in cloud
if os.environ.get("YOUTUBE_TOKEN_JSON"):
    with open(os.path.join(BASE_DIR, "token.json"), "w", encoding="utf-8") as f:
        f.write(os.environ["YOUTUBE_TOKEN_JSON"])

if os.environ.get("YOUTUBE_CLIENT_SECRET_JSON"):
    with open(os.path.join(BASE_DIR, "client_secret.json"), "w", encoding="utf-8") as f:
        f.write(os.environ["YOUTUBE_CLIENT_SECRET_JSON"])
WEBSITE_DIR = os.environ.get("WEBSITE_DIR", r"d:\Personal\VCF Website")

# Token resolution (container local or website dir)
local_token = os.path.join(BASE_DIR, "token.json")
if os.path.exists(local_token):
    TOKEN_PATH = local_token
else:
    TOKEN_PATH = os.path.join(WEBSITE_DIR, "token.json")

# Client secret resolution
local_cs = os.path.join(BASE_DIR, "client_secret.json")
if os.path.exists(local_cs):
    CLIENT_SECRET_PATH = local_cs
else:
    cs_files = glob.glob(os.path.join(WEBSITE_DIR, "client_secret*.json"))
    CLIENT_SECRET_PATH = cs_files[0] if cs_files else os.path.join(WEBSITE_DIR, "client_secret.json")

# Archive JSON
ARCHIVE_JSON = os.path.join(WEBSITE_DIR, "sermons_youtube_archive_clean.json")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "jakesiemens/vcf-site")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOGO_PATH = os.path.join(STATIC_DIR, "logo.png")
CLOUDFLARED_BIN = r"d:\Personal\cloudflared.exe"

# FFmpeg resolution
if shutil.which("ffmpeg"):
    FFMPEG_BIN = "ffmpeg"
else:
    try:
        import imageio_ffmpeg
        FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
    except:
        FFMPEG_BIN = "ffmpeg"

PREACHERS = [
    "Jake Siemens",
    "Corny Janzen",
    "Jake Driedger",
    "Jerry Mawhorr",
    "John Banman",
    "Henry Wall",
    "John Enns",
    "Bernie Bergen",
    "Aaron Knelsen",
    "Seth Janzen",
    "David Hiebert",
    "Joe Brubacher",
    "Johan Fehr",
    "Matthew Janzen",
    "Peter Driedger",
    "Henry Klassen",
    "Mark Villeneuve",
    "Open Sharing",
    "Guest Speaker"
]

DEFAULT_PORT = int(os.environ.get("PORT", 7860))
