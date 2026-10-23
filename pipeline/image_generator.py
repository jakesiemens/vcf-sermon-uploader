import os
import re
import time
import random
import shutil
import requests
import urllib.parse
from PIL import Image
from config import GEMINI_API_KEY, HF_TOKEN, OUTPUT_DIR
from pipeline.video_maker import render_sermon_backdrop, resolve_backdrop_image

# Pure evangelical, non-denominational outdoor/nature/biblical prompts (Strictly NO church interiors, cathedrals, stained glass, or altars)
THEME_PROMPTS = {
    "CROSS_GRACE": "majestic rough-hewn wooden cross standing on a tranquil grassy hill at golden hour sunrise, warm heavenly sunbeams breaking through glowing clouds over rolling hills, cinematic landscape photography, 8k, photorealistic masterpiece, no text",
    "WORD_TEACHING": "a single open leather-bound Holy Bible resting flat on a rustic weathered oak table outdoors overlooking a peaceful sunlit mountain meadow at golden hour, warm natural morning light illuminating the pages, shallow depth of field, 8k, photorealistic masterpiece, single book only, no stacked books, no text",
    "FAITH_MOUNTAIN": "majestic rugged mountain peak rising above a sea of morning mist at golden sunrise, radiant sunbeams piercing through dramatic clouds over pine forests, awe-inspiring creation landscape, 8k, photorealistic masterpiece, no text",
    "PEACE_SHEPHERD": "lush green pastures beside still crystal-clear reflective waters in a sunlit valley at dawn, gentle rolling hills and olive trees in warm golden morning light, Psalm 23 scenery, 8k, photorealistic masterpiece, no text",
    "STORM_DELIVERANCE": "dramatic ocean waves calming as a brilliant golden beam of sunlight breaks through dark storm clouds onto a peaceful horizon, cinematic coastal landscape, 8k, photorealistic masterpiece, no text",
    "HOLY_SPIRIT": "radiant golden sunbeams descending through morning mist into a tranquil evergreen forest valley beside a clear flowing river at sunrise, peaceful creation atmosphere, 8k, photorealistic masterpiece, no text",
    "LOCAL_FELLOWSHIP": "breathtaking golden hour sunrise over a peaceful New Brunswick river valley surrounded by vibrant autumn maples and evergreen pines, warm natural light reflecting on calm water, 8k, photorealistic masterpiece, no text"
}

FORBIDDEN_CHURCH_TERMS = re.compile(
    r"\b(cathedral|cathedrals|gothic|stained[\s-]?glass|pew|pews|altar|altars|chapel|sanctuary|church\s+interior|inside\s+of\s+a?\s*church|church\s+building|steeple|crucifix|liturgical|priest|monastery|abbey|crypt|cryptic|chandelier|candles|candelabra|organ\s+pipes|nave|vaulted\s+ceiling|stone\s+arches)\b",
    re.IGNORECASE
)

def sanitize_evangelical_prompt(prompt_text, fallback_theme="WORD_TEACHING"):
    """
    Guarantees that NO prompt ever requests old-fashioned, gothic, liturgical, or inside-of-church imagery.
    """
    if not prompt_text:
        return THEME_PROMPTS.get(fallback_theme, THEME_PROMPTS["WORD_TEACHING"])

    cleaned = FORBIDDEN_CHURCH_TERMS.sub("natural outdoor sunlight", prompt_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (
        f"{cleaned}, natural outdoor setting or serene creation scenery, "
        "warm golden hour cinematic lighting, ultra-detailed 8k photorealistic photography, "
        "no buildings, no church interiors, no stained glass, no people, no text, no words, no letters"
    )

def create_thematic_prompt(title, scripture="", visual_theme="WORD_TEACHING", summary="", ai_image_prompt=""):
    """
    Uses Gemini (or the multimodal audio analyzer's custom image_prompt) to craft a bespoke
    photorealistic background scene that directly matches the sermon's message and topic.
    Strictly forbids old-fashioned/cryptic church interiors.
    """
    theme_key = (visual_theme or "WORD_TEACHING").strip().upper()
    default_prompt = THEME_PROMPTS.get(theme_key, THEME_PROMPTS["WORD_TEACHING"])

    if ai_image_prompt and len(ai_image_prompt.strip()) > 20:
        return sanitize_evangelical_prompt(ai_image_prompt.strip(), fallback_theme=theme_key)

    if not GEMINI_API_KEY:
        return sanitize_evangelical_prompt(default_prompt, fallback_theme=theme_key)

    try:
        p_text = f"""You are designing a high-resolution 16:9 background photograph for an evangelical, non-denominational Christian sermon thumbnail.
Sermon Title: "{title}"
Scripture Passage: "{scripture}"
Sermon Summary: "{summary}"
Visual Theme Category: "{theme_key}"

Write a single vivid, concrete text-to-image prompt (35-50 words) for a breathtaking, photorealistic background scene that visually connects to the specific topic and metaphor of this sermon:
- Match the heart of the message! For example:
  • Marriage, friendship, family, or unity -> a peaceful sunlit country path through a blooming meadow or two Adirondack chairs by a calm golden-hour lake surrounded by autumn trees.
  • Home, foundation, or authority -> a warm, sturdy cedar homestead in a sunlit mountain valley or a solid rock lighthouse/foundation beside clear waters at sunrise.
  • Faith, endurance, or spiritual warfare -> majestic rugged mountain peaks above morning clouds at sunrise.
  • The Word, truth, or doctrine -> a single open leather-bound Bible lying flat on a rustic wooden table outdoors in warm golden morning sunlight (never stacked Bibles or multiple Bibles).
  • Grace, salvation, or the Gospel -> a simple wooden cross on a grassy hill at sunrise with golden rays breaking through clouds.
  • Peace, guidance, or comfort -> green pastures and still reflective waters at dawn.
- STRICT NEGATIVE RULES:
  • We are an evangelical, non-denominational church. NEVER include any church buildings, inside-of-church interiors, cathedrals, stained glass, pews, altars, candles, or old-fashioned/cryptic religious architecture.
  • NEVER show two Bibles or a Bible standing on top of another Bible.
  • NO human faces/people, NO text, NO typography, NO letters, NO words in the image.
Return ONLY the raw prompt description, nothing else."""

        for model in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.7-flash", "gemini-3.6-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                res = requests.post(url, json={"contents": [{"parts": [{"text": p_text}]}]}, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    if "candidates" in data and data["candidates"]:
                        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        text = re.sub(r'^["\']|["\']$', '', text).strip()
                        if text:
                            return sanitize_evangelical_prompt(text, fallback_theme=theme_key)
            except Exception as e:
                print(f"[ImageGenerator] Prompt gen with {model} failed: {e}")
                continue
    except Exception as e:
        print(f"[ImageGenerator] AI prompt generation error: {e}")

    return sanitize_evangelical_prompt(default_prompt, fallback_theme=theme_key)

def _generate_with_flux_schnell(prompt, out_path):
    """
    Generates a native Full HD 1920x1080 image using black-forest-labs/FLUX.1-schnell via Gradio Client.
    """
    try:
        from gradio_client import Client
        print("[ImageGenerator] Generating native 1920x1080 HD artwork with FLUX.1-schnell...", flush=True)
        client_kwargs = {}
        if HF_TOKEN:
            client_kwargs["token"] = HF_TOKEN
        client = Client("black-forest-labs/FLUX.1-schnell", **client_kwargs)
        result = client.predict(
            prompt=prompt,
            seed=0,
            randomize_seed=True,
            width=1920,
            height=1080,
            num_inference_steps=4,
            api_name="/infer"
        )
        img_temp_path = result[0] if isinstance(result, (list, tuple)) else result
        if isinstance(img_temp_path, dict) and "path" in img_temp_path:
            img_temp_path = img_temp_path["path"]

        if img_temp_path and os.path.exists(img_temp_path):
            dir_name = os.path.dirname(os.path.abspath(out_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with Image.open(img_temp_path) as im:
                rgb = im.convert("RGB")
                if rgb.size != (1920, 1080):
                    rgb = rgb.resize((1920, 1080), Image.Resampling.LANCZOS)
                rgb.save(out_path, "JPEG", quality=96, subsampling=0)
            print(f"[ImageGenerator] FLUX.1-schnell native 1920x1080 artwork saved to {out_path}")
            return out_path
    except Exception as e:
        print(f"[ImageGenerator] FLUX.1-schnell generation notice: {e}")
    return None

def _generate_with_pollinations_hd(prompt, out_path, max_retries=2):
    """
    Fallback: Fetches 1920x1080 Flux image from Pollinations.ai.
    """
    seed = random.randint(1000, 999999)
    encoded = urllib.parse.quote(prompt.strip())
    url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width=1920&height=1080&nologo=true&enhance=true&seed={seed}"

    for attempt in range(max_retries):
        try:
            print(f"[ImageGenerator] Requesting Pollinations Flux HD image (attempt {attempt + 1}/{max_retries})...", flush=True)
            r = requests.get(url, timeout=35)

            if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
                raw_path = out_path + ".raw.jpg"
                dir_name = os.path.dirname(os.path.abspath(out_path))
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

                with open(raw_path, 'wb') as f:
                    f.write(r.content)

                with Image.open(raw_path) as im:
                    rgb = im.convert("RGB")
                    w, h = rgb.size
                    cropped = rgb.crop((0, 0, w, max(h - 40, int(h * 0.94))))
                    upscaled = cropped.resize((1920, 1080), Image.Resampling.LANCZOS)
                    upscaled.save(out_path, "JPEG", quality=96, subsampling=0)

                if os.path.exists(raw_path):
                    try:
                        os.remove(raw_path)
                    except Exception:
                        pass

                print(f"[ImageGenerator] Pollinations HD image saved to {out_path} (1920x1080)")
                return out_path
            else:
                print(f"[ImageGenerator] Pollinations returned {r.status_code}")
                break
        except Exception as e:
            print(f"[ImageGenerator] Pollinations fallback error: {e}")
            break

    return None

def fetch_ai_image(prompt, out_path, max_retries=2):
    """
    Generates a high-resolution 1920x1080 16:9 sermon background image:
    1. Primary: Native 1920x1080 via black-forest-labs/FLUX.1-schnell (Hugging Face Gradio API).
    2. Fallback: 1920x1080 via Pollinations Flux HD.
    """
    res = _generate_with_flux_schnell(prompt, out_path)
    if res and os.path.exists(res):
        return res

    return _generate_with_pollinations_hd(prompt, out_path, max_retries=max_retries)

def generate_sermon_artwork(title, preacher, display_date, scripture="", visual_theme="WORD_TEACHING", subtitle="", out_path=None, custom_image_path=None, sermon_summary="", ai_image_prompt=""):
    """
    Creates complete 1920x1080 Full HD sermon thumbnail and video backdrop:
    1. If user provided a custom image, uses that.
    2. Otherwise, crafts a sermon-specific evangelical prompt (strictly no church interiors) and
       generates a native 1920x1080 image using FLUX.1-schnell.
    3. If online AI generation is unreachable, falls back to curated 1080p outdoor/Bible backdrops.
    4. Renders supersampled, anti-aliased typography with Gaussian shadows and gold gradients.
    """
    if not out_path:
        raise ValueError("out_path is required")

    bg_path = None

    # Option A: User uploaded custom graphic
    if custom_image_path and os.path.exists(custom_image_path):
        bg_path = custom_image_path

    # Option B: Dynamic High-Res AI Generation (FLUX.1-schnell 1920x1080)
    if not bg_path:
        try:
            prompt = create_thematic_prompt(
                title=title,
                scripture=scripture,
                visual_theme=visual_theme,
                summary=sermon_summary,
                ai_image_prompt=ai_image_prompt
            )
            print(f"[ImageGenerator] Dynamic AI Prompt: {prompt}")
            ai_bg_target = os.path.join(os.path.dirname(os.path.abspath(out_path)), f"ai_bg_{int(time.time())}.jpg")
            bg_path = fetch_ai_image(prompt, ai_bg_target)
        except Exception as e:
            print(f"[ImageGenerator] Error during dynamic AI generation: {e}")
            bg_path = None

    # Option C: Curated Thematic Fallback (100% outdoor nature / open Bible in sunlight, zero church buildings)
    if not bg_path or not os.path.exists(bg_path):
        print(f"[ImageGenerator] Using curated 1080p backdrop for theme: {visual_theme}")
        bg_path = resolve_backdrop_image(visual_theme=visual_theme)

    # Render supersampled 4K->1080p typography & scrim
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
