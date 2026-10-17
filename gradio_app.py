import os
import re
import uuid
import time
import shutil
from datetime import datetime
import gradio as gr

from config import (
    UPLOADS_DIR, OUTPUT_DIR, PREACHERS,
    GEMINI_API_KEY, OFFICIAL_PLAYLIST_ID
)
from pipeline.audio_analyzer import analyze_sermon_audio_multimodal
from pipeline.video_maker import render_sermon_backdrop, build_video_from_audio
from pipeline.youtube_uploader import upload_sermon_to_youtube, get_youtube_service
from pipeline.site_sync import sync_new_sermon_to_website

def clean_and_polish_title(raw_title):
    if not raw_title:
        return ""
    t = raw_title.strip()
    words = t.split()
    if words and len(words) > 1 and all(w.islower() for w in words):
        minor_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'from', 'by', 'in', 'of'}
        polished = []
        for i, w in enumerate(words):
            if i == 0 or i == len(words) - 1 or w.lower() not in minor_words:
                polished.append(w.capitalize())
            else:
                polished.append(w.lower())
        t = ' '.join(polished)
    return t

def clean_and_polish_scripture(raw_scripture):
    if not raw_scripture:
        return ""
    s = raw_scripture.strip().replace(';', ':').replace(',', ':')
    s = ' '.join(s.split())
    m = re.match(r'^([0-9]?\s*[A-Za-z]+)\s+([0-9]{1,3})\s+([0-9]{1,3}(?:\s*[-–]\s*[0-9]{1,3})?)$', s)
    if m:
        book, chap, v = m.groups()
        return f"{book.title()} {chap}:{v.replace(' ', '')}"
    return s.title()

def get_most_recent_sunday():
    d = datetime.now()
    offset = (d.weekday() + 1) % 7
    sun = d.replace(hour=12, minute=0, second=0, microsecond=0)
    import datetime as dt_module
    sun = sun - dt_module.timedelta(days=offset)
    return sun.strftime("%Y-%m-%d")

THEME_CHOICES = [
    ("Automatic (AI matches sermon topic)", "AUTO"),
    ("Holy Spirit / Pentecost", "HOLY_SPIRIT"),
    ("Peaceful Waters / Shepherd (Psalm 23)", "PEACE_SHEPHERD"),
    ("Mountain of Faith & Endurance", "FAITH_MOUNTAIN"),
    ("Cross & Grace (Romans / Redemption)", "CROSS_GRACE"),
    ("Bible Study & Word of God", "WORD_TEACHING"),
    ("Peace in the Storm / Deliverance", "STORM_DELIVERANCE"),
    ("Williamsburg Community Fellowship", "LOCAL_FELLOWSHIP"),
    ("Classic Deep Navy Slate", "CLASSIC_SLATE"),
]

def publish_sermon(audio_file, preacher, preached_date_str, custom_title, custom_scripture, custom_theme, privacy, progress=gr.Progress(track_tqdm=True)):
    if not audio_file:
        raise gr.Error("Please select an audio file to publish.")

    progress(0.05, desc="Checking YouTube authorization...")
    try:
        yt = get_youtube_service()
    except Exception as e:
        raise gr.Error(f"YouTube Authorization Error: {str(e)}. Please check your credentials or re-auth.")

    progress(0.10, desc="Saving audio file...")
    job_id = uuid.uuid4().hex[:8]
    original_name = os.path.basename(audio_file)
    audio_path = os.path.join(UPLOADS_DIR, f"{datetime.now().strftime('%Y%m%d')}_{job_id}_{original_name}")
    shutil.copy2(audio_file, audio_path)

    try:
        dt = datetime.strptime(preached_date_str.strip(), "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y")
        preached_date_iso = dt.strftime("%Y-%m-%d")
    except Exception:
        dt = datetime.now()
        display_date = dt.strftime("%B %d, %Y")
        preached_date_iso = dt.strftime("%Y-%m-%d")

    progress(0.20, desc="Gemini AI listening to audio & analyzing sermon...")
    title = clean_and_polish_title(custom_title)
    scripture = clean_and_polish_scripture(custom_scripture)
    ai_details = analyze_sermon_audio_multimodal(audio_path, preacher=preacher)

    if ai_details:
        if not title and ai_details.get("title"):
            title = clean_and_polish_title(ai_details["title"])
        if not scripture and ai_details.get("scripture"):
            scripture = clean_and_polish_scripture(ai_details["scripture"])

    if not title:
        title = f"Sunday Message - {display_date}"

    ai_theme = ai_details.get("visual_theme", "WORD_TEACHING") if ai_details else "WORD_TEACHING"
    theme_to_use = custom_theme if (custom_theme and custom_theme != "AUTO") else ai_theme
    subtitle = ai_details.get("subtitle", "") if ai_details else ""

    progress(0.50, desc=f"Rendering 3D golden typography backdrop ({theme_to_use})...")
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    backdrop_path = os.path.join(OUTPUT_DIR, f"{base_name}_backdrop.jpg")
    video_path = os.path.join(OUTPUT_DIR, f"{base_name}_1080p.mp4")

    render_sermon_backdrop(
        title=title,
        preacher=preacher,
        date_str=display_date,
        out_image_path=backdrop_path,
        scripture=scripture,
        visual_theme=theme_to_use,
        subtitle=subtitle
    )

    progress(0.65, desc="Encoding 1080p video with FFmpeg...")
    success_video = build_video_from_audio(audio_path, backdrop_path, video_path)
    if not success_video:
        raise gr.Error("FFmpeg failed to render 1080p video file.")

    progress(0.80, desc="Uploading video & thumbnail to YouTube...")
    desc_lines = []
    if ai_details and ai_details.get("summary"):
        desc_lines.append(ai_details["summary"].strip())
        desc_lines.append("")
    if scripture:
        desc_lines.append(f"Scripture: {scripture}")
    desc_lines.append(f"Speaker: {preacher}")
    desc_lines.append(f"Date: {display_date}")
    desc_lines.append("Victory Christian Fellowship")
    desc_lines.append("https://victorychristianfellowship.ca")
    if ai_details and ai_details.get("timestamps"):
        desc_lines.append("")
        desc_lines.append("Message Outline:")
        desc_lines.append(ai_details["timestamps"].strip())

    description = "\n".join(desc_lines)

    yt_result = upload_sermon_to_youtube(
        video_path,
        title,
        description,
        privacy=privacy,
        playlist_id=OFFICIAL_PLAYLIST_ID,
        thumbnail_path=backdrop_path
    )

    video_id = yt_result.get("video_id")
    youtube_url = yt_result.get("youtube_url")

    progress(0.95, desc="Syncing sermon to church website archive...")
    sync_new_sermon_to_website(
        video_id=video_id,
        title=title,
        preacher=preacher,
        preached_date_iso=preached_date_iso,
        display_date=display_date,
        scripture=scripture
    )

    progress(1.0, desc="Publishing Complete!")
    summary_md = f"""
### 🎉 Sermon Published Successfully!
* **Title:** {title}
* **Speaker:** {preacher}
* **Scripture:** {scripture or "None provided"}
* **Date Preached:** {display_date}
* **YouTube Video:** [Watch on YouTube]({youtube_url})
* **Church Website:** [View Archive](https://victorychristianfellowship.ca)
"""
    return summary_md, backdrop_path, youtube_url

# Gradio UI Layout
custom_theme = gr.themes.Soft(
    primary_hue="orange",
    neutral_hue="slate"
)

with gr.Blocks(title="VCF Sermon Publisher") as demo:
    gr.Markdown("""
    # 🎙️ Victory Christian Fellowship
    ### Automated Sermon Publishing Portal
    Upload an audio recording to automatically analyze the message, generate 1080p artwork, upload to YouTube, and update the church website.
    """)

    with gr.Row():
        with gr.Column(scale=5):
            audio_in = gr.Audio(
                sources=["upload"],
                type="filepath",
                label="Step 1: Choose Audio File (MP3, M4A, WAV, etc.)"
            )

            with gr.Row():
                preacher_in = gr.Dropdown(
                    choices=PREACHERS,
                    value=PREACHERS[0] if PREACHERS else "Jake Siemens",
                    label="Preacher"
                )
                date_in = gr.Textbox(
                    value=get_most_recent_sunday(),
                    label="Date Preached (YYYY-MM-DD)"
                )

            with gr.Row():
                title_in = gr.Textbox(
                    label="Sermon Title",
                    placeholder="Leave blank to let AI detect title"
                )
                scripture_in = gr.Textbox(
                    label="Scripture Passage",
                    placeholder="e.g. Romans 8:1-11 (Optional - AI detects)"
                )

            with gr.Row():
                theme_in = gr.Dropdown(
                    choices=THEME_CHOICES,
                    value="AUTO",
                    label="Thumbnail & Video Artwork"
                )
                privacy_in = gr.Dropdown(
                    choices=[("Public (Visible to everyone)", "public"), ("Unlisted (Review link first)", "unlisted"), ("Private", "private")],
                    value="public",
                    label="YouTube Privacy"
                )

            publish_btn = gr.Button("🚀 Process & Publish Sermon", variant="primary", size="lg")

        with gr.Column(scale=4):
            status_out = gr.Markdown("### Publishing Status\nUpload an audio file on the left and click **Process & Publish**.")
            preview_img = gr.Image(label="Rendered Artwork Preview", type="filepath")
            yt_btn = gr.Button("▶️ Open Published Video on YouTube", variant="secondary", visible=False)

    def on_publish_complete(result_md, img_path, yt_url):
        return (
            result_md,
            img_path,
            gr.update(visible=bool(yt_url), link=yt_url) if yt_url else gr.update(visible=False)
        )

    publish_btn.click(
        fn=publish_sermon,
        inputs=[audio_in, preacher_in, date_in, title_in, scripture_in, theme_in, privacy_in],
        outputs=[status_out, preview_img, yt_btn]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, theme=custom_theme)
