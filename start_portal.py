import os
import sys
import time
import socket
import subprocess
import re
import webbrowser
from threading import Thread

# Fix windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = r"d:\Personal\cloudflared.exe"
PORT = 5000

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return 'localhost'
    finally:
        s.close()

def run_server():
    from app import app
    from waitress import serve
    serve(app, host='0.0.0.0', port=PORT, threads=6)

def run_tunnel():
    if not os.path.exists(CLOUDFLARED):
        return
    cmd = [CLOUDFLARED, "tunnel", "--url", f"http://localhost:{PORT}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding='utf-8', errors='replace')
    
    pattern = r'https://(?!api\b)([a-zA-Z0-9-]+)\.trycloudflare\.com'
    tunnel_url = None
    for line in proc.stdout:
        if not tunnel_url:
            match = re.search(pattern, line)
            if match:
                tunnel_url = match.group(0)
                print(f"\n  ===============================================================")
                print(f"  PERMANENT CLOUD PORTAL LINK:")
                print(f"  >>> https://vcf-sermon-uploader-1.onrender.com/ <<<")
                print(f"  ===============================================================")
                print(f"  Local Tunnel URL: {tunnel_url}")
                with open(os.path.join(BASE_DIR, "active_mobile_link.txt"), "w", encoding="utf-8") as f:
                    f.write(tunnel_url)

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("=" * 70)
    print("   VICTORY CHRISTIAN FELLOWSHIP - SERMON PUBLISHING PORTAL")
    print("=" * 70)
    print(f"\n  LOCAL COMPUTER:              http://localhost:{PORT}")
    print(f"  NETWORK ACCESS (Same WiFi):  http://{local_ip}:{PORT}")
    print(f"  CLOUD PORTAL (24/7):         https://vcf-sermon-uploader-1.onrender.com/")

    # Start server in thread
    t_server = Thread(target=run_server, daemon=True)
    t_server.start()

    # Start tunnel in thread
    t_tunnel = Thread(target=run_tunnel, daemon=True)
    t_tunnel.start()

    time.sleep(2)
    webbrowser.open(f"http://localhost:{PORT}")

    print("\n  Portal is running! Keep this window open while publishing sermons.")
    print("  Press Ctrl+C to stop the portal.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down portal...")
