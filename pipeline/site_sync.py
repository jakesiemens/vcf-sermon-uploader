import os
import json
import base64
import requests
import subprocess
from datetime import datetime
from config import ARCHIVE_JSON, WEBSITE_DIR, GITHUB_REPO, GITHUB_TOKEN

def sync_new_sermon_to_website(video_id, title, preacher, preached_date_iso, display_date, scripture="", duration_seconds=0):
    """Updates sermons_youtube_archive_clean.json via local git OR cloud GitHub API"""
    try:
        dt = datetime.strptime(preached_date_iso, "%Y-%m-%d")
        ts = int(dt.timestamp() * 1000)
        short_date = dt.strftime("%b %d, %Y")
    except:
        dt = datetime.now()
        ts = int(dt.timestamp() * 1000)
        short_date = dt.strftime("%b %d, %Y")

    key = f"youtube_{video_id}"
    new_entry = {
        "videoId": video_id,
        "title": title,
        "speaker": preacher or "Victory Christian Fellowship",
        "passage": scripture or "",
        "date": display_date,
        "uploadedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "short_date": short_date,
        "youtube_title": f"{title} - {preacher} ({display_date}) | Victory Christian Fellowship",
        "preached_date": preached_date_iso,
        "display_date": display_date,
        "preached_timestamp": ts,
        "source": "YouTube"
    }

    # Case 1: Local repository exists
    if os.path.exists(ARCHIVE_JSON):
        with open(ARCHIVE_JSON, "r", encoding="utf-8") as f:
            archive = json.load(f)

        existing_key = None
        if isinstance(archive, dict):
            for k, v in archive.items():
                if isinstance(v, dict) and (v.get("videoId") == video_id or v.get("video_id") == video_id):
                    existing_key = k
                    break
            target_key = existing_key or key
            archive[target_key] = new_entry
        elif isinstance(archive, list):
            archive.insert(0, new_entry)

        with open(ARCHIVE_JSON, "w", encoding="utf-8") as f:
            json.dump(archive, f, indent=2, ensure_ascii=False)

        try:
            subprocess.run(["git", "add", "sermons_youtube_archive_clean.json"], cwd=WEBSITE_DIR, check=True)
            subprocess.run(["git", "commit", "-m", f"Add new sermon: {title}"], cwd=WEBSITE_DIR, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=WEBSITE_DIR, check=True)
            print("Successfully synced and pushed new sermon to GitHub Pages via local git!")
        except Exception as e:
            print(f"Warning: Git push failed: {e}")
        return True

    # Case 2: Cloud execution via GitHub REST API
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/sermons_youtube_archive_clean.json"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "VCF-Sermon-Publisher"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        resp = requests.get(api_url, headers=headers)
        if resp.status_code == 200:
            file_data = resp.json()
            sha = file_data["sha"]
            raw_content = base64.b64decode(file_data["content"]).decode("utf-8")
            archive = json.loads(raw_content)

            if isinstance(archive, dict):
                archive[key] = new_entry
            elif isinstance(archive, list):
                archive.insert(0, new_entry)

            new_json_str = json.dumps(archive, indent=2, ensure_ascii=False)
            encoded_content = base64.b64encode(new_json_str.encode("utf-8")).decode("utf-8")

            put_data = {
                "message": f"Add new sermon: {title}",
                "content": encoded_content,
                "sha": sha,
                "branch": "main"
            }
            put_resp = requests.put(api_url, headers=headers, json=put_data)
            if put_resp.status_code in [200, 201]:
                print(f"[Cloud GitHub API] Successfully pushed new sermon {video_id} to GitHub Pages!")
                return True
            else:
                print(f"[Cloud GitHub API] Failed to update: {put_resp.status_code} - {put_resp.text}")
    except Exception as e:
        print(f"[Cloud GitHub API] Error syncing to GitHub: {e}")

    return False
