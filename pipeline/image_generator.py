import os
import requests
import json
import base64
from config import GEMINI_API_KEY
from pipeline.video_maker import render_sermon_backdrop

def generate_sermon_artwork(title, preacher, display_date, scripture="", visual_theme="WORD_TEACHING", subtitle="", out_path=None, custom_image_path=None):
    """
    Creates complete sermon thumbnail and video backdrop.
    1. If custom image was provided, uses that.
    2. Renders high-impact cinematic artwork with 3D embossed golden typography,
       matching the exact design from modern sermon broadcasts.
    """
    if not out_path:
        raise ValueError("out_path is required")

    # If user uploaded a custom graphic directly
    if custom_image_path and os.path.exists(custom_image_path):
        return render_sermon_backdrop(
            title=title,
            preacher=preacher,
            date_str=display_date,
            out_image_path=out_path,
            scripture=scripture,
            visual_theme=visual_theme,
            custom_bg_path=custom_image_path,
            subtitle=subtitle
        )

    # Render with the enhanced cinematic typography engine
    return render_sermon_backdrop(
        title=title,
        preacher=preacher,
        date_str=display_date,
        out_image_path=out_path,
        scripture=scripture,
        visual_theme=visual_theme,
        subtitle=subtitle
    )
