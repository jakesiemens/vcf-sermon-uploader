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
    """Accurately extracts audio length in seconds across all formats (.mp3, .m4a, .wav, .aac, .flac, .ogg)"""
    if not audio_path or not os.path.exists(audio_path):
        return None

    # 1. Mutagen generic File loader (supports MP3, M4A/MP4, WAV, FLAC, OGG, AAC)
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(audio_path)
        if audio and getattr(audio, "info", None) and getattr(audio.info, "length", None):
            val = float(audio.info.length)
            if val > 0:
                return int(val)
    except Exception:
        pass

    # 2. ffprobe
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
            return int(val)
    except Exception:
        pass

    # 3. Parse FFmpeg stderr Duration: HH:MM:SS.xx
    try:
        proc = subprocess.run(
            [FFMPEG_BIN, "-i", audio_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace"
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
        if m:
            hrs, mins, secs = int(m.group(1)), int(m.group(2)), float(m.group(3))
            total = int(hrs * 3600 + mins * 60 + secs)
            if total > 0:
                return total
    except Exception:
        pass

    return None

def _parse_timestamp_to_seconds(ts_str):
    """Parses 'M:SS', 'MM:SS', or 'H:MM:SS' into integer seconds"""
    if not ts_str:
        return None
    s = str(ts_str).strip()
    m = re.search(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", s)
    if not m:
        return None
    if m.group(3) is not None:
        hrs = int(m.group(1))
        mins = int(m.group(2))
        secs = int(m.group(3))
        return hrs * 3600 + mins * 60 + secs
    else:
        mins = int(m.group(1))
        secs = int(m.group(2))
        return mins * 60 + secs

def _format_seconds_to_timestamp(total_seconds):
    """Formats seconds into YouTube chapter timestamp ('M:SS' or 'H:MM:SS')"""
    total_seconds = max(0, int(total_seconds))
    if total_seconds >= 3600:
        hrs = total_seconds // 3600
        rem = total_seconds % 3600
        mins = rem // 60
        secs = rem % 60
        return f"{hrs}:{mins:02d}:{secs:02d}"
    else:
        mins = total_seconds // 60
        secs = total_seconds % 60
        return f"{mins}:{secs:02d}"

def ensure_full_duration_timestamps(raw_timestamps, total_dur_seconds, key_themes=None, title="", scripture=""):
    """
    Validates, normalizes, and guarantees that YouTube chapter timestamps start at 0:00
    and span the ENTIRE sermon duration (including 60 to 80+ minute sermons).
    """
    total_dur_seconds = max(300, int(total_dur_seconds or 3600))
    total_dur_mins = max(5, round(total_dur_seconds / 60))

    parsed_items = []
    if isinstance(raw_timestamps, list):
        for item in raw_timestamps:
            if isinstance(item, dict):
                t_str = str(item.get("time", "")).strip()
                t_title = str(item.get("title", "")).strip()
                sec = _parse_timestamp_to_seconds(t_str)
                if sec is not None and t_title and 0 <= sec < total_dur_seconds - 15:
                    parsed_items.append({"sec": sec, "title": t_title})

    # Sort chronologically and deduplicate close timestamps
    parsed_items.sort(key=lambda x: x["sec"])
    cleaned = []
    for item in parsed_items:
        if not cleaned:
            item["sec"] = 0
            cleaned.append(item)
        else:
            # YouTube requires at least 10 seconds between chapters
            if item["sec"] - cleaned[-1]["sec"] >= 30:
                cleaned.append(item)

    if len(cleaned) < 4:
        return generate_fallback_timestamps(key_themes, total_dur_mins, title, scripture, total_dur_seconds=total_dur_seconds)

    # Check if the timestamps stopped prematurely (e.g. around 15-20 mins on a 60-80 min sermon)
    max_sec = cleaned[-1]["sec"]
    if total_dur_seconds > 1500 and max_sec < total_dur_seconds * 0.58 and max_sec > 300:
        # Scale chapters proportionally across the full sermon duration so the entire sermon is covered
        target_end_sec = int(total_dur_seconds * 0.90)
        scale_factor = target_end_sec / float(max_sec)
        for idx, item in enumerate(cleaned):
            if idx == 0:
                item["sec"] = 0
            else:
                scaled = int(round((item["sec"] * scale_factor) / 15.0) * 15)
                # Ensure strictly increasing by at least 60s
                item["sec"] = min(total_dur_seconds - 60, max(cleaned[idx - 1]["sec"] + 60, scaled))

    return [
        {"time": _format_seconds_to_timestamp(item["sec"]), "title": item["title"]}
        for item in cleaned
    ]

def analyze_sermon_audio_multimodal(audio_path, preacher="", custom_title="", custom_scripture=""):
    """
    Listens to the full sermon audio using Gemini Flash.
    Compresses the entire speech recording (up to 2 hours) into high-efficiency 12kbps mono MP3,
    transmits to Gemini, and returns authentic title, scripture, summary, themes, custom artwork prompt,
    and full-length video chapters/timestamps.
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
        total_dur = get_audio_duration_seconds(audio_path) or 3600
        dur_mins = max(1, round(total_dur / 60))
        total_timestamp_str = _format_seconds_to_timestamp(total_dur)
        print(f"[AudioAnalyzer] Total audio duration: {dur_mins} minutes ({total_dur}s / {total_timestamp_str}). Compressing full sermon audio...", flush=True)

        # Compress the FULL sermon (up to 2.5 hours = 9000s) at 12kbps 12kHz mono MP3 (~5.2 MB per hour)
        # so Gemini hears the entire sermon from beginning to end!
        sample_dur = min(total_dur, 9000)

        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", "0",
            "-t", str(sample_dur),
            "-i", audio_path,
            "-vn",
            "-ar", "12000",
            "-ac", "1",
            "-b:a", "12k",
            compressed_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        if not os.path.exists(compressed_path) or os.path.getsize(compressed_path) == 0:
            print("[AudioAnalyzer] Compression failed.")
            return None

        file_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
        print(f"[AudioAnalyzer] Full sermon compressed audio size: {file_size_mb:.2f} MB ({sample_dur}s). Encoding base64...", flush=True)

        with open(compressed_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        context_hints = []
        if custom_title:
            context_hints.append(f"Provided Sermon Title: \"{custom_title}\"")
        if custom_scripture:
            context_hints.append(f"Provided Scripture Passage: \"{custom_scripture}\"")
        hints_block = ("\n" + "\n".join(context_hints) + "\n") if context_hints else ""

        prompt = f"""You are an expert evangelical Christian media director.
Listen carefully to this full-length sermon audio preached by {preacher if preacher else 'the speaker'}.
Total sermon length is {dur_mins} minutes ({total_timestamp_str}).{hints_block}
IMPORTANT GUIDELINES:
1. Do NOT assume this was preached on a Sunday or at a specific building/location unless explicitly stated—keep the summary focused purely on the biblical message and teaching.
2. You have been given the ENTIRE {dur_mins}-minute recording from start (0:00) to finish ({total_timestamp_str}). Your video chapter timestamps MUST span the ENTIRE {dur_mins}-minute duration from 0:00 all the way through the later sections of the message (e.g. 30:00, 45:00, {max(20, dur_mins - 5)}:00). Never stop timestamps at 15 or 20 minutes!

Analyze the message and return ONLY a valid JSON object matching this exact schema:
{{
  "title": "Exact sermon title announced by the preacher (or use the provided title if given), or an authentic, engaging 3-6 word title that captures the message's thesis",
  "scripture": "The exact Bible book, chapter, and verses taught in this message (e.g. '1 Thessalonians 1:1-10' or 'Genesis 2:18; John 15:15')",
  "preacher": "{preacher if preacher else 'Victory Christian Fellowship'}",
  "visual_theme": "Choose ONE: 'CROSS_GRACE', 'WORD_TEACHING', 'FAITH_MOUNTAIN', 'PEACE_SHEPHERD', 'STORM_DELIVERANCE', 'HOLY_SPIRIT', or 'LOCAL_FELLOWSHIP'",
  "image_prompt": "A vivid 35-50 word photorealistic scene description for the sermon thumbnail background that directly illustrates the specific topic, metaphor, or biblical teaching of THIS message (e.g. sunlit nature, open Bible on rustic wood outdoors, mountains, calm waters, harvest field, rugged cross at sunrise, anchor in waves, shepherd pastures, warm golden sunrise over forest/river). STRICT RULE: We are an evangelical, non-denominational church—NEVER include old-fashioned, gothic, catholic, liturgical, or cryptic inside-of-church buildings, cathedrals, stained glass, pews, or altars. NO text or letters in the scene.",
  "one_sentence_summary": "2-3 sentences summarizing the core biblical message and gospel focus (do NOT write 'delivers a Sunday message' or mention a church location)",
  "key_themes": [
    {{"theme": "Theme Title 1", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}},
    {{"theme": "Theme Title 2", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}},
    {{"theme": "Theme Title 3", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}},
    {{"theme": "Theme Title 4", "explanation": "2-3 sentences explaining this theme based directly on what was preached"}}
  ],
  "practical_takeaway": "2-3 sentences on how believers can practically apply this message in daily Christian living",
  "timestamps": [
    {{"time": "0:00", "title": "Introduction & Scripture Reading"}},
    {{"time": "...", "title": "..."}},
    {{"time": "...", "title": "Closing Application & Prayer"}}
  ]
}}

Generate 7 to 10 accurate YouTube video chapter timestamps distributed across the ENTIRE {dur_mins}-minute sermon (from 0:00 up to ~{max(10, dur_mins - 4)}:00). Use M:SS format for times under 60 minutes (e.g. "42:15") and H:MM:SS for times 60 minutes or longer (e.g. "1:04:30").
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

        candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-flash-latest"
        ]
        for model_name in candidate_models:
            try:
                print(f"[AudioAnalyzer] Sending full {dur_mins}-min audio to {model_name} (timeout=180s)...", flush=True)
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                res = requests.post(url, json=payload, timeout=180)
                
                if res.status_code == 200:
                    data = res.json()
                    if "candidates" in data and data["candidates"]:
                        raw_json = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if raw_json.startswith("```"):
                            lines = raw_json.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            raw_json = "\n".join(lines).strip()

                        parsed = json.loads(raw_json)
                        title = custom_title or parsed.get("title", "")
                        scripture = custom_scripture or parsed.get("scripture", "")
                        theme = parsed.get("visual_theme", "WORD_TEACHING")
                        print(f"[AudioAnalyzer] Core AI Analysis Succeeded ({model_name}): Title='{title}', Scripture='{scripture}', Theme='{theme}'")

                        # Validate and ensure timestamps cover the full sermon duration
                        parsed["timestamps"] = ensure_full_duration_timestamps(
                            parsed.get("timestamps"),
                            total_dur_seconds=total_dur,
                            key_themes=parsed.get("key_themes", []),
                            title=title,
                            scripture=scripture
                        )
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

def generate_fallback_timestamps(key_themes, total_dur_mins, title="", scripture="", total_dur_seconds=None):
    """Generates well-spaced chapter timestamps spanning the full sermon duration when AI chapters need fallback"""
    if not total_dur_seconds:
        total_dur_seconds = max(300, int((total_dur_mins or 60) * 60))

    timestamps = [{
        "time": "0:00",
        "title": f"Introduction & Scripture ({scripture})" if scripture else "Introduction & Opening"
    }]

    theme_titles = []
    if key_themes and isinstance(key_themes, list):
        for t in key_themes:
            t_name = t.get("theme") if isinstance(t, dict) else str(t)
            if t_name and t_name.strip():
                theme_titles.append(t_name.strip())

    if not theme_titles:
        theme_titles = [
            f"Biblical Context: {scripture}" if scripture else "Biblical Context & Foundation",
            f"Core Teaching: {title}" if title else "Core Scriptural Teaching",
            "Walking in Truth & Faith",
            "Practical Application for Daily Living"
        ]

    # Distribute chapters evenly between 8% and 88% of the total sermon duration
    start_sec = int(total_dur_seconds * 0.10)
    end_sec = int(total_dur_seconds * 0.88)
    count = len(theme_titles)
    step_sec = max(120, int((end_sec - start_sec) / max(1, count)))

    cur_sec = start_sec
    for t_name in theme_titles:
        rounded_sec = int(round(cur_sec / 30.0) * 30)
        if rounded_sec < total_dur_seconds - 90:
            timestamps.append({
                "time": _format_seconds_to_timestamp(rounded_sec),
                "title": t_name
            })
        cur_sec += step_sec

    close_sec = max(cur_sec - step_sec + 120, int(round((total_dur_seconds * 0.92) / 30.0) * 30))
    if close_sec < total_dur_seconds - 30:
        timestamps.append({
            "time": _format_seconds_to_timestamp(close_sec),
            "title": "Closing Application & Prayer"
        })

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
    """Legacy text-based transcript analysis with gemini-2.5-flash"""
    if not GEMINI_API_KEY or not transcript:
        return None
    prompt = f"""Analyze this sermon transcript from {preacher}:
{transcript[:15000]}
Return JSON: {{"title": "...", "scripture": "...", "summary": "..."}}"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
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
    return "Biblical Message"
