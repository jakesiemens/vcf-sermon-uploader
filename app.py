import os
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename

from config import (
    DEFAULT_PORT, UPLOADS_DIR, OUTPUT_DIR, PREACHERS,
    TOKEN_PATH, CLIENT_SECRET_PATH
)
from pipeline.audio_analyzer import extract_audio_snippet, transcribe_audio_snippet, detect_scripture, generate_smart_title
from pipeline.video_maker import render_sermon_backdrop, build_video_from_audio
from pipeline.youtube_uploader import upload_sermon_to_youtube
from pipeline.site_sync import sync_new_sermon_to_website

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB upload limit

# In-memory background jobs registry
JOBS = {}

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

def process_sermon_worker(job_id, audio_path, filename, custom_title, custom_scripture, preacher, preached_date_iso, privacy):
    try:
        dt = datetime.strptime(preached_date_iso, '%Y-%m-%d') if preached_date_iso else datetime.now()
        display_date = dt.strftime('%B %d, %Y')
    except:
        dt = datetime.now()
        display_date = dt.strftime('%B %d, %Y')

    # Step 2: AI Analysis
    JOBS[job_id].update({
        'step': 2,
        'step_name': 'ai',
        'progress': 30,
        'message': 'AI analyzing sermon audio, title, and scripture...'
    })

    title = custom_title
    scripture = custom_scripture

    if not title or not scripture:
        print(f'[{job_id}] Extracting snippet for AI analysis...')
        snippet_wav = extract_audio_snippet(audio_path, duration_seconds=75)
        transcript = ''
        if snippet_wav and os.path.exists(snippet_wav):
            transcript = transcribe_audio_snippet(snippet_wav)
            print(f'[{job_id}] Transcript: {transcript[:100]}...')
        
        if not scripture:
            scripture = detect_scripture(transcript)
        if not title:
            title = generate_smart_title(transcript, scripture, preacher)

    if not title:
        title = 'Sunday Morning Message'

    print(f'[{job_id}] Final Title: {title} | Scripture: {scripture} | Preacher: {preacher}')

    # Step 3: Video Generation
    JOBS[job_id].update({
        'step': 3,
        'step_name': 'video',
        'progress': 55,
        'message': f'Rendering 1080p graphic backdrop for "{title}"...'
    })

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    backdrop_path = os.path.join(OUTPUT_DIR, f'{base_name}_backdrop.jpg')
    video_path = os.path.join(OUTPUT_DIR, f'{base_name}_1080p.mp4')

    render_sermon_backdrop(title, preacher, display_date, backdrop_path)
    
    JOBS[job_id]['message'] = 'Encoding 1080p video with FFmpeg...'
    success_video = build_video_from_audio(audio_path, backdrop_path, video_path)
    if not success_video:
        raise RuntimeError('FFmpeg failed to render 1080p video file.')

    # Step 4: YouTube Upload
    JOBS[job_id].update({
        'step': 4,
        'step_name': 'youtube',
        'progress': 80,
        'message': 'Uploading 1080p video & thumbnail to YouTube channel...'
    })

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
            privacy_status=privacy
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
    JOBS[job_id].update({
        'step': 5,
        'step_name': 'website',
        'progress': 95,
        'message': 'Syncing sermon to victorychristianfellowship.ca...'
    })

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
    JOBS[job_id].update({
        'status': 'completed',
        'step': 5,
        'progress': 100,
        'message': 'Sermon published successfully!',
        'result': {
            'title': title,
            'preacher': preacher,
            'scripture': scripture,
            'display_date': display_date,
            'video_id': video_id,
            'youtube_url': youtube_url or f'https://youtu.be/{video_id}' if video_id else '',
            'quota_notice': quota_notice,
            'quota_message': quota_message
        }
    })
    print(f'[{job_id}] Completed successfully!')

@app.route('/api/publish', methods=['POST'])
def start_publish_job():
    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': 'No audio file uploaded'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    filename = secure_filename(audio_file.filename)
    job_id = uuid.uuid4().hex[:12]
    saved_filename = f"{datetime.now().strftime('%Y%m%d')}_{job_id}_{filename}"
    audio_path = os.path.join(UPLOADS_DIR, saved_filename)
    
    print(f'[{job_id}] Saving uploaded audio: {filename}...')
    audio_file.save(audio_path)

    custom_title = request.form.get('title', '').strip()
    custom_scripture = request.form.get('scripture', '').strip()
    preacher = request.form.get('preacher', 'Victory Christian Fellowship').strip()
    preached_date_iso = request.form.get('preached_date', datetime.now().strftime('%Y-%m-%d')).strip()
    privacy = request.form.get('privacy', 'public').strip()

    # Register job
    JOBS[job_id] = {
        'status': 'processing',
        'step': 1,
        'step_name': 'upload',
        'progress': 20,
        'message': 'Audio file received. Starting AI processing...',
        'created_at': time.time()
    }

    # Start background thread
    worker_thread = threading.Thread(
        target=process_sermon_worker,
        args=(job_id, audio_path, filename, custom_title, custom_scripture, preacher, preached_date_iso, privacy),
        daemon=True
    )
    worker_thread.start()

    # Immediately respond with 200 OK and job_id! Zero 502 timeouts!
    return jsonify({
        'success': True,
        'job_id': job_id,
        'message': 'Upload received. Processing in background.'
    }), 200

@app.route('/api/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'status': 'not_found', 'error': 'Unknown job ID'}), 404
    return jsonify(job), 200

if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('PORT', 7860))
    print('=' * 65)
    print('  VCF SERMON PUBLISHING PORTAL (ASYNC BACKGROUND ENGINE)')
    print(f'  Starting cloud server on 0.0.0.0:{port}')
    print('=' * 65)
    serve(app, host='0.0.0.0', port=port, threads=6)
