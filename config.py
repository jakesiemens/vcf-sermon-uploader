import os
import glob
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load local .env if present
env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception as e:
        print(f"Notice: Could not load .env: {e}")

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

# Gemini AI Key for YouTube analysis, timestamps, and description summaries
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OFFICIAL_PLAYLIST_ID = os.environ.get("OFFICIAL_PLAYLIST_ID", "PLGQORcmRVjX0")

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
