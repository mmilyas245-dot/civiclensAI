# CivicLens: Fixes, Setup and Deployment

## 0. DO THIS FIRST: your Gemini API key was exposed

`backend/.env.example` in your zip contained a **real Gemini key, identical to the one in `backend/.env`**. `.env.example` is meant to be committed to GitHub. If you ever pushed that file, treat the key as public (Git history keeps it even after you edit the file).

1. Go to https://aistudio.google.com/apikey, create a **new** key and delete the old one.
2. Put the new key in `backend/.env` (local) and in the `.env` on PythonAnywhere. Never in `.env.example` and never in frontend code.
3. In this fixed version `.env.example` now holds only a placeholder, and a root `.gitignore` plus `backend/.gitignore` keep `.env`, `.venv`, `data/` and `node_modules` out of Git.
4. If the key was already pushed: after rotating it, you do not need to rewrite history, because the old key is dead.

The frontend has no secrets: only `NEXT_PUBLIC_API_URL` (a public address). I searched the frontend source and found no keys or passwords.

---

## 1. What was actually wrong

### The CORS / "Failed to fetch" error

**Your CORS list was correct.** I ran your real `app.py` and confirmed that `localhost:3001` receives the right `Access-Control-Allow-Origin` header on both the preflight and the real request. So adding the origin was never going to change anything.

What produces that exact browser message is a response **without** the CORS header. I found and reproduced these causes:

| # | Cause | Status |
|---|---|---|
| 1 | **`debug=True`**: any unhandled crash returns Werkzeug's debugger page with **no CORS header**, so the browser shows "blocked by CORS" and hides the real error. Reproduced: same crash with debug off keeps the header. | Fixed (debug off by default, plus a global JSON error handler. Tested with debug ON: header kept). |
| 2 | Debug mode also ran the **auto-reloader**, which can restart the server mid-request (browser: "Failed to fetch"). | Fixed (`use_reloader=False`). |
| 3 | Hard-coded origin list: a different Next.js port (3002 when 3001 is busy) or a new Vercel preview URL gets no header. | Fixed (any localhost port, your Vercel domains and preview URLs, optional `CORS_ORIGINS`). |
| 4 | **Likely, but I cannot prove it from here:** an **old backend still running on port 5000**. Your zip has no saved-reports file, yet you saw four reports, which suggests an older in-memory version answered. On Windows an old process can keep the port. | Use `check_backend.py` and the commands in section 3. |
| 5 | The frontend swallowed the real error: after any failure it retried silently and then always showed "could not connect", even for a 500 with a clear message. | Fixed. |

Please check cause 4 yourself, because it is the one I could not test:
`netstat -ano | findstr :5000` should show **one** process. If you see several, stop them all (`taskkill /PID <pid> /F`) and start the backend once.

### All bugs fixed

**Security**
1. Real Gemini key in `.env.example` replaced with a placeholder (see section 0).
2. No `.gitignore` anywhere: added root and backend ignore files.
3. `debug=True` on `host=0.0.0.0` exposed Flask's debugger to your whole Wi-Fi. Now `127.0.0.1` and debug off by default (`FLASK_DEBUG=1` to opt in).
4. Admin login crashed (HTTP 500) when a username contained a non-ASCII character. Now returns a normal 401.
5. CORS no longer sends credentials flags you do not need (login uses a Bearer token, not cookies).

**Backend (`backend/app.py`)**
6. Global error handler: every error is JSON and keeps CORS headers.
7. Report IDs used `len(list)+1`, which could repeat IDs after a deletion. Now `max id + 1`.
8. A citizen's submission could be **lost** if the AI agent step failed (rate limit, max steps). Now the report is saved directly as a fallback.
9. Large phone photos (4000 px, many MB) were sent to Gemini at full size: slow and a cause of timeouts. Photos are now rotated correctly (EXIF) and resized to 1280 px before analysis.
10. Gemini calls had no retry or timeout. Now: 45 s timeout and up to 3 tries on temporary errors (429/503).
11. AI JSON was trusted blindly. Now validated: severity limited to Low/Medium/High/Critical, priority clamped to 1-10, missing fields filled, code fences stripped.
12. A **Resolved** report was still offered as a "duplicate" for the same spot. Now closed reports are ignored, so a returning problem becomes a new report.
13. "Update" overwrote the previous extra information. Now new information is appended.
14. Retrying a request could update the same report twice. Now each submission carries a `client_request_id`, and a repeat gets the same answer (10 minute memory).
15. Upload validation: non-image files are rejected with a clear 400, and uploads over 15 MB are refused.
16. A damaged `civic_reports.json` would be silently overwritten on the next save. Now it is renamed to `.corrupt-<time>` first.
17. Windows consoles could crash on non-English text in `print`. Output now replaces unprintable characters.
18. `/health` now also reports the model, report count and whether admin login is configured (no secrets).

**Frontend**
19. `app/globals.css` was **two files pasted together**: `@import "tailwindcss"` twice, duplicate rules, conflicting selection colours. Merged into one.
20. The public page never got the "In Progress" status edit: type and colour added, so reports the admin moves to In Progress keep their badge.
21. Retry logic: now retries **only** real network failures, shows the **server's own error message**, and does not show three alerts when location is denied.
22. The page titled "Create Next App": now "CivicLens - AI Civic Issue Reporting".
23. The sample rows ("#CL-0042" etc.) looked like live data. A "Sample data" notice now appears until real reports load.
24. `API_BASE_URL` now ignores a trailing slash.
25. ESLint: 7 errors reduced to 0.

**Files I did not delete but you should know about**
- `backend/vercel.json` and `backend/api/index.py`: leftovers for hosting the backend on Vercel. Your backend runs on PythonAnywhere, and Vercel's file system is read-only, so saving reports and photos would fail there. They are unused; delete them if you like.
- `INTEGRATION_GUIDE.md`: replaced by this document.
- `backend/.venv` (Windows virtual environment, hundreds of MB): do not upload or commit it. It is not in the fixed zip.

**Already correct (no change needed):** the admin dashboard (`app/admin/*`) calls the right endpoints with the right field names. Login, report list, photo loading and the PATCH status update all match the backend.

---

## 2. What I tested, and what I could not

**Run and passed**
- Backend: `python -m py_compile`; **37 automated tests** on your real `app.py` (CORS allowed/blocked origins, preflight with PATCH and Authorization, analyse -> create, nearby -> update, far -> create, resolved -> new report, ID uniqueness, persistence reload, admin login/token/status flow, protected photo endpoint, agent-failure fallback, debug-mode error keeping CORS, corrupt-file handling, idempotent retry).
- Real server start (`python app.py`) and a request exactly like the browser's, from origin `http://localhost:3001`.
- Frontend: TypeScript `tsc --noEmit` = 0 errors; ESLint = 0 errors (2 harmless warnings).
- PPTX: schema validation passed, 12 slides rendered and visually checked, speaker notes on all 12.

**NOT run: you must check these manually** (no internet or browser in my environment)
- **Real Gemini calls.** In my tests Gemini was replaced by a stand-in, so the *logic around* the AI is tested, but not Gemini's actual answers or the model name `gemini-3.1-flash-lite` on your key. Run `python check_api.py`.
- OpenStreetMap address lookup (it fails gracefully, and the report is still saved without an address).
- `npm run build` and the pages in a real browser: GPS prompt, photo upload, admin screens. The Windows-only build tools in your `node_modules` and the Google-fonts download could not run here.
- PythonAnywhere and Vercel deployments. Free PythonAnywhere accounts only reach an allow-list of sites, so run `check_api.py` **on the server**.

---

## 3. Run it locally (Windows)

**Backend** (Command Prompt, in the project folder)
```
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
python check_api.py          # must say Gemini works
python setup_admin.py        # only if admin login is not set up yet
python app.py                # -> http://127.0.0.1:5000
```
In a second window: `python check_backend.py` (expects "All good").

**Frontend**
```
cd civiclens-frontend
npm install
npm run dev -- -p 3001       # -> http://localhost:3001
```
`civiclens-frontend/.env.local` must contain `NEXT_PUBLIC_API_URL=http://127.0.0.1:5000`. Restart `npm run dev` after changing it.

**Manual test order**
1. `http://127.0.0.1:5000/health` shows `healthy` and `"model": "gemini-3.1-flash-lite"`.
2. Open `http://localhost:3001`, upload a photo, allow location, click Analyze: a result appears.
3. Upload a similar photo at the same place: the report is **updated**, not duplicated.
4. Open `http://localhost:3001/admin`, sign in: the report shows with both photos.
5. Set **In Progress**, then **Resolved**. Reload: the status stays.
6. Stop and restart `python app.py`: the report is still there (stored in `backend/data/`).

New optional `.env` settings: `CORS_ORIGINS` (extra website addresses, comma separated), `FLASK_DEBUG=1` (local auto-reload; leave unset in production), `PORT`.

---

## 4. Deploy

**Backend on PythonAnywhere** (Bash console)
```
cd ~/CivicLens && git pull
workon <your-virtualenv>
cd backend
pip install -r requirements.txt
nano .env                    # GEMINI_API_KEY=<new key>, then run: python setup_admin.py
python check_api.py          # run it ON the server
```
Web tab: the WSGI file must import the app like this (adjust the path to your folder):
```python
import sys
path = '/home/milyas1/CivicLens/backend'
if path not in sys.path:
    sys.path.insert(0, path)
from app import app as application
```
Click the green **Reload** button. Then, from your PC:
`python check_backend.py https://milyas1.pythonanywhere.com https://civic-lens1.vercel.app`

**Frontend on Vercel**
1. Project Settings -> Environment Variables: `NEXT_PUBLIC_API_URL` = `https://milyas1.pythonanywhere.com` (no trailing slash).
2. **Redeploy.** The value is baked in at build time, so changing it without redeploying does nothing.
3. Test https://civic-lens1.vercel.app and https://civic-lens1.vercel.app/admin.

**Git**
```
git add .
git commit -m "Fix CORS/debug crashes, harden backend, merge admin dashboard"
git push
```
Check `git status` first: `.env`, `.venv`, `node_modules` and `backend/data` must NOT be listed.

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| "Failed to fetch" in the browser | Open DevTools -> Network -> click the failed `/analyze` request. No response = backend down or old process on the port. A status code = read the JSON `error`. Then run `check_backend.py`. |
| Alert shows the server's error text | That is the real cause. Check the backend terminal for the traceback. |
| `GEMINI_API_KEY is missing` | Add it to `backend/.env`, restart. |
| Gemini 429 | Free-tier limit: wait a minute (the backend already retries). |
| Admin says "not configured" | Run `python setup_admin.py`, restart the backend. |
| Admin locked out | 5 wrong tries lock for 10 minutes. Restart the backend to clear. |
| Vercel site cannot reach backend | `NEXT_PUBLIC_API_URL` wrong, or you did not redeploy after setting it. |

---

## 6. Honest limits of this version
- Reports and photos are stored in a JSON file and image files: fine for a hackathon, not for a city. The code comments already plan a move to a database.
- AI accuracy has not been measured. Do not quote any accuracy figure.
- Duplicate detection = reports within 1 km plus the AI's judgement. It is not guaranteed.
- No citizen accounts or notifications yet; the admin is a single login.
