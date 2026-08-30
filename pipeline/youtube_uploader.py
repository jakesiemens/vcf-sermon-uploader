import os
import json
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests
from config import TOKEN_PATH, CLIENT_SECRET_PATH, GEMINI_API_KEY, OFFICIAL_PLAYLIST_ID

def generate_gemini_summary(title, preacher, scripture, transcript=""):
    """Calls Google Gemini to generate a warm, 1-paragraph summary for the YouTube description"""
    if not GEMINI_API_KEY:
        return ""
    
    prompt = f"""You are a church media assistant for Victory Christian Fellowship in Williamsburg, New Brunswick.
Write an engaging, 1-paragraph sermon summary (3 to 4 sentences) for a Sunday sermon YouTube video description.
Preacher: {preacher}
Sermon Title: {title}
Scripture: {scripture if scripture else 'Biblical Teaching'}
Additional Context/Notes: {transcript[:500] if transcript else ''}

Rules:
1. Write 3-4 inspiring sentences summarizing the spiritual core of the sermon.
2. Do not use hashtags, greetings, bullet points, or sign-offs.
3. Output only the summary paragraph.
"""
    for model_name in ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if "candidates" in data and data["candidates"]:
                    summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if summary:
                        return summary
        except Exception as e:
            print(f"Gemini summary notice ({model_name}): {e}")
            
    return ""

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

    # Generate 1-paragraph AI summary
    summary_para = generate_gemini_summary(title, preacher, scripture, transcript)

    # Description
    desc_lines = [
        f"{title} | {preacher}",
    ]
    if scripture:
        desc_lines.append(f"Scripture: {scripture}")
    desc_lines.append("Victory Christian Fellowship • Williamsburg, New Brunswick")
    desc_lines.append(f"Date Preached: {display_date}")
    desc_lines.append("")

    if summary_para:
        desc_lines.append(summary_para)
        desc_lines.append("")

    desc_lines.extend([
        "Visit our website for more sermons, service times, and resources:",
        "https://victorychristianfellowship.ca/sermons.html"
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

    # Add to Official Chronological Playlist at position 0 (top)
    add_video_to_official_playlist(video_id)

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": yt_title
    }
