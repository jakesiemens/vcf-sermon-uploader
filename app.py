import os
import sys
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

# Local config & pipeline modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PREACHERS, UPLOADS_DIR, OUTPUT_DIR, DEFAULT_PORT
from pipeline.audio_analyzer import extract_audio_snippet, transcribe_audio_snippet, detect_scripture, generate_smart_title
from pipeline.video_maker import render_sermon_backdrop, build_video_from_audio
from pipeline.youtube_uploader import upload_sermon_to_youtube
from pipeline.site_sync import sync_new_sermon_to_website

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max audio upload

def get_most_recent_sunday():
    today = datetime.now()
    # Sunday is 6 in Python weekday() (Monday=0 ... Sunday=6)
    days_to_subtract = (today.weekday() + 1) % 7
    recent_sunday = today - timedelta(days=days_to_subtract)
    return recent_sunday.strftime('%Y-%m-%d')

def format_display_date(iso_date_str):
    try:
        dt = datetime.strptime(iso_date_str, '%Y-%m-%d')
        return dt.strftime('%B %d, %Y').replace(' 0', ' ')
    except:
        return iso_date_str

@app.route('/')
def home():
    default_date = get_most_recent_sunday()
    return render_template('index.html', preachers=PREACHERS, default_date=default_date)

@app.route('/api/publish', methods=['POST'])
def publish_sermon():
    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': 'No audio file provided'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    # Save uploaded file
    orig_name = secure_filename(audio_file.filename)
    unique_id = uuid.uuid4().hex[:8]
    base_name = f"{datetime.now().strftime('%Y%m%d')}_{unique_id}_{orig_name}"
    audio_path = os.path.join(UPLOADS_DIR, base_name)
    audio_file.save(audio_path)

    # Form parameters
    preacher = request.form.get('preacher', '').strip()
    preached_date_iso = request.form.get('preached_date', '').strip() or get_most_recent_sunday()
    display_date = format_display_date(preached_date_iso)
    title = request.form.get('title', '').strip()
    scripture = request.form.get('scripture', '').strip()
    privacy = request.form.get('privacy', 'public').strip()

    # Step 1: AI Audio Analysis
    print(f"Analyzing audio: {audio_path}...")
    snippet_wav = extract_audio_snippet(audio_path, duration_seconds=180)
    transcript = transcribe_audio_snippet(snippet_wav) if snippet_wav else ""
    
    if not scripture:
        scripture = detect_scripture(transcript)
        print(f"AI detected scripture: {scripture}")

    if not title:
        title = generate_smart_title(transcript, scripture, preacher)
        print(f"AI generated title: {title}")

    # Step 2: Render Graphic Backdrop & Video
    backdrop_path = os.path.join(OUTPUT_DIR, f"{base_name}_backdrop.jpg")
    video_path = os.path.join(OUTPUT_DIR, f"{base_name}_1080p.mp4")

    print(f"Rendering 1080p graphic backdrop...")
    render_sermon_backdrop(title, preacher, display_date, backdrop_path)

    print(f"Encoding 1080p video with FFmpeg...")
    success_video = build_video_from_audio(audio_path, backdrop_path, video_path)
    if not success_video:
        return jsonify({'success': False, 'error': 'Failed to render video'}), 500

    # Step 3: YouTube Upload
    print(f"Uploading to YouTube channel...")
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
        if "quotaExceeded" in err_msg or "quota" in err_msg.lower():
            print("YouTube daily quota reached. Video generated and saved in output folder.")
            return jsonify({
                'success': True,
                'quota_notice': True,
                'title': title,
                'preacher': preacher,
                'scripture': scripture,
                'display_date': display_date,
                'message': '1080p Video rendered successfully! Google YouTube upload quota will reset tonight at 4:00 AM ADT, at which point the video will complete uploading automatically.'
            })
        return jsonify({'success': False, 'error': f'YouTube upload error: {err_msg}'}), 500

    # Step 4: Website Sync
    print(f"Syncing new sermon to victorychristianfellowship.ca...")
    sync_new_sermon_to_website(
        video_id=video_id,
        title=title,
        preacher=preacher,
        preached_date_iso=preached_date_iso,
        display_date=display_date,
        scripture=scripture
    )

    return jsonify({
        'success': True,
        'video_id': video_id,
        'youtube_url': youtube_url,
        'title': title,
        'preacher': preacher,
        'scripture': scripture,
        'display_date': display_date
    })

if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get("PORT", 7860))
    print(f"=" * 65)
    print(f"  VCF SERMON PUBLISHING PORTAL")
    print(f"  Starting cloud server on 0.0.0.0:{port}")
    print(f"=" * 65)
    serve(app, host='0.0.0.0', port=port, threads=6)
