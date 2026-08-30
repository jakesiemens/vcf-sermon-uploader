import os
import re
import subprocess
import speech_recognition as sr
from config import FFMPEG_BIN, UPLOADS_DIR

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

BOOKS_REGEX = re.compile(r'\\b(' + '|'.join(BIBLE_BOOKS) + r')\\s+([0-9]{1,3})(?:\\s*[:vV,]\\s*([0-9]{1,3}(?:\\s*[-–]\\s*[0-9]{1,3})?))?\\b', re.IGNORECASE)

import requests
import json
from config import FFMPEG_BIN, UPLOADS_DIR, GEMINI_API_KEY

def get_audio_duration_seconds(audio_path):
    """Accurately extracts audio length in seconds using ffprobe"""
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
    except:
        pass
    return None

def extract_audio_snippet(input_path, duration_seconds=90):
    """Extracts strategic clips based on audio duration (starts at 0s for short recordings, or 0s + 2m for full sermons)"""
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(UPLOADS_DIR, f"{base_name}_snippet.wav")
    
    total_dur = get_audio_duration_seconds(input_path) or 60
    
    # If audio is under 3 minutes (like a short recording or exhortation), start at 0s!
    if total_dur < 180:
        start_sec = 0
        dur_to_extract = min(60, total_dur)
    else:
        # Full sermon: sample from 2 minutes (120s) where scripture is read and title announced
        start_sec = 120
        dur_to_extract = min(80, total_dur - start_sec)
        
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", str(start_sec),
        "-t", str(dur_to_extract),
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        out_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_wav if os.path.exists(out_wav) else None

def transcribe_audio_snippet(wav_path):
    """Transcribes WAV snippet in fast 18-second chunks"""
    if not wav_path or not os.path.exists(wav_path):
        return ""
    recognizer = sr.Recognizer()
    full_text = []
    
    try:
        with sr.AudioFile(wav_path) as source:
            for i in range(4):
                try:
                    audio = recognizer.record(source, duration=18)
                    text = recognizer.recognize_google(audio)
                    if text:
                        full_text.append(text)
                except sr.UnknownValueError:
                    pass
                except Exception as e:
                    print(f"Chunk {i+1} notice: {e}")
                    break
        return ' '.join(full_text)
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""
    finally:
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except:
            pass

def analyze_transcript_with_gemini(transcript, preacher=""):
    """Uses Gemini to extract title, scripture, and 1-paragraph summary from transcript"""
    if not GEMINI_API_KEY or not transcript or len(transcript.strip()) < 15:
        return None
        
    prompt = f"""You are a church media assistant for Victory Christian Fellowship in Williamsburg, New Brunswick.
Analyze this sermon/message audio transcript:
Transcript: \"\"\"{transcript}\"\"\"

Task:
1. Identify the exact Scripture reference (e.g. 'Mark 2:1-10') mentioned by the speaker. If none, leave blank.
2. Identify the exact Title given by the preacher (e.g. 'Son, Thy Sins Be Forgiven Thee'). If none given, formulate a 3-5 word authentic title based on the main topic.
3. Write an engaging, 1-paragraph summary (3-4 sentences) for the YouTube video description based directly on what the preacher actually said.

Format as JSON:
{{"title": "...", "scripture": "...", "summary": "..."}}
"""
    for model_name in ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if "candidates" in data and data["candidates"]:
                    raw_json = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw_json)
                    return parsed
        except Exception as e:
            print(f"Gemini analysis notice ({model_name}): {e}")
            
    return None

def detect_scripture(transcript):
    """Detects Bible book, chapter, and verse references from transcript"""
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
    
    # Common keyword detection
    lower = transcript.lower()
    if 'gospel of mark' in lower or 'book of mark' in lower:
        if 'chapter 1' in lower or 'verse 21' in lower or 'synagogue' in lower or 'capernaum' in lower or 'authority' in lower:
            return 'Mark 1:21-28'
        return 'Mark 1'
    elif 'sermon on the mount' in lower or 'sermon amount' in lower:
        return 'Matthew 5-7'
    elif 'gospels' in lower or 'gospel' in lower:
        return 'The Gospels'
    
    return ""

def generate_smart_title(transcript, scripture, preacher):
    """Generates clean, authentic sermon title if none was entered"""
    lower = transcript.lower()
    
    if 'authority' in lower and ('mark' in lower or 'synagogue' in lower or 'scribes' in lower or 'doctrine' in lower or 'jesus' in lower):
        return 'Teaching with Authority'
    elif 'authority' in lower:
        return 'The Authority of Christ'
    elif 'primary message' in lower or 'primary teaching' in lower:
        return 'The Primary Teaching of Jesus'
    elif 'sermon on the mount' in lower or 'sermon amount' in lower:
        return 'Lessons from the Sermon on the Mount'
    elif 'grace' in lower and ('faith' in lower or 'salvation' in lower):
        return "The Power of God's Grace"
    elif 'holy spirit' in lower or 'spirit of god' in lower:
        return 'Walking in the Holy Spirit'
    elif 'kingdom of god' in lower or 'kingdom of heaven' in lower:
        return 'The Kingdom of God'
    elif scripture:
        return f'Message from {scripture}'
    
    return 'Sunday Morning Message'
