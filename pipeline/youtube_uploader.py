import os
import json
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests
from config import TOKEN_PATH, CLIENT_SECRET_PATH, GEMINI_API_KEY, OFFICIAL_PLAYLIST_ID

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

def generate_rich_sermon_description(title, preacher, scripture, display_date, transcript=""):
    """Generates a complete, structured YouTube description with overview, key themes, practical takeaway, and links"""
    website_link = "https://victorychristianfellowship.ca/sermons.html"
    subscribe_link = "https://www.youtube.com/@VictoryChristianFellowship?sub_confirmation=1"
    
    if not GEMINI_API_KEY:
        lines = [
            f"{preacher} delivers a Sunday message titled '{title}' at Victory Christian Fellowship in Williamsburg, New Brunswick.",
            "",
            "Connect With Us",
            "",
            f"Church Website: {website_link}",
            f"Subscribe for Weekly Sermons: {subscribe_link}"
        ]
        if scripture:
            lines.append(f"Scripture Reference: {scripture}")
        lines.append(f"Date Preached: {display_date}")
        return "\n".join(lines)
    
    prompt = f"""You are an expert church media specialist for Victory Christian Fellowship in Williamsburg, New Brunswick.
Generate a structured YouTube video description based on this sermon info:
Preacher: {preacher}
Title: {title}
Scripture: {scripture if scripture else 'Biblical Teaching'}
Date: {display_date}
Transcript/Context: \"\"\"{transcript[:15000] if transcript else ''}\"\"\"

Format the description EXACTLY like this template:

{preacher} examines biblical teachings in {scripture if scripture else title}—exploring the theological meaning, spiritual significance, and modern application.

Key Themes in This Message

[Theme 1 Title]: [1-2 sentence explanation based on the sermon]

[Theme 2 Title]: [1-2 sentence explanation based on the sermon]

[Theme 3 Title]: [1-2 sentence explanation based on the sermon]

Practical Takeaway
[1-2 sentences on how believers should apply this message to their daily Christian walk]

Connect With Us

Church Website: {website_link}

Subscribe for Weekly Sermons: {subscribe_link}

Scripture Reference: {scripture if scripture else 'Biblical Teaching'}
Date Preached: {display_date}
"""
    for model_name in ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=12)
            if res.status_code == 200:
                data = res.json()
                if "candidates" in data and data["candidates"]:
                    desc = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if desc:
                        return desc
        except Exception as e:
            print(f"Gemini description notice ({model_name}): {e}")
            
    return f"{title} | {preacher}\nScripture: {scripture}\nDate Preached: {display_date}\n\nChurch Website: {website_link}\nSubscribe: {subscribe_link}"

def add_video_to_official_playlist(video_id):
    """Adds newly published sermon to top (position 0) of the official playlist"""
    if not OFFICIAL_PLAYLIST_ID:
        return
    try:
        yt = get_youtube_service()
        body = {
            "snippet": {
                "playlistId": OFFICIAL_PLAYLIST_ID,
                "position": 0,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
        yt.playlistItems().insert(part="snippet", body=body).execute()
        print(f"Added video {video_id} to top of official playlist {OFFICIAL_PLAYLIST_ID}")
    except Exception as e:
        print(f"Playlist insertion notice: {e}")

def upload_sermon_to_youtube(video_path, thumbnail_path, title, preacher, display_date, scripture="", privacy_status="public", transcript=""):
    """Uploads MP4 video and custom thumbnail to YouTube channel"""
    youtube = get_youtube_service()

    # Clean YouTube Title
    if preacher and scripture:
        yt_title = f"{title} ({preacher}, {scripture})"
    elif preacher:
        yt_title = f"{title} - {preacher}"
    else:
        yt_title = title

    # Generate Rich Structured Description (Summary, Themes, Takeaways, Connect Links)
    yt_description = generate_rich_sermon_description(title, preacher, scripture, display_date, transcript)

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

    # Add to Official Chronological Playlist at position 0 (top)
    add_video_to_official_playlist(video_id)

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": yt_title
    }
