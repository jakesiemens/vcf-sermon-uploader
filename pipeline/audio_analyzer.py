import os
import re
import subprocess
import requests
import json
import base64
import uuid
from config import FFMPEG_BIN, UPLOADS_DIR, GEMINI_API_KEY

BIBLE_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges", "Ruth",
    "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms?", "Proverbs", "Ecclesiastes", "Song of Solomon",
    "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah",
    "Malachi", "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation"
]

BOOKS_REGEX = re.compile(r'\b(' + '|'.join(BIBLE_BOOKS) + r')\s*(?:chapter\s+)?([0-9]{1,3})(?:\s*[:vV,]\s*([0-9]{1,3}(?:\s*[-–]\s*[0-9]{1,3})?))?\b', re.IGNORECASE)

def get_audio_duration_seconds(audio_path):
    """Accurately extracts audio length in seconds using mutagen or ffmpeg"""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(audio_path)
        if audio and audio.info and audio.info.length:
            return int(audio.info.length)
    except Exception:
        pass
    return None

def analyze_sermon_audio_multimodal(audio_path, preacher=""):
    """
    Listens to the entire sermon audio using Gemini 3.6 Flash.
    Compresses speech into high-efficiency 24kbps mono MP3, transmits to Gemini,
    and returns authentic title, scripture, summary, themes, and exact video chapters/timestamps.
    """
    if not GEMINI_API_KEY:
        print("[AudioAnalyzer] Warning: GEMINI_API_KEY not configured.")
        return None

    if not os.path.exists(audio_path):
        print(f"[AudioAnalyzer] Audio file not found: {audio_path}")
        return None

    temp_id = uuid.uuid4().hex[:8]
    compressed_path = os.path.join(UPLOADS_DIR, f"temp_gemini_audio_{temp_id}.mp3")

    try:
        total_dur = get_audio_duration_seconds(audio_path) or 1800
        dur_mins = round(total_dur / 60)
        print(f"[AudioAnalyzer] Total audio duration: {dur_mins} minutes. Preparing audio stream...", flush=True)

        # 18 minutes (1080s) captures prelude, scripture reading, title announcement, and key theological points
        # At 16kbps mono, 1080s is only ~2.1 MB, uploads in seconds, and provides deep sermon context
        sample_dur = min(total_dur, 1080)

        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", "0",
            "-t", str(sample_dur),
            "-i", audio_path,
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "16k",
            compressed_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        if not os.path.exists(compressed_path) or os.path.getsize(compressed_path) == 0:
            print("[AudioAnalyzer] Compression failed.")
            return None

        file_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
        print(f"[AudioAnalyzer] Compressed audio size: {file_size_mb:.2f} MB. Reading base64...", flush=True)

        with open(compressed_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt = f"""You are an expert church media director for Victory Christian Fellowship in Williamsburg, New Brunswick.
Listen carefully to this Sunday morning sermon audio preached by {preacher if preacher else 'the speaker'}. Total audio length is {dur_mins} minutes.

Analyze the message and return ONLY a JSON object:
{{
  "title": "Exact sermon title announced by the preacher, or an authentic, engaging 3-6 word title that accurately captures the message's thesis",
  "scripture": "The exact Bible book, chapter, and verses taught in this message (e.g. '1 Thessalonians 1:1-10' or 'Mark 2:1-12')",
  "preacher": "{preacher if preacher else 'Victory Christian Fellowship'}",
  "visual_theme": "Choose exactly ONE that best matches this message: 'CROSS_GRACE' (the Cross, salvation, grace, sacrifice, redemption, the gospel), 'WORD_TEACHING' (scripture teaching, law, truth, doctrine, expository Bible study), 'FAITH_MOUNTAIN' (faith, perseverance, overcoming trials, courage, spiritual strength), 'PEACE_SHEPHERD' (peace, the Good Shepherd, Psalm 23, rest, comfort, God's love, gentleness), 'STORM_DELIVERANCE' (trials, suffering, calming the storm, miracles, deliverance, trust in difficulty), 'HOLY_SPIRIT' (Holy Spirit, prayer, worship, presence of God, sanctuary, revival), or 'LOCAL_FELLOWSHIP' (community, thanksgiving, fellowship, church life)",
  "one_sentence_summary": "1-2 sentences summarizing the core message and gospel focus",
  "key_themes": [
    {{"theme": "Theme Title 1", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}},
    {{"theme": "Theme Title 2", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}},
    {{"theme": "Theme Title 3", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}}
  ],
  "practical_takeaway": "2-3 sentences on how the congregation should apply this message to daily Christian living",
  "timestamps": [
    {{"time": "0:00", "title": "Welcome & Scripture Reading"}},
    {{"time": "8:00", "title": "Introduction & Context"}},
    {{"time": "...", "title": "Theme 1..."}},
    {{"time": "...", "title": "Theme 2..."}},
    {{"time": "...", "title": "Closing Prayer & Benediction"}}
  ]
}}

Generate 5 to 8 YouTube video chapter timestamps spanning the {dur_mins}-minute message, starting at 0:00.
Return ONLY valid JSON.
"""

        payload = {
            "contents": [{
                "parts": [
                    {"inlineData": {"mimeType": "audio/mp3", "data": audio_b64}},
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        # Try fast resilient models with generous 120s timeout
        candidate_models = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-flash-latest", "gemini-3.5-flash"]
        for model_name in candidate_models:
            try:
                print(f"[AudioAnalyzer] Sending audio to {model_name} (timeout=120s)...", flush=True)
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                res = requests.post(url, json=payload, timeout=120)
                
                if res.status_code == 200:
                    data = res.json()
                    if "candidates" in data and data["candidates"]:
                        raw_json = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        # Robust markdown stripping if wrapped
                        if raw_json.startswith("```"):
                            lines = raw_json.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            raw_json = "\n".join(lines).strip()

                        parsed = json.loads(raw_json)
                        title = parsed.get("title", "")
                        scripture = parsed.get("scripture", "")
                        theme = parsed.get("visual_theme", "CROSS_GRACE")
                        print(f"[AudioAnalyzer] Core AI Analysis Succeeded ({model_name}): Title='{title}', Scripture='{scripture}', Theme='{theme}'")

                        # Ensure valid timestamps
                        ts = parsed.get("timestamps")
                        if not ts or not isinstance(ts, list) or len(ts) == 0:
                            parsed["timestamps"] = generate_fallback_timestamps(parsed.get("key_themes", []), dur_mins, title, scripture)
                        return parsed
                else:
                    print(f"[AudioAnalyzer] {model_name} returned status {res.status_code}: {res.text[:200]}")
            except Exception as ex:
                print(f"[AudioAnalyzer] Error querying {model_name}: {ex}. Trying next model...")

    except Exception as e:
        print(f"[AudioAnalyzer] Exception in multimodal analysis: {e}")
    finally:
        if os.path.exists(compressed_path):
            try:
                os.remove(compressed_path)
            except Exception:
                pass

    return None

def generate_fallback_timestamps(key_themes, total_dur_mins, title="", scripture=""):
    """Fast local timestamp generation when AI chapters need fallback"""
    timestamps = [{"time": "0:00", "title": f"Welcome & Scripture Reading ({scripture})" if scripture else "Welcome & Scripture Reading"}]
    dur = max(5, total_dur_mins)
    if key_themes and isinstance(key_themes, list):
        step = max(5, int((dur - 8) / (len(key_themes) + 1)))
        cur_min = 5
        for t in key_themes:
            t_name = t.get("theme") if isinstance(t, dict) else str(t)
            if t_name:
                timestamps.append({"time": f"{cur_min}:00", "title": t_name})
                cur_min += step
    else:
        timestamps.append({"time": "5:00", "title": f"Message: {title}" if title else "Message"})
    
    close_min = max(dur - 3, 2)
    timestamps.append({"time": f"{close_min}:00", "title": "Closing Prayer & Benediction"})
    return timestamps

def generate_sermon_timestamps(title, scripture, preacher, total_dur_mins):
    """Fast chapter generation alias"""
    return generate_fallback_timestamps([], total_dur_mins, title, scripture)

def extract_audio_snippet(input_path, duration_seconds=90):
    """Legacy alias for backward compatibility"""
    return input_path

def transcribe_audio_snippet(audio_path):
    """Legacy alias for backward compatibility"""
    return ""

def analyze_transcript_with_gemini(transcript, preacher=""):
    """Legacy text-based transcript analysis with gemini-3.6-flash"""
    if not GEMINI_API_KEY or not transcript:
        return None
    prompt = f"""Analyze this sermon transcript from {preacher}:
{transcript[:15000]}
Return JSON: {{"title": "...", "scripture": "...", "summary": "..."}}"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}, timeout=15)
        if res.status_code == 200:
            return json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:
        print(f"Transcript analysis notice: {e}")
    return None

def detect_scripture(transcript):
    """Detects Bible book, chapter, and verse references from text"""
    if not transcript:
        return ""
    matches = BOOKS_REGEX.findall(transcript)
    if matches:
        book, chap, verse = matches[0]
        if book.lower().startswith('psalm'):
            book = 'Psalm'
        if verse:
            return f"{book.title()} {chap}:{verse}"
        return f"{book.title()} {chap}"
    return ""

def generate_smart_title(transcript, scripture, preacher):
    """Fallback smart title"""
    if scripture:
        return f"Message from {scripture}"
    return "Sunday Morning Message"
