import os
import re
import time
import requests
import urllib.parse
from PIL import Image
from config import GEMINI_API_KEY, OUTPUT_DIR
from pipeline.video_maker import render_sermon_backdrop, resolve_backdrop_image

THEME_PROMPTS = {
    "CROSS_GRACE": "majestic wooden cross silhouette on a tranquil hill at golden hour sunrise, divine heavenly rays breaking through warm clouds, cinematic lighting, 8k, photorealistic masterpiece, no text",
    "WORD_TEACHING": "ancient open Holy Bible on rustic wooden table with radiant golden heavenly light streaming through sanctuary stained glass, cinematic, 8k, photorealistic masterpiece, no text",
    "FAITH_MOUNTAIN": "majestic rugged mountain summit at sunrise with radiant golden sunlight breaking through morning clouds, cinematic landscape, 8k, photorealistic masterpiece, no text",
    "PEACE_SHEPHERD": "peaceful green pastures by still calm waters with rolling hills and warm golden morning sunlight, tranquil biblical scenery, 8k, photorealistic masterpiece, no text",
    "STORM_DELIVERANCE": "dramatic stormy sea waves with golden beam of divine heavenly light breaking through dark storm clouds onto calm waters, cinematic, 8k, photorealistic masterpiece, no text",
    "HOLY_SPIRIT": "ethereal radiant golden light and gentle mist descending from heaven into tranquil valley at dawn, sacred atmosphere, 8k, photorealistic masterpiece, no text",
    "LOCAL_FELLOWSHIP": "warm sunlit peaceful country chapel sanctuary with golden morning light shining through windows, tranquil sacred atmosphere, 8k, photorealistic masterpiece, no text"
}

def create_thematic_prompt(title, scripture="", visual_theme="WORD_TEACHING", summary=""):
    """
    Uses Gemini (if available) to craft a customized, bespoke prompt matching the sermon topic.
    Falls back to curated high-impact Christian themes.
    """
    theme_key = (visual_theme or "WORD_TEACHING").strip().upper()
    default_prompt = THEME_PROMPTS.get(theme_key, THEME_PROMPTS["WORD_TEACHING"])

    if not GEMINI_API_KEY:
        return default_prompt

    try:
        p_text = f"""Given sermon title: "{title}", scripture: "{scripture}", theme: "{theme_key}".
Write a single concise text-to-image prompt (30-40 words) for a cinematic, photorealistic Christian sermon background.
Describe atmospheric landscape, divine heavenly light rays, ancient biblical scenery, open scriptures, or serene nature matching this topic.
Strict negative rules: NO humans with distorted faces, NO text, NO typography, NO words, NO letters.
Return ONLY the raw prompt text, nothing else."""

        for model in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.7-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                res = requests.post(url, json={"contents": [{"parts": [{"text": p_text}]}]}, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    if "candidates" in data and data["candidates"]:
                        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        text = re.sub(r'^["\']|["\']$', '', text).strip()
                        if text:
                            return f"{text}, cinematic lighting, 8k, photorealistic masterpiece, no text"
            except Exception as e:
                print(f"[ImageGenerator] Prompt gen with {model} failed: {e}")
                continue
    except Exception as e:
        print(f"[ImageGenerator] AI prompt generation error: {e}")

    return default_prompt

def fetch_ai_image(prompt, out_path, max_retries=2):
    """
    Fetches AI-generated 16:9 image from Pollinations.ai.
    Crops any watermark from the bottom edge and upscales cleanly to 1920x1080.
    Handles rate-limiting gracefully.
    """
    encoded = urllib.parse.quote(prompt.strip())
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=576&nologo=true"

    for attempt in range(max_retries):
        try:
            print(f"[ImageGenerator] Requesting AI image (attempt {attempt + 1}/{max_retries})...", flush=True)
            r = requests.get(url, timeout=35)

            if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
                raw_path = out_path + ".raw.jpg"
                dir_name = os.path.dirname(os.path.abspath(out_path))
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

                with open(raw_path, 'wb') as f:
                    f.write(r.content)

                # Open with PIL, crop bottom 36px (removes any watermark), scale to 1920x1080
                with Image.open(raw_path) as im:
                    w, h = im.size
                    cropped = im.crop((0, 0, w, max(h - 36, 100)))
                    upscaled = cropped.resize((1920, 1080), Image.Resampling.LANCZOS)
                    upscaled.save(out_path, "JPEG", quality=95)

                if os.path.exists(raw_path):
                    try:
                        os.remove(raw_path)
                    except:
                        pass

                print(f"[ImageGenerator] AI image generated and saved to {out_path} (1920x1080)")
                return out_path

            elif r.status_code == 402:
                print(f"[ImageGenerator] Rate limited by Pollinations (402): {r.text[:100]}")
                wait_match = re.search(r'Retry after (\d+)s', r.text)
                wait_sec = int(wait_match.group(1)) if wait_match else 20
                if attempt < max_retries - 1 and wait_sec <= 25:
                    print(f"[ImageGenerator] Waiting {wait_sec + 2}s before retry...")
                    time.sleep(wait_sec + 2)
                    continue
                else:
                    break
            else:
                print(f"[ImageGenerator] Pollinations returned {r.status_code}: {r.text[:100]}")
                break

        except requests.exceptions.Timeout:
            print("[ImageGenerator] Request timed out.")
            break
        except Exception as e:
            print(f"[ImageGenerator] Generation error: {e}")
            break

    return None

def generate_sermon_artwork(title, preacher, display_date, scripture="", visual_theme="WORD_TEACHING", subtitle="", out_path=None, custom_image_path=None, sermon_summary=""):
    """
    Creates complete sermon thumbnail and video backdrop.
    1. If user provided a custom image, uses that.
    2. Otherwise, crafts an AI prompt matching sermon topic, generates an AI background,
       crops any watermarks, and upscales to 1920x1080.
    3. If generation fails or times out, gracefully falls back to the curated thematic backdrop.
    4. Renders 3D embossed golden typography, speaker name, scripture, and vignette.
    """
    if not out_path:
        raise ValueError("out_path is required")

    bg_path = None

    # Option A: User uploaded custom graphic
    if custom_image_path and os.path.exists(custom_image_path):
        bg_path = custom_image_path

    # Option B: Dynamic AI Generation
    if not bg_path:
        try:
            prompt = create_thematic_prompt(title=title, scripture=scripture, visual_theme=visual_theme, summary=sermon_summary)
            print(f"[ImageGenerator] Dynamic AI Prompt: {prompt}")
            ai_bg_target = os.path.join(os.path.dirname(os.path.abspath(out_path)), f"ai_bg_{int(time.time())}.jpg")
            bg_path = fetch_ai_image(prompt, ai_bg_target)
        except Exception as e:
            print(f"[ImageGenerator] Error during dynamic AI generation: {e}")
            bg_path = None

    # Option C: Curated Thematic Fallback (always gorgeous, never casual phone photos)
    if not bg_path or not os.path.exists(bg_path):
        print(f"[ImageGenerator] Using curated premium backdrop for theme: {visual_theme}")
        bg_path = resolve_backdrop_image(visual_theme=visual_theme)

    # Render with embossed golden typography & scrim
    return render_sermon_backdrop(
        title=title,
        preacher=preacher,
        date_str=display_date,
        out_image_path=out_path,
        scripture=scripture,
        visual_theme=visual_theme,
        custom_bg_path=bg_path,
        subtitle=subtitle
    )
