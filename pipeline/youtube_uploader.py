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
        raise RuntimeError("YouTube authentication token not found. Please run reauth.bat or reauth_youtube.py to log in.")

    try:
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_info(info)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save updated refreshed token
            try:
                with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception:
                pass
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        err_msg = str(e)
        if "invalid_grant" in err_msg or "expired" in err_msg.lower():
            raise RuntimeError("YouTube token has expired (Google 7-day limit in Testing mode). Please run reauth.bat or reauth_youtube.py to re-authenticate.")
        raise

def generate_rich_sermon_description(title, preacher, scripture, display_date, transcript="", ai_details=None):
    """Generates a complete, structured YouTube description with overview, key themes, practical takeaway, timestamps, and links"""
    website_link = "https://victorychristianfellowship.ca/sermons.html"
    subscribe_link = "https://www.youtube.com/@VictoryChristianFellowship?sub_confirmation=1"
    
    sections = []

    # 1. Overview
    summary = ""
    key_themes = []
    practical_takeaway = ""
    timestamps = []

    if isinstance(ai_details, dict):
        summary = ai_details.get("one_sentence_summary", "")
        key_themes = ai_details.get("key_themes", [])
        practical_takeaway = ai_details.get("practical_takeaway", "")
        timestamps = ai_details.get("timestamps", [])

    if summary:
        sections.append(f"{preacher} delivers a Sunday message titled '{title}' from {scripture if scripture else 'Scripture'} at Victory Christian Fellowship in Williamsburg, New Brunswick.\n\n{summary}")
    else:
        sections.append(f"{preacher} examines biblical teachings in {scripture if scripture else title}—exploring the theological meaning, spiritual significance, and modern application for believers today.")

    # 2. Key Themes
    if key_themes:
        theme_lines = ["Key Themes in This Message\n"]
        for t in key_themes:
            t_name = t.get("theme", "")
            t_exp = t.get("explanation", "")
            theme_lines.append(f"• {t_name}: {t_exp}")
        sections.append("\n".join(theme_lines))

    # 3. Practical Takeaway
    if practical_takeaway:
        sections.append(f"Practical Takeaway\n{practical_takeaway}")

    # 4. Video Chapters & Timestamps (YouTube Native Chapters)
    if timestamps and len(timestamps) > 0:
        ts_lines = ["Video Chapters & Timestamps:"]
        for ts in timestamps:
            time_str = ts.get("time", "")
            ts_title = ts.get("title", "")
            # Ensure time format has at least m:ss
            ts_lines.append(f"{time_str} - {ts_title}")
        sections.append("\n".join(ts_lines))

    # 5. Connect With Us & Reference Info
    connect_lines = [
        "Connect With Us",
        f"Church Website: {website_link}",
        f"Subscribe for Weekly Sermons: {subscribe_link}",
        "",
        f"Scripture Reference: {scripture if scripture else 'Biblical Teaching'}",
        f"Date Preached: {display_date}"
    ]
    sections.append("\n".join(connect_lines))

    return "\n\n".join(sections)

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

def upload_sermon_to_youtube(video_path, thumbnail_path, title, preacher, display_date, scripture="", privacy_status="public", transcript="", ai_details=None):
    """Uploads MP4 video and custom thumbnail to YouTube channel"""
    youtube = get_youtube_service()

    # Clean YouTube Title
    if preacher and scripture:
        yt_title = f"{title} ({preacher}, {scripture})"
    elif preacher:
        yt_title = f"{title} - {preacher}"
    else:
        yt_title = title

    # Generate Rich Structured Description with Chapters & Timestamps
    yt_description = generate_rich_sermon_description(title, preacher, scripture, display_date, transcript, ai_details=ai_details)

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
    retry_count = 0
    max_retries = 5
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
            retry_count = 0
        except Exception as e:
            err_str = str(e)
            if "quota" in err_str.lower():
                raise
            retry_count += 1
            if retry_count > max_retries:
                raise RuntimeError(f"Network error during YouTube upload after {max_retries} retries: {e}")
            sleep_time = min(30, 2 ** retry_count)
            print(f"Upload chunk interrupted ({e}). Retrying in {sleep_time}s (attempt {retry_count}/{max_retries})...")
            time.sleep(sleep_time)
    
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
