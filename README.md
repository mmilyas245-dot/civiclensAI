# CivicLens — AI-Powered Civic Issue Reporting

## Project overview

CivicLens is an AI-assisted civic issue reporting MVP. Citizens can submit a photo of a public issue and, when available, its location. The Flask backend uses Google Gemini (`gemini-3.1-flash-lite`) to analyze the image and produce structured issue information. Reports can be reviewed in the admin dashboard, where an administrator can update their status.

AI-generated results and nearby/duplicate matching are decision-support features. They are not guaranteed to be correct and should be reviewed by people.

## Main features

- Submit a civic issue photo.
- Analyze the image using Gemini vision and return structured JSON.
- Capture the user's location when browser permission is granted.
- Find nearby reports and support updating a matching report.
- Save reports and uploaded images.
- Admin login, report listing, photo viewing, and status updates.

## Technology

- Frontend: Next.js, React, TypeScript
- Backend: Python, Flask
- AI: Google Gemini API, model `gemini-3.1-flash-lite`

## Requirements

- Python and pip
- Node.js and npm
- A Google Gemini API key
- Internet access from the backend for Gemini API requests

## Project structure

```text
CivicLens/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── check_api.py
│   ├── check_backend.py
│   └── setup_admin.py
└── civiclens-frontend/
    ├── app/
    ├── package.json
    └── .env.example (if included)
```

Other source files and assets required by the application should remain in their original folders.

## Run locally on Windows (PowerShell)

Run the backend and frontend in separate terminal windows. Keep both terminals running.

### 1. Backend setup

From the project root:

```powershell
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
```

If the virtual environment does not exist yet, create it first:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Create `backend/.env` based on `backend/.env.example` and set your own key:

```env
GEMINI_API_KEY=your_new_gemini_api_key
```

Never put a real key in `.env.example`, frontend code, GitHub, or the submission ZIP.

Test the Gemini connection:

```powershell
python check_api.py
```

The check should confirm:
- Text request works.
- Vision request (photo to JSON) works.
- Agent tool-calling works.

If admin login has not yet been configured, run this once and follow the prompts:

```powershell
python setup_admin.py
```

Start the backend:

```powershell
python app.py
```

The local backend should be available at `http://127.0.0.1:5000`.

In a separate terminal, you can run the backend connectivity check:

```powershell
cd <project-root>
python check_backend.py
```

It should report that the backend is reachable. If the script is located elsewhere in your project, run it from that location.

### 2. Frontend setup

Open another PowerShell window:

```powershell
cd civiclens-frontend
npm install
```

Create or update `civiclens-frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:5000
```

Start the frontend:

```powershell
npm run dev -- -p 3001
```

Open:

- Citizen interface: `http://localhost:3001`
- Admin dashboard: `http://localhost:3001/admin`
- Backend health: `http://127.0.0.1:5000/health`
- Reports endpoint: `http://127.0.0.1:5000/reports`

### 3. Admin access

Open `http://localhost:3001/admin` and sign in using the administrator credentials configured for this installation.

If admin access has not been configured, run `python setup_admin.py` from the activated backend environment. Do not include real admin passwords or access tokens in this README or in the public submission.

### 4. Suggested manual test sequence

1. Open `/health` and confirm the backend reports healthy and identifies `gemini-3.1-flash-lite`.
2. Open the citizen interface, upload an issue photo, grant location permission if appropriate, and submit it for analysis.
3. Confirm the AI analysis is displayed and the report is saved.
4. Submit a similar issue photo at the same location and check whether the nearby-report logic updates a matching report rather than creating a duplicate. This matching is approximate.
5. Open `/admin`, sign in, and confirm the report appears.
6. Change the report status to `In Progress`, then `Resolved`, and reload to confirm the status remains.
7. Restart the backend and confirm saved reports remain available in the configured local storage.

## Environment variables

Backend file: `backend/.env`

```env
GEMINI_API_KEY=your_gemini_api_key
```

Frontend file: `civiclens-frontend/.env.local`

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:5000
```

Optional backend settings documented by the project:

```env
CORS_ORIGINS=https://your-extra-origin.example
FLASK_DEBUG=1
PORT=5000
```

Keep debug mode disabled in production. The frontend API URL is public configuration; the Gemini key is secret.

## Deployment notes

### Backend — PythonAnywhere

1. Pull the latest project source into the PythonAnywhere project directory.
2. Activate the PythonAnywhere virtual environment.
3. Install backend dependencies:

   ```bash
   cd ~/CivicLens
   git pull
   workon <your-virtualenv>
   cd backend
   pip install -r requirements.txt
   ```

4. Create/update `backend/.env` on the server with a newly generated `GEMINI_API_KEY`.
5. Run `python check_api.py` on the server to test Gemini connectivity.
6. In the PythonAnywhere Web tab, configure the WSGI file with the correct project path. Example:

   ```python
   import sys

   path = '/home/<your-username>/CivicLens/backend'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```

7. Save the WSGI file and click **Reload** in PythonAnywhere.
8. From your local computer, test the deployed backend/frontend connectivity using the project's `check_backend.py` script, if available:

   ```powershell
   python check_backend.py https://your-backend-domain https://your-frontend-domain
   ```

### Frontend — Vercel

1. In Vercel project settings, add the environment variable:

   ```env
   NEXT_PUBLIC_API_URL=https://your-backend-domain
   ```

2. Redeploy the frontend after changing the environment variable.
3. Test the deployed citizen page and `/admin` page.

Replace example domains and paths with the actual deployment values used by the team. Never place the Gemini key in Vercel frontend environment variables.

## AI implementation and disclosure

CivicLens uses the Google Gemini API with the `gemini-3.1-flash-lite` model for image understanding and structured issue analysis. The backend also uses an agent workflow with tools such as nearby-report lookup and report saving/updating. The project uses open-source frontend and backend dependencies listed in `civiclens-frontend/package.json` and `backend/requirements.txt`.

The AI-generated category, severity, priority, description, and recommendations may be incorrect. No measured AI accuracy percentage is claimed.

## Data, security, and limitations

- Reports and photos are stored in JSON and image files under the backend data storage. This is suitable for an MVP demonstration, not a production city-wide deployment.
- Nearby/duplicate matching considers reports within approximately 1 km together with AI judgement; it is not guaranteed.
- The MVP does not include citizen accounts or automated citizen notifications.
- Admin access uses a configured administrator login.
- Do not include real `.env` files, API keys, passwords, tokens, or private user data in the ZIP or public repository.
- The Gemini API key was previously found exposed in an earlier `.env.example`. Generate a new key, revoke the exposed key, and use only the new key in local/server `.env` files. The `.env.example` must contain placeholders only.

## Hackathon submission checklist

- Include this `README.md`.
- Include the complete frontend and backend source code.
- Include `backend/requirements.txt` and `civiclens-frontend/package.json`.
- Include a safe `.env.example` with placeholder values only.
- Remove `.venv/`, `node_modules/`, `__pycache__/`, actual `.env` files, and other local secret/configuration files.
- Do not include backend virtual environments or generated local data unless the organizers specifically request sample data.
- Keep the ZIP at or below 200 MB.
- Name the ZIP exactly as required: `[Application_Ref]_[Team_Name].zip`.
- Record the mandatory 2-minute MVP demo, upload it to YouTube, and submit an accessible video link in the official Google Form.
- Dataset links and GitHub/GitLab repository URLs are optional according to the competition instructions.

## Dataset information

The setup notes provided for this version do not identify an external training dataset. If the final submitted project uses an external or custom dataset, provide its direct link in the designated Google Form field.
