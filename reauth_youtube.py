import os
import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from config import CLIENT_SECRET_PATH, TOKEN_PATH

# Force immediate console output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

def main():
    print("=" * 65, flush=True)
    print("   VICTORY CHRISTIAN FELLOWSHIP - YOUTUBE AUTHENTICATION", flush=True)
    print("=" * 65, flush=True)
    print("\nStarting local authentication server...", flush=True)
    print("A browser window will open automatically asking you to log into", flush=True)
    print("the Google account that manages Victory Christian Fellowship's YouTube channel.\n", flush=True)
    print("If Google displays 'Google hasn't verified this app':", flush=True)
    print("  1. Click 'Advanced' (bottom left)", flush=True)
    print("  2. Click 'Go to vcf-sermons (unsafe)'", flush=True)
    print("  3. Check the YouTube permissions and click 'Continue'\n", flush=True)

    if not os.path.exists(CLIENT_SECRET_PATH):
        print(f"Error: client_secret.json not found at: {CLIENT_SECRET_PATH}", flush=True)
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_PATH,
        scopes=SCOPES
    )

    try:
        # Fixed port 8088 or random port
        creds = flow.run_local_server(
            port=8088,
            prompt="consent",
            access_type="offline"
        )

        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        print("\n" + "=" * 65, flush=True)
        print("  [SUCCESS] New YouTube token generated and saved to token.json!", flush=True)
        print("=" * 65, flush=True)
        print("You can now upload sermons to YouTube.\n", flush=True)

    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {e}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
