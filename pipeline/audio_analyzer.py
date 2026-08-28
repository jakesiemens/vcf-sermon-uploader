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

def extract_audio_snippet(input_path, duration_seconds=80):
    """Extracts ~80s of audio as 16kHz mono WAV for fast speech recognition"""
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    out_wav = os.path.join(UPLOADS_DIR, f"{base_name}_snippet.wav")
    
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", "20",
        "-t", str(duration_seconds),
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        out_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_wav if os.path.exists(out_wav) else None

def transcribe_audio_snippet(wav_path):
    """Transcribes WAV snippet in fast 25-second chunks"""
    if not wav_path or not os.path.exists(wav_path):
        return ""
    recognizer = sr.Recognizer()
    full_text = []
    
    try:
        with sr.AudioFile(wav_path) as source:
            for i in range(3):
                try:
                    audio = recognizer.record(source, duration=25)
                    text = recognizer.recognize_google(audio)
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
    if 'sermon on the mount' in lower or 'sermon amount' in lower:
        return 'Matthew 5-7'
    elif 'gospels' in lower or 'gospel' in lower:
        return 'The Gospels'
    
    return ""

def generate_smart_title(transcript, scripture, preacher):
    """Generates clean, authentic sermon title if none was entered"""
    lower = transcript.lower()
    
    if 'primary message' in lower or 'primary teaching' in lower:
        return 'The Primary Teaching of Jesus'
    elif 'sermon on the mount' in lower or 'sermon amount' in lower:
        return 'Lessons from the Sermon on the Mount'
    elif 'story of jesus' in lower:
        return 'The Living Story of Jesus Christ'
    elif scripture:
        return f'Message from {scripture}'
    
    # Fallback to key words
    words = [w.capitalize() for w in transcript.split() if len(w) > 4 and w.lower() not in ['going', 'would', 'things', 'there', 'start', 'guess', 'right']]
    if len(words) >= 3:
        return f'Walking in Truth: {" ".join(words[:2])}'
    
    return 'Sunday Morning Message'
