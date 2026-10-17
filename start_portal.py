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
    except:
        return 'localhost'
    finally:
        s.close()

def run_server():
    from app import app
    from waitress import serve
    serve(app, host='0.0.0.0', port=PORT, threads=6)

WEBSITE_DIR = r"d:\Personal\VCF Website"

def update_website_redirect(tunnel_url):
    """Updates victorychristianfellowship.ca/upload to redirect to the active tunnel"""
    try:
        import json
        upload_dir = os.path.join(WEBSITE_DIR, "upload")
        os.makedirs(upload_dir, exist_ok=True)
        redirect_file = os.path.join(upload_dir, "index.html")
        root_redirect = os.path.join(WEBSITE_DIR, "upload.html")
        tunnel_json_path = os.path.join(upload_dir, "tunnel.json")

        tunnel_data = {
            "url": tunnel_url,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        with open(tunnel_json_path, "w", encoding="utf-8") as f:
            json.dump(tunnel_data, f, indent=2)

        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>Connecting to VCF Sermon Publisher</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1e3142;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            text-align: center;
            padding: 20px;
            box-sizing: border-box;
        }
        .box {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 40px 28px;
            max-width: 480px;
            width: 100%;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .spinner {
            width: 44px;
            height: 44px;
            border: 4px solid rgba(255,255,255,0.2);
            border-top-color: #EA642A;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 20px auto;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        h2 { margin: 0 0 10px 0; font-size: 1.35rem; font-weight: 700; }
        p { color: #94aec5; font-size: 0.95rem; margin: 0 0 24px 0; line-height: 1.4; }
        .btn {
            display: inline-block;
            background: #EA642A;
            color: white;
            padding: 14px 28px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 700;
            font-size: 1rem;
            transition: background 0.2s;
        }
        .btn:hover { background: #ce5119; }
        .hint { margin-top: 18px; font-size: 0.82rem; color: #7890a8; }
    </style>
</head>
<body>
    <div class="box">
        <div class="spinner"></div>
        <h2>Connecting to Sermon Publisher...</h2>
        <p>Connecting securely to Victory Christian Fellowship's publishing portal.</p>
        <a id="portal-link" href="{URL}" class="btn">Open Portal Directly</a>
        <div class="hint" id="status-hint">Resolving active portal link...</div>
    </div>

    <script>
        var fallbackUrl = "{URL}";
        var targetUrl = fallbackUrl;

        function redirect(url) {
            if (url) {
                var btn = document.getElementById('portal-link');
                if (btn) btn.href = url;
                window.location.replace(url);
            }
        }

        var ts = Date.now();
        var urlsToTry = [
            'tunnel.json?v=' + ts,
            'https://raw.githubusercontent.com/jakesiemens/vcf-site/main/upload/tunnel.json?v=' + ts
        ];

        function tryNext(index) {
            if (index >= urlsToTry.length) {
                setTimeout(function() { redirect(fallbackUrl); }, 500);
                return;
            }
            fetch(urlsToTry[index], { cache: 'no-store' })
                .then(function(res) {
                    if (res.ok) return res.json();
                    throw new Error('Not ok');
                })
                .then(function(data) {
                    if (data && data.url) {
                        targetUrl = data.url;
                        var hint = document.getElementById('status-hint');
                        if (hint) hint.textContent = 'Redirecting...';
                        redirect(targetUrl);
                    } else {
                        tryNext(index + 1);
                    }
                })
                .catch(function() {
                    tryNext(index + 1);
                });
        }

        tryNext(0);

        setTimeout(function() {
            redirect(targetUrl);
        }, 3000);
    </script>
</body>
</html>""".replace("{URL}", tunnel_url)

        with open(redirect_file, "w", encoding="utf-8") as f:
            f.write(html_template)
        with open(root_redirect, "w", encoding="utf-8") as f:
            f.write(html_template)
            
        print("\n  Updating permanent website link: https://victorychristianfellowship.ca/upload...")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=WEBSITE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "upload/index.html", "upload.html", "upload/tunnel.json"], cwd=WEBSITE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Update live sermon uploader redirect URL and tunnel.json"], cwd=WEBSITE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        push_res = subprocess.run(["git", "push", "origin", "main"], cwd=WEBSITE_DIR, capture_output=True, text=True)
        if push_res.returncode == 0:
            print("  [SUCCESS] Permanent link is live: https://victorychristianfellowship.ca/upload\n")
        else:
            print(f"  [WARNING] Git push failed: {push_res.stderr.strip()}\n")
    except Exception as e:
        print(f"  Notice: Could not update git redirect: {e}")

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
                print(f"  PERMANENT CHURCH LINK FOR YOUR VOLUNTEER:")
                print(f"  >>> https://victorychristianfellowship.ca/upload <<<")
                print(f"  ===============================================================")
                print(f"  Direct Tunnel URL: {tunnel_url}")
                with open(os.path.join(BASE_DIR, "active_mobile_link.txt"), "w", encoding="utf-8") as f:
                    f.write(tunnel_url)
                
                # Automatically update the church website redirect!
                update_website_redirect(tunnel_url)

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("=" * 70)
    print("   VICTORY CHRISTIAN FELLOWSHIP - SERMON PUBLISHING PORTAL")
    print("=" * 70)
    print(f"\n  LOCAL COMPUTER:              http://localhost:{PORT}")
    print(f"  NETWORK ACCESS (Same WiFi):  http://{local_ip}:{PORT}")
    print("\n  Starting secure mobile tunnel... Please wait...")

    # Start server in thread
    t_server = Thread(target=run_server, daemon=True)
    t_server.start()

    # Start tunnel in thread
    t_tunnel = Thread(target=run_tunnel, daemon=True)
    t_tunnel.start()

    time.sleep(2)
    # Open local browser
    webbrowser.open(f"http://localhost:{PORT}")

    print("\n  Portal is running! Keep this window open while publishing sermons.")
    print("  Press Ctrl+C to stop the portal.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down portal...")
