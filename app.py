import os
import re
import json
import uuid
import threading
import time
import traceback
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename

from config import (
    DEFAULT_PORT, UPLOADS_DIR, OUTPUT_DIR, PREACHERS,
    TOKEN_PATH, CLIENT_SECRET_PATH, GEMINI_API_KEY
)
from pipeline.audio_analyzer import (
    extract_audio_snippet, transcribe_audio_snippet,
    detect_scripture, generate_smart_title, analyze_transcript_with_gemini,
    analyze_sermon_audio_multimodal
)
from pipeline.image_generator import generate_sermon_artwork
from pipeline.video_maker import render_sermon_backdrop, build_video_from_audio
from pipeline.youtube_uploader import upload_sermon_to_youtube
from pipeline.site_sync import sync_new_sermon_to_website

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB upload limit

ALLOWED_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.aac', '.flac', '.ogg', '.wma'}

# Persistent background jobs registry
JOBS_FILE = os.path.join(OUTPUT_DIR, "jobs_store.json")
JOBS_LOCK = threading.Lock()
JOBS = {}

def load_jobs():
    """Loads existing jobs from persistent JSON storage into memory"""
    global JOBS
    with JOBS_LOCK:
        if os.path.exists(JOBS_FILE):
            try:
                with open(JOBS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        JOBS = data
            except Exception as e:
                print(f"Warning: Could not load jobs from {JOBS_FILE}: {e}")
                JOBS = {}
        else:
            JOBS = {}

def save_jobs():
    """Atomically persists jobs to disk using a temporary file and replace"""
    with JOBS_LOCK:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            temp_file = JOBS_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(JOBS, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, JOBS_FILE)
        except Exception as e:
            print(f"Warning: Could not save jobs to {JOBS_FILE}: {e}")

def update_job(job_id, **kwargs):
    """Thread-safe update and persistence of a background job"""
    with JOBS_LOCK:
        if job_id not in JOBS:
            JOBS[job_id] = {}
        JOBS[job_id]["job_id"] = job_id
        for k, v in kwargs.items():
            JOBS[job_id][k] = v
        JOBS[job_id]["updated_at"] = time.time()
    save_jobs()

# Initialize jobs from disk on startup
load_jobs()

@app.route('/')
def index():
    today = datetime.now()
    days_since_sunday = (today.weekday() + 1) % 7
    default_date = (today if days_since_sunday == 0 else today).strftime('%Y-%m-%d')
    return render_template('index.html', preachers=PREACHERS, default_date=default_date)

@app.route('/health')
@app.route('/healthz')
def health():
    return jsonify({'status': 'healthy', 'time': datetime.now().isoformat()}), 200

@app.route('/api/jobs')
def list_jobs():
    with JOBS_LOCK:
        return jsonify(JOBS), 200

@app.route('/api/debug')
def debug_info():
    ffmpeg_log = ""
    log_p = os.path.join(OUTPUT_DIR, "ffmpeg.log")
    if os.path.exists(log_p):
        try:
            with open(log_p, "r") as f:
                ffmpeg_log = f.read()[-1000:]
        except:
            pass
    with JOBS_LOCK:
        jobs_copy = dict(JOBS)
    return jsonify({
        "jobs": jobs_copy,
        "ffmpeg_log": ffmpeg_log
    }), 200

def clean_and_polish_title(raw_title):
    """Cleans up volunteer typos, casing, file extensions, and punctuation"""
    if not raw_title:
        return ""
    t = raw_title.strip()
    for ext in ['.mp3', '.m4a', '.wav', '.aac', '.flac', '.ogg', '.wma']:
        if t.lower().endswith(ext):
            t = t[:-len(ext)].strip()
            
    t = t.replace('_', ' ')
    t = ' '.join(t.split())
    
    typo_map = {
        r'\bchrsitian\b': 'Christian',
        r'\bchristain\b': 'Christian',
        r'\bgospal\b': 'Gospel',
        r'\bgosple\b': 'Gospel',
        r'\bfellowhip\b': 'Fellowship',
        r'\bfellowshp\b': 'Fellowship',
        r'\bauthorty\b': 'Authority',
        r'\bauthoriy\b': 'Authority',
        r'\bmesage\b': 'Message',
        r'\bmessge\b': 'Message',
        r'\bscriptur\b': 'Scripture',
        r'\bressurection\b': 'Resurrection'
    }
    for pat, repl in typo_map.items():
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
        
    minor_words = {'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'nor', 'of', 'on', 'or', 'so', 'the', 'to', 'up', 'yet', 'with'}
    words = t.split()
    if words:
        polished = []
        for i, w in enumerate(words):
            lower_w = w.lower()
            if i == 0 or i == len(words) - 1 or lower_w not in minor_words:
                polished.append(w.capitalize() if w.islower() or w.isupper() else w)
            else:
                polished.append(lower_w)
        t = ' '.join(polished)
        
    return t

def clean_and_polish_scripture(raw_scripture):
    """Standardizes volunteer scripture formatting (e.g. rom 8 1 11 -> Romans 8:1-11)"""
    if not raw_scripture:
        return ""
    s = raw_scripture.strip()
    s = s.replace(';', ':').replace(',', ':')
    s = ' '.join(s.split())
    m = re.match(r'^([0-9]?\s*[A-Za-z]+)\s+([0-9]{1,3})\s+([0-9]{1,3}(?:\s*[-–]\s*[0-9]{1,3})?)$', s)
    if m:
        book, chap, v = m.groups()
        return f"{book.title()} {chap}:{v.replace(' ', '')}"
    return s.title()

def process_sermon_worker(job_id, audio_path, filename, custom_title, custom_scripture, preacher, preached_date_iso, privacy, custom_theme=None, custom_bg_path=None):
    try:
        try:
            dt = datetime.strptime(preached_date_iso, '%Y-%m-%d') if preached_date_iso else datetime.now()
            display_date = dt.strftime('%B %d, %Y')
        except Exception:
            dt = datetime.now()
            display_date = dt.strftime('%B %d, %Y')

        # Step 2: Multimodal AI Audio Analysis
        update_job(job_id,
            step=2,
            step_name='ai',
            progress=30,
            message='AI listening to full sermon audio, extracting title, scripture, & chapters...'
        )

        title = clean_and_polish_title(custom_title)
        scripture = clean_and_polish_scripture(custom_scripture)
        transcript = ''
        ai_details = None

        print(f'[{job_id}] Running multimodal sermon analysis with Gemini...')
        ai_details = analyze_sermon_audio_multimodal(audio_path, preacher=preacher)

        if ai_details:
            if not title and ai_details.get('title'):
                title = clean_and_polish_title(ai_details['title'])
            if not scripture and ai_details.get('scripture'):
                scripture = clean_and_polish_scripture(ai_details['scripture'])

        if not title:
            if scripture:
                title = f'Message from {scripture}'
            elif display_date:
                title = f'Sunday Message - {display_date}'
            else:
                title = 'Sunday Morning Message'

        print(f'[{job_id}] Final Title: "{title}" | Scripture: "{scripture}" | Preacher: "{preacher}"')

        # Determine visual theme: user override or AI detected
        ai_theme = ai_details.get('visual_theme', 'WORD_TEACHING') if ai_details else 'WORD_TEACHING'
        theme_to_use = custom_theme if (custom_theme and custom_theme != 'AUTO') else ai_theme
        subtitle = ai_details.get('subtitle', '') if ai_details else ''

        # Step 3: Video Generation (Fast 1fps)
        update_job(job_id,
            step=3,
            step_name='video',
            progress=55,
            message=f'Generating custom AI artwork for "{title}" ({theme_to_use})...'
        )

        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        backdrop_path = os.path.join(OUTPUT_DIR, f'{base_name}_backdrop.jpg')
        video_path = os.path.join(OUTPUT_DIR, f'{base_name}_1080p.mp4')
        sermon_summary = ai_details.get('one_sentence_summary', '') if ai_details else ''

        generate_sermon_artwork(
            title=title,
            preacher=preacher,
            display_date=display_date,
            scripture=scripture,
            visual_theme=theme_to_use,
            subtitle=subtitle,
            out_path=backdrop_path,
            custom_image_path=custom_bg_path,
            sermon_summary=sermon_summary
        )
        
        update_job(job_id, message='Encoding 1080p video with FFmpeg...')
        success_video = build_video_from_audio(audio_path, backdrop_path, video_path)
        if not success_video:
            raise RuntimeError('FFmpeg failed to render 1080p video file.')

        # Step 4: YouTube Upload
        update_job(job_id,
            step=4,
            step_name='youtube',
            progress=80,
            message='Uploading 1080p video & thumbnail to YouTube channel...'
        )

        video_id = None
        youtube_url = None
        quota_notice = False
        quota_message = ''

        try:
            yt_res = upload_sermon_to_youtube(
                video_path=video_path,
                thumbnail_path=backdrop_path,
                title=title,
                preacher=preacher,
                display_date=display_date,
                scripture=scripture,
                privacy_status=privacy,
                transcript=transcript,
                ai_details=ai_details
            )
            video_id = yt_res['video_id']
            youtube_url = yt_res['url']
        except Exception as e:
            err_msg = str(e)
            if 'quotaExceeded' in err_msg or 'quota' in err_msg.lower():
                quota_notice = True
                quota_message = 'Video rendered successfully! YouTube daily upload quota will reset at 4:00 AM ADT, at which point the video will complete uploading automatically.'
                print(f'[{job_id}] YouTube quota reached. Video saved in output.')
            else:
                raise RuntimeError(f'YouTube API upload failed: {err_msg}')

        # Step 5: Website Sync
        update_job(job_id,
            step=5,
            step_name='website',
            progress=95,
            message='Syncing sermon to victorychristianfellowship.ca...'
        )

        if video_id:
            try:
                sync_new_sermon_to_website(
                    video_id=video_id,
                    title=title,
                    preacher=preacher,
                    preached_date_iso=preached_date_iso,
                    display_date=display_date,
                    scripture=scripture
                )
            except Exception as e:
                print(f'[{job_id}] Website sync notice: {e}')

        # Completed
        update_job(job_id,
            status='completed',
            step=5,
            progress=100,
            message='Sermon published successfully!',
            result={
                'title': title,
                'preacher': preacher,
                'scripture': scripture,
                'display_date': display_date,
                'video_id': video_id,
                'youtube_url': youtube_url or (f'https://youtu.be/{video_id}' if video_id else ''),
                'quota_notice': quota_notice,
                'quota_message': quota_message
            }
        )
        print(f'[{job_id}] Completed successfully!')

    except Exception as e:
        err_detail = traceback.format_exc()
        print(f'[{job_id}] FATAL WORKER ERROR: ' + err_detail)
        update_job(job_id,
            status='error',
            error=str(e),
            message=f'Error: {str(e)}'
        )

@app.route('/api/publish', methods=['POST'])
def start_publish_job():
    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': 'No audio file uploaded'}), 400

    audio_file = request.files['audio']
    if not audio_file or audio_file.filename == '':
        return jsonify({'success': False, 'error': 'Please select an audio file'}), 400

    filename = secure_filename(audio_file.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid audio filename'}), 400

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            'success': False,
            'error': f'Unsupported audio format "{ext}". Please choose MP3, M4A, WAV, AAC, FLAC, OGG, or WMA.'
        }), 400

    # Ensure non-empty file (0 bytes validation)
    audio_file.seek(0, os.SEEK_END)
    file_size = audio_file.tell()
    audio_file.seek(0)
    if file_size <= 0:
        return jsonify({'success': False, 'error': 'Uploaded audio file is empty (0 bytes).'}), 400

    custom_title = request.form.get('title', '').strip()
    custom_scripture = request.form.get('scripture', '').strip()
    preacher = request.form.get('preacher', 'Victory Christian Fellowship').strip()
    preached_date_iso = request.form.get('preached_date', datetime.now().strftime('%Y-%m-%d')).strip()
    privacy = request.form.get('privacy', 'public').strip()
    custom_theme = request.form.get('theme', 'AUTO').strip()

    # Preached date validation
    try:
        p_date = datetime.strptime(preached_date_iso, '%Y-%m-%d').date()
        if p_date > datetime.now().date():
            return jsonify({'success': False, 'error': 'The preached date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format (must be YYYY-MM-DD)'}), 400

    # Optional custom artwork upload
    custom_bg_path = None
    if 'custom_artwork' in request.files:
        art_file = request.files['custom_artwork']
        if art_file and art_file.filename != '':
            art_ext = os.path.splitext(art_file.filename)[1].lower()
            if art_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                art_name = f"{uuid.uuid4().hex[:8]}_art{art_ext}"
                custom_bg_path = os.path.join(UPLOADS_DIR, art_name)
                art_file.save(custom_bg_path)

    # Idempotency key handling to prevent duplicate jobs on network retry/double-submit
    idempotency_key = request.form.get('idempotency_key', '').strip()
    if not idempotency_key:
        idempotency_key = f"{filename}_{file_size}_{preached_date_iso}_{preacher}_{custom_theme}"

    with JOBS_LOCK:
        for existing_id, job in JOBS.items():
            if job.get('idempotency_key') == idempotency_key:
                status = job.get('status')
                created_at = job.get('created_at', 0)
                # If currently processing or completed in the last 4 hours
                if status == 'processing' or (status == 'completed' and (time.time() - created_at < 14400)):
                    print(f"[{existing_id}] Matched idempotency key '{idempotency_key}'. Returning existing job.")
                    return jsonify({
                        'success': True,
                        'job_id': existing_id,
                        'message': 'Job already in progress or completed. Resuming status.'
                    }), 200

    job_id = uuid.uuid4().hex[:12]
    saved_filename = f"{datetime.now().strftime('%Y%m%d')}_{job_id}_{filename}"
    audio_path = os.path.join(UPLOADS_DIR, saved_filename)
    temp_upload_path = os.path.join(UPLOADS_DIR, f"{saved_filename}.part")
    
    print(f'[{job_id}] Saving uploaded audio: {filename} ({file_size / 1048576:.1f} MB)...')
    try:
        audio_file.save(temp_upload_path)
        os.replace(temp_upload_path, audio_path)
    except Exception as e:
        if os.path.exists(temp_upload_path):
            try:
                os.remove(temp_upload_path)
            except:
                pass
        return jsonify({'success': False, 'error': f'Failed to store uploaded file: {str(e)}'}), 500

    # Register job in persistent storage
    update_job(job_id,
        idempotency_key=idempotency_key,
        status='processing',
        step=1,
        step_name='upload',
        progress=20,
        message='Audio file received. Starting AI processing...',
        created_at=time.time(),
        filename=filename,
        audio_path=audio_path,
        error=None,
        result=None
    )

    # Start background worker thread
    worker_thread = threading.Thread(
        target=process_sermon_worker,
        args=(job_id, audio_path, filename, custom_title, custom_scripture, preacher, preached_date_iso, privacy, custom_theme, custom_bg_path),
        daemon=True
    )
    worker_thread.start()

    return jsonify({
        'success': True,
        'job_id': job_id,
        'message': 'Upload received. Processing in background.'
    }), 200

@app.route('/api/health', methods=['GET'])
def health_check():
    """Validates system readiness including YouTube OAuth token status"""
    yt_ok = False
    yt_error = None
    try:
        from pipeline.youtube_uploader import get_youtube_service
        yt = get_youtube_service()
        yt_ok = True
    except Exception as e:
        yt_error = str(e)

    return jsonify({
        'status': 'ok' if yt_ok else 'warning',
        'youtube_auth': yt_ok,
        'youtube_error': yt_error,
        'gemini_configured': bool(GEMINI_API_KEY)
    }), 200

@app.route('/api/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        load_jobs()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
    if not job:
        return jsonify({'status': 'not_found', 'error': 'Unknown job ID'}), 404
    return jsonify(job), 200

try:
    from gradio_app import demo
except Exception as e:
    print(f"Notice: Gradio import: {e}")
    demo = None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7860))
    if (os.environ.get('SPACE_ID') or os.environ.get('GRADIO_MODE')) and demo:
        print('=' * 65)
        print('  VCF SERMON PUBLISHING PORTAL (HUGGING FACE CLOUD)')
        print(f'  Starting Gradio cloud app on 0.0.0.0:{port}')
        demo.launch(server_name='0.0.0.0', server_port=port, ssr_mode=False)
        while True:
            time.sleep(3600)
    else:
        from waitress import serve
        print('=' * 65)
        print('  VCF SERMON PUBLISHING PORTAL (LOCAL / WAITRESS ENGINE)')
        print(f'  Starting server on 0.0.0.0:{port}')
        print('=' * 65)
        serve(app, host='0.0.0.0', port=port, threads=6)

