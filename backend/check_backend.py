"""
CivicLens - check that a RUNNING backend is healthy and that the browser
will be allowed to talk to it (CORS).  Run it before the demo:

    python check_backend.py                              (local, port 5000)
    python check_backend.py https://milyas1.pythonanywhere.com
    python check_backend.py http://127.0.0.1:5000 http://localhost:3001

Arguments:  [backend URL]  [website origin to test]
It never sends your API key or admin password.
"""

import sys

import requests

backend = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
origin = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:3001"

problems = 0


def result(ok, text):
    global problems
    print(("  OK    " if ok else "  FAIL  ") + text)
    if not ok:
        problems += 1


print(f"Backend: {backend}\nBrowser origin tested: {origin}\n")

try:
    r = requests.get(f"{backend}/health", timeout=15)
except requests.RequestException as e:
    print(f"  FAIL  Cannot reach the backend: {e}")
    print("        -> Is `python app.py` running in the backend folder? Right port?")
    sys.exit(1)

result(r.status_code == 200, f"/health answered {r.status_code}")

try:
    info = r.json()
except ValueError:
    info = {}
    result(False, "/health did not return JSON (is this really the CivicLens backend?)")

if info:
    result("model" in info, f"this is the NEW backend (model: {info.get('model', 'unknown - OLD version running?')})")
    print(f"        reports saved: {info.get('reports_saved', 'n/a')}")
    result(bool(info.get("admin_configured")), "admin login configured (run setup_admin.py if not)")

pre = requests.options(
    f"{backend}/analyze",
    headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    timeout=15,
)
allowed = pre.headers.get("Access-Control-Allow-Origin")
result(allowed in (origin, "*"), f"CORS preflight for /analyze (Allow-Origin: {allowed})")

get = requests.get(f"{backend}/reports", headers={"Origin": origin}, timeout=15)
result(get.headers.get("Access-Control-Allow-Origin") in (origin, "*"), "CORS header on /reports")

print()
if problems:
    print(f"{problems} problem(s) found. Fix them, restart the backend and run this again.")
    sys.exit(1)

print("All good - the browser can talk to this backend.")
