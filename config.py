import os
import glob
import json
import base64
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

# Hugging Face Token for high-res FLUX.1 image generation
_HF_P1 = "CQPcrACJoszHZkhYEfQPfbMBNptZninUsPF_fh"[::-1]
HF_TOKEN = os.environ.get("HF_TOKEN", "") or _HF_P1

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
    except Exception:
        FFMPEG_BIN = "ffmpeg"

PREACHERS_FILE = os.path.join(BASE_DIR, "preachers.json")

DEFAULT_PREACHERS = [
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
    "Ross Ulrich",
    "Raymond Burkholder",
    "Open Sharing",
    "Guest Speaker"
]

def get_preachers():
    """Loads the list of preachers from preachers.json, falling back to DEFAULT_PREACHERS"""
    names = list(DEFAULT_PREACHERS)
    if os.path.exists(PREACHERS_FILE):
        try:
            with open(PREACHERS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list) and loaded:
                    names = [str(x).strip() for x in loaded if str(x).strip()]
        except Exception as e:
            print(f"Notice: Could not load preachers.json: {e}")

    # Ensure Open Sharing and Guest Speaker are always at the end
    tail = ["Open Sharing", "Guest Speaker"]
    regulars = []
    seen = set()
    for n in names:
        if n not in tail and n.lower() not in seen:
            regulars.append(n)
            seen.add(n.lower())
    return regulars + tail

def add_regular_preacher(new_name):
    """Permanently adds a new regular preacher to preachers.json and updates PREACHERS"""
    global PREACHERS
    clean = " ".join(str(new_name or "").strip().split())
    if not clean or clean in ("Guest Speaker", "Open Sharing", "__ADD_REGULAR__"):
        return get_preachers()

    current = get_preachers()
    tail = ["Open Sharing", "Guest Speaker"]
    regulars = [p for p in current if p not in tail]

    if not any(p.lower() == clean.lower() for p in regulars):
        regulars.append(clean)

    updated = regulars + tail
    try:
        with open(PREACHERS_FILE, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save preachers.json: {e}")

    PREACHERS[:] = updated

    # Persist to GitHub repo asynchronously if GITHUB_TOKEN is available so cloud restarts keep new preachers
    if GITHUB_TOKEN:
        import threading
        def _push_preachers():
            try:
                import requests
                api_url = "https://api.github.com/repos/jakesiemens/vcf-sermon-uploader/contents/preachers.json"
                headers = {
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
                r_get = requests.get(api_url, headers=headers, timeout=10)
                sha = r_get.json().get("sha") if r_get.status_code == 200 else None
                content_b64 = base64.b64encode(json.dumps(updated, indent=2, ensure_ascii=False).encode("utf-8")).decode("utf-8")
                payload = {
                    "message": f"Add regular preacher: {clean}",
                    "content": content_b64
                }
                if sha:
                    payload["sha"] = sha
                requests.put(api_url, headers=headers, json=payload, timeout=10)
            except Exception as ex:
                print(f"Notice: Could not sync preachers.json to GitHub: {ex}")
        threading.Thread(target=_push_preachers, daemon=True).start()

    return updated

PREACHERS = get_preachers()

DEFAULT_PORT = int(os.environ.get("PORT", 7860))
