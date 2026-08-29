import os
import json
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import TOKEN_PATH, CLIENT_SECRET_PATH

def get_youtube_service():
    """Initializes authenticated YouTube API client from env var or file"""
    info = None

    # 1. Try direct environment variable
    env_token = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
    if env_token:
        try:
            if (env_token.startswith("'") and env_token.endswith("'")) or (env_token.startswith('"') and env_token.endswith('"')):
                env_token = env_token[1:-1].strip()
            info = json.loads(env_token)
        except Exception as e:
            print(f"Warning: Could not parse YOUTUBE_TOKEN_JSON env var: {e}")

    # 2. Try token file
    if not info and os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    info = json.loads(content)
        except Exception as e:
            print(f"Warning: Could not parse {TOKEN_PATH}: {e}")

    if not info:
        raise RuntimeError("YouTube authentication token not configured. Please add YOUTUBE_TOKEN_JSON under Environment in Render.")

    creds = Credentials.from_authorized_user_info(info)
    return build("youtube", "v3", credentials=creds)

def upload_sermon_to_youtube(video_path, thumbnail_path, title, preacher, display_date, scripture="", privacy_status="public"):
    """Uploads MP4 video and custom thumbnail to YouTube channel"""
    youtube = get_youtube_service()

    # Clean YouTube Title
    if preacher and scripture:
        yt_title = f"{title} ({preacher}, {scripture})"
    elif preacher:
        yt_title = f"{title} - {preacher}"
    else:
        yt_title = title

    # Description
    desc_lines = [
        "Victory Christian Fellowship",
        "Williamsburg, New Brunswick",
        "",
        f"Sermon: {title}",
        f"Preacher: {preacher}",
        f"Date Preached: {display_date}",
    ]
    if scripture:
        desc_lines.append(f"Scripture: {scripture}")
    desc_lines.extend([
        "",
        "Visit our website for more sermons, service times, and directions:",
        "https://victorychristianfellowship.ca",
        "",
        "1534 NB-107, Williamsburg, NB  E6B 1W9"
    ])
    yt_description = "\n".join(desc_lines)

    tags = ["Victory Christian Fellowship", "VCF Sermons", "Williamsburg NB", "New Brunswick", "Sermon"]
    if preacher:
        tags.append(preacher)
    if scripture:
        tags.append(scripture)

    body = {
        "snippet": {
            "title": yt_title[:100],
            "description": yt_description,
            "tags": tags,
            "categoryId": "29"
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
    }

    # Upload Video (Resumable)
    media = MediaFileUpload(video_path, chunksize=1024*1024*5, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
    
    video_id = response.get("id")
    print(f"Video uploaded successfully! Video ID: {video_id}")

    # Set Custom Thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            ).execute()
            print(f"Thumbnail uploaded for {video_id}")
        except Exception as e:
            print(f"Thumbnail upload error (may retry later): {e}")

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": yt_title
    }
