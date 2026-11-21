import os
import io
import json
import base64
import math
import hmac
import time
import threading
import uuid
import re
import sys
from functools import wraps
from datetime import datetime, timezone
from io import BytesIO
from google import genai
from google.genai import types

from flask import Flask, request, jsonify, Response, g
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image, ImageOps
from werkzeug.security import check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature
import requests

# ============================================================
# CIVICLENS BACKEND
# ============================================================

load_dotenv(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
)

# A Windows console can crash on non-English text inside print().
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass


# ------------------------------------------------------------
# Flask application
# ------------------------------------------------------------

app = Flask(__name__)

# Browser origins allowed to call this API.
#
#   * any http://localhost:<port> / http://127.0.0.1:<port>   (local dev,
#     so it keeps working if Next.js moves from port 3001 to 3002)
#   * the production site and this project's Vercel preview deployments
#   * anything extra you list in CORS_ORIGINS (comma separated) in .env
#
# Login uses a Bearer token in the Authorization header, not cookies,
# so supports_credentials stays False.

_extra_origins = [
    o.strip().rstrip("/")
    for o in os.getenv("CORS_ORIGINS", "").split(",")
    if o.strip()
]

ALLOWED_ORIGINS = [
    "https://civic-lens1.vercel.app",
    re.compile(r"^https://civic-lens1(-[a-z0-9]+)*-ai-lover\.vercel\.app$"),
    re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d{2,5})?$"),
] + _extra_origins

CORS(
    app,
    resources={r"/*": {"origins": ALLOWED_ORIGINS}},
    supports_credentials=False,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PATCH", "OPTIONS"],
    max_age=600,
)

# Reject absurdly large uploads early (phone photos are usually 2-8 MB).
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024


@app.errorhandler(Exception)
def handle_any_error(error):
    """
    Always answer with JSON, even when something crashes.

    Why this matters: when Flask runs with debug=True an unhandled error
    is answered by the Werkzeug debugger page WITHOUT any CORS header, so
    the browser reports a misleading "blocked by CORS policy / Failed to
    fetch" instead of the real error. Handling it here keeps the CORS
    headers on every response and the real message visible.
    """

    if isinstance(error, HTTPException):
        return jsonify({
            "success": False,
            "error": error.description or error.name
        }), error.code

    print(f"UNHANDLED ERROR on {request.method} {request.path}: {error!r}")

    return jsonify({
        "success": False,
        "error": "Internal server error. Check the backend terminal."
    }), 500


# ------------------------------------------------------------
# Gemini client
# ------------------------------------------------------------

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing.")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=45000)
)

GEMINI_MODEL = "gemini-3.1-flash-lite"


# ============================================================
# CIVIC REPORT STORAGE
# ============================================================

# Prototype storage.
#
# Later we will replace this with Supabase/PostgreSQL.
#
# For now reports remain available while Flask is running.

civic_reports = []

# ------------------------------------------------------------
# Persistence: reports and their photos survive restarts
# ------------------------------------------------------------
#
# The civic_reports list above is still what the agent code uses.
# Every change is also written to backend/data/civic_reports.json and
# photos are kept in backend/data/photos/.

DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data"
)

PHOTO_DIR = os.path.join(DATA_DIR, "photos")

DATA_FILE = os.path.join(DATA_DIR, "civic_reports.json")

os.makedirs(PHOTO_DIR, exist_ok=True)

_store_lock = threading.RLock()

_last_mtime = None

MAX_PHOTOS_PER_REPORT = 5


def persist_reports():
    """Atomically write all reports to disk."""

    global _last_mtime

    with _store_lock:
        tmp_path = DATA_FILE + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(civic_reports, f, ensure_ascii=False)

        os.replace(tmp_path, DATA_FILE)

        _last_mtime = os.path.getmtime(DATA_FILE)


def load_reports():
    """Load saved reports (if any) into civic_reports."""

    global _last_mtime

    if not os.path.exists(DATA_FILE):
        return

    with _store_lock:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)

            if isinstance(saved, list):
                civic_reports[:] = saved

            _last_mtime = os.path.getmtime(DATA_FILE)

        except Exception as e:
            print(f"Could not load saved reports: {e}")

            try:
                backup = f"{DATA_FILE}.corrupt-{int(time.time())}"
                os.replace(DATA_FILE, backup)
                print(f"Damaged data file kept as {backup}")
            except OSError:
                pass


load_reports()


@app.before_request
def sync_reports_from_disk():
    """If another web worker saved reports, pick them up."""

    try:
        if (
            os.path.exists(DATA_FILE)
            and os.path.getmtime(DATA_FILE) != _last_mtime
        ):
            load_reports()
    except OSError:
        pass


def next_report_id():
    """Next free report id (max + 1, so ids are never reused)."""

    return max(
        (r.get("report_id", 0) for r in civic_reports),
        default=0
    ) + 1


def find_report(report_id):

    for saved_report in civic_reports:
        if saved_report["report_id"] == report_id:
            return saved_report

    return None


def photo_path(report_id, n):

    return os.path.join(
        PHOTO_DIR,
        f"report_{int(report_id)}_{int(n)}.jpg"
    )


def attach_evidence(report_id, address, image_file):
    """
    Save the street address and the uploaded photo on a report.
    Never raises - the citizen's analysis result must not fail
    because of a storage problem.
    """

    try:

        if not report_id:
            return

        with _store_lock:

            saved_report = find_report(report_id)

            if saved_report is None:
                return

            if address and not saved_report.get("address"):
                saved_report["address"] = address

            count = saved_report.get("photo_count", 0)

            if count < MAX_PHOTOS_PER_REPORT:

                image_file.stream.seek(0)

                photo = ImageOps.exif_transpose(
                    Image.open(image_file.stream)
                ).convert("RGB")

                photo.thumbnail((1280, 1280))

                photo.save(
                    photo_path(report_id, count),
                    format="JPEG",
                    quality=82
                )

                saved_report["photo_count"] = count + 1

            persist_reports()

    except Exception as e:
        print(f"Could not store evidence: {e}")


def public_report(saved_report):
    """Report as sent to the public site (no admin-only data)."""

    return {
        k: v for k, v in saved_report.items()
        if k not in ("status_history", "admin_note")
    }


# ============================================================
# LOCATION TOOL
# ============================================================

# ============================================================
# LOCATION TOOL
# ============================================================

import requests


def get_location(latitude=None, longitude=None):
    """
    Get the user's real browser GPS location.

    If frontend sends coordinates:
        latitude + longitude
    → use them
    → reverse geocode with OpenStreetMap Nominatim

    If no coordinates are provided:
        use CivicLens test coordinates.
    """

    # --------------------------------------------------------
    # REAL GPS LOCATION FROM FRONTEND
    # --------------------------------------------------------

    if latitude is not None and longitude is not None:

        latitude = float(latitude)
        longitude = float(longitude)

        try:

            url = "https://nominatim.openstreetmap.org/reverse"

            params = {
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1
            }

            headers = {
                "User-Agent": "CivicLens/1.0"
            }

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=5
            )

            response.raise_for_status()

            data = response.json()

            return {
                "success": True,

                "location": {
                    "latitude": latitude,
                    "longitude": longitude,

                    "address":
                        data.get("display_name"),

                    "address_details":
                        data.get("address", {})
                },

                "message":
                    "Real GPS location received and reverse-geocoded."
            }

        except Exception as e:

            print(
                f"OpenStreetMap error: {e}"
            )

            # GPS is still valid even if
            # address lookup fails.

            return {
                "success": True,

                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": None
                },

                "message":
                    "GPS received but address lookup failed."
            }

    # --------------------------------------------------------
    # TEST / FALLBACK LOCATION
    # --------------------------------------------------------

    return {

        "success": True,

        "location": {

            "latitude": 34.0151,

            "longitude": 71.5249,

            "address":
                "CivicLens test location"

        },

        "message":
            "Using CivicLens test location."
    }
# ============================================================
# DISTANCE CALCULATION
# ============================================================

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two GPS coordinates
    using the Haversine formula.

    Returns distance in kilometers.
    """

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)

    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.asin(math.sqrt(a))

    earth_radius_km = 6371

    return earth_radius_km * c


# ============================================================
# FIND NEARBY REPORTS
# ============================================================

def find_nearby_reports(
    latitude,
    longitude,
    radius_km=1
):
    """
    Find previously reported civic problems
    within the specified radius.
    """

    nearby_reports = []

    for saved_report in civic_reports:

        if "location" not in saved_report:
            continue

        report_lat = saved_report["location"]["latitude"]
        report_lon = saved_report["location"]["longitude"]

        distance = calculate_distance(
            latitude,
            longitude,
            report_lat,
            report_lon
        )

        if distance <= radius_km:

            nearby_reports.append({
                "report_id": saved_report["report_id"],
                "problem": saved_report["problem"],
                "category": saved_report["category"],
                "severity": saved_report["severity"],
                "priority_score": saved_report["priority_score"],
                "distance_km": round(distance, 3),
                "status": saved_report["status"]
            })

    return {
        "success": True,
        "number_of_nearby_reports": len(nearby_reports),
        "reports": nearby_reports
    }


# ============================================================
# SAVE CIVIC REPORT
# ============================================================

def save_civic_report(
    problem,
    category,
    severity,
    priority_score,
    responsible_department,
    description,
    risk,
    recommended_action,
    latitude,
    longitude
):
    """
    Save a new CivicLens report.
    """

    now_iso = datetime.now(timezone.utc).isoformat()

    new_report = {

        "report_id": 0,

        "problem": problem,

        "category": category,

        "severity": severity,

        "priority_score": priority_score,

        "responsible_department": responsible_department,

        "description": description,

        "risk": risk,

        "recommended_action": recommended_action,

        "location": {
            "latitude": latitude,
            "longitude": longitude
        },

        "status": "Pending",

        "created_at": now_iso,

        "report_count": 1,

        "status_history": [
            {
                "status": "Pending",
                "at": now_iso,
                "note": "Report created by CivicLens AI",
                "by": "CivicLens AI"
            }
        ]
    }

    with _store_lock:
        new_report["report_id"] = next_report_id()
        civic_reports.append(new_report)
        persist_reports()

    return {
        "success": True,
        "report_id": new_report["report_id"],
        "message": "Civic report successfully saved."
    }


# ============================================================
# UPDATE CIVIC REPORT
# ============================================================

def update_civic_report(
    report_id,
    additional_information,
    new_severity=None,
    new_priority_score=None
):
    """
    Update an existing CivicLens report.
    """

    for saved_report in civic_reports:

        if saved_report["report_id"] == report_id:

            previous = saved_report.get("additional_information")

            saved_report["additional_information"] = (
                f"{previous} | {additional_information}"
                if previous
                else additional_information
            )[:1500]

            saved_report["report_count"] = (
                saved_report.get("report_count", 1) + 1
            )

            if new_severity is not None:
                saved_report["severity"] = new_severity

            if new_priority_score is not None:
                saved_report["priority_score"] = (
                    new_priority_score
                )

            persist_reports()

            return {
                "success": True,
                "report_id": report_id,
                "message": "Civic report successfully updated."
            }

    return {
        "success": False,
        "error": f"Report {report_id} not found."
    }


# ============================================================
# GEMINI VISION
# ============================================================

def gemini_generate(**kwargs):
    """
    Call Gemini, retrying briefly on temporary errors
    (rate limit 429, overload 503, network hiccups).
    """

    delay = 1.5

    for attempt in range(3):

        try:
            return client.models.generate_content(**kwargs)

        except Exception as e:

            text = str(e).lower()

            temporary = any(
                marker in text
                for marker in (
                    "429", "503", "500", "unavailable",
                    "resource_exhausted", "timed out",
                    "timeout", "connection"
                )
            )

            if attempt == 2 or not temporary:
                raise

            print(f"Gemini temporary error, retrying: {e}")

            time.sleep(delay)

            delay *= 2


ALLOWED_SEVERITIES = ("Low", "Medium", "High", "Critical")


def clean_analysis(data):
    """Make sure the model's JSON has every field and sane values."""

    if isinstance(data, list) and data:
        data = data[0]

    if not isinstance(data, dict):
        raise ValueError("Gemini did not return a JSON object.")

    severity = str(data.get("severity", "Medium")).strip().capitalize()

    if severity not in ALLOWED_SEVERITIES:
        severity = "Medium"

    try:
        priority = int(round(float(data.get("priority_score", 5))))
    except (TypeError, ValueError):
        priority = 5

    priority = max(1, min(10, priority))

    def text(key, default):
        value = str(data.get(key) or "").strip()
        return value or default

    return {
        "problem": text("problem", "Civic problem"),
        "category": text("category", "General"),
        "severity": severity,
        "priority_score": priority,
        "responsible_department": text(
            "responsible_department", "Municipal Corporation"
        ),
        "description": text("description", ""),
        "risk": text("risk", ""),
        "recommended_action": text("recommended_action", "")
    }


def analyze_image_with_gemini(image_file):

    # Phone photos can be 4000x3000 px. Fix the rotation and shrink the
    # picture first: Gemini does not need more, and the upload is much
    # faster (fewer slow requests and timeouts).
    image = ImageOps.exif_transpose(Image.open(image_file))

    image = image.convert("RGB")

    image.thumbnail((1280, 1280))

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=85
    )

    image_part = types.Part.from_bytes(
        data=buffer.getvalue(),
        mime_type="image/jpeg"
    )

    vision_prompt = """
You are CivicLens, an AI assistant for identifying
and reporting civic problems.

Analyze this image carefully.

Identify:
1. What civic problem is visible?
2. Which civic category does it belong to?
3. How severe is the problem?
4. What priority score should it receive from 1 to 10?
5. Which department should handle it?
6. Give a detailed description.
7. What risks does the problem create?
8. What action should be taken?

Return valid JSON only.

Use exactly this structure:

{
    "problem": "string",
    "category": "string",
    "severity": "Low|Medium|High|Critical",
    "priority_score": 1,
    "responsible_department": "string",
    "description": "string",
    "risk": "string",
    "recommended_action": "string"
}

Do not invent details that cannot be identified
from the photograph.
"""

    response = gemini_generate(
        model=GEMINI_MODEL,
        contents=[
            vision_prompt,
            image_part
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )

    raw = (response.text or "").strip()

    # Some models wrap JSON in ```json fences even when told not to.
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

    return clean_analysis(json.loads(raw))


# ============================================================
# CIVICLENS AGENT
# ============================================================

def run_civiclens_agent(
    report,
    latitude,
    longitude
):
    """
    Run the CivicLens Gemini agent.

    Agent responsibilities:

    1. Check nearby reports.
    2. Detect possible duplicate.
    3. Update existing report when appropriate.
    4. Save a new report when no matching report exists.
    """

    # --------------------------------------------------------
    # Check nearby reports ourselves first.
    #
    # This guarantees the backend has the information
    # even if Gemini decides not to call the tool.
    # --------------------------------------------------------

    nearby_result = find_nearby_reports(
        latitude=latitude,
        longitude=longitude,
        radius_km=1
    )

    # A report the admin already marked Resolved is closed. If the same
    # kind of problem shows up there again it is a NEW problem, so closed
    # reports are not offered to the agent as duplicates.
    nearby_reports = [
        r for r in nearby_result["reports"]
        if r.get("status") != "Resolved"
    ]

    # --------------------------------------------------------
    # Prepare tools for Gemini
    # --------------------------------------------------------

    civic_tools = [

        types.Tool(

            function_declarations=[

                types.FunctionDeclaration(

                    name="find_nearby_reports",

                    description="""
Find previously reported civic problems near
a given latitude and longitude.

Use this before creating a new report to
check whether a similar problem already exists.
""",

                    parameters=types.Schema(

                        type=types.Type.OBJECT,

                        properties={

                            "latitude": types.Schema(
                                type=types.Type.NUMBER
                            ),

                            "longitude": types.Schema(
                                type=types.Type.NUMBER
                            ),

                            "radius_km": types.Schema(
                                type=types.Type.NUMBER
                            )
                        },

                        required=[
                            "latitude",
                            "longitude"
                        ]
                    )
                ),

                types.FunctionDeclaration(

                    name="save_civic_report",

                    description="""
Save a new civic problem report.
Use this only when a matching report
does not already exist.
""",

                    parameters=types.Schema(

                        type=types.Type.OBJECT,

                        properties={

                            "problem": types.Schema(
                                type=types.Type.STRING
                            ),

                            "category": types.Schema(
                                type=types.Type.STRING
                            ),

                            "severity": types.Schema(
                                type=types.Type.STRING
                            ),

                            "priority_score": types.Schema(
                                type=types.Type.INTEGER
                            ),

                            "responsible_department": types.Schema(
                                type=types.Type.STRING
                            ),

                            "description": types.Schema(
                                type=types.Type.STRING
                            ),

                            "risk": types.Schema(
                                type=types.Type.STRING
                            ),

                            "recommended_action": types.Schema(
                                type=types.Type.STRING
                            ),

                            "latitude": types.Schema(
                                type=types.Type.NUMBER
                            ),

                            "longitude": types.Schema(
                                type=types.Type.NUMBER
                            )
                        },

                        required=[
                            "problem",
                            "category",
                            "severity",
                            "priority_score",
                            "responsible_department",
                            "description",
                            "risk",
                            "recommended_action",
                            "latitude",
                            "longitude"
                        ]
                    )
                ),

                types.FunctionDeclaration(

                    name="update_civic_report",

                    description="""
Update an existing civic report when
new information adds value.
""",

                    parameters=types.Schema(

                        type=types.Type.OBJECT,

                        properties={

                            "report_id": types.Schema(
                                type=types.Type.INTEGER
                            ),

                            "additional_information": types.Schema(
                                type=types.Type.STRING
                            ),

                            "new_severity": types.Schema(
                                type=types.Type.STRING
                            ),

                            "new_priority_score": types.Schema(
                                type=types.Type.INTEGER
                            )
                        },

                        required=[
                            "report_id",
                            "additional_information"
                        ]
                    )
                )
            ]
        )
    ]

    # --------------------------------------------------------
    # Agent messages
    # --------------------------------------------------------

    system_prompt = """

You are CivicLens, an AI civic issue analysis assistant.

Analyze the submitted image and return concise, factual results.

Return ONLY these fields:
- problem: Short issue name.
- category: Issue category.
- severity: Low, Medium, or High.
- priority_score: 1–10.
- responsible_department: Relevant department.
- description: Maximum 2 short sentences.
- risk: Maximum 1 short sentence.
- recommended_action: Maximum 2 short sentences.

Rules:
- Do not provide lengthy explanations.
- Do not repeat information.
- Do not reveal internal reasoning.
- Do not invent facts that cannot be verified from the image.
- Use simple English.
- Return valid JSON only.
"""

    contents = [

        types.Content(

            role="user",

            parts=[

                types.Part.from_text(

                    text=f"""
Process this CivicLens report:

{json.dumps(report, indent=2)}

Current location:

Latitude: {latitude}
Longitude: {longitude}

Nearby reports already found by CivicLens:

{json.dumps(nearby_reports, indent=2)}

Determine whether this should create a new report
or update an existing report.
"""
                )
            ]
        )
    ]

    # --------------------------------------------------------
    # Agent loop
    # --------------------------------------------------------

    max_iterations = 5

    action = None
    report_id = None

    for iteration in range(max_iterations):

        print(
            f"\n========== AGENT ITERATION "
            f"{iteration + 1} =========="
        )

        # While nothing has been created or updated yet, Gemini must
        # choose between saving a new report and updating an existing
        # one (the nearby reports are already in the prompt).
        # Afterwards it may answer freely.
        #
        # To let Gemini decide completely on its own, replace this
        # block with:  mode=types.FunctionCallingConfigMode.AUTO
        if action is None:

            function_calling_config = types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=[
                    "save_civic_report",
                    "update_civic_report"
                ]
            )

        else:

            function_calling_config = types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.AUTO
            )

        response = gemini_generate(

            model=GEMINI_MODEL,

            contents=contents,

            config=types.GenerateContentConfig(

                system_instruction=system_prompt,

                tools=civic_tools,

                tool_config=types.ToolConfig(
                    function_calling_config=function_calling_config
                ),

                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                )
            )
        )

        # Keep Gemini's whole reply in the conversation unchanged
        # (it carries the thought signatures Gemini needs next turn).
        contents.append(response.candidates[0].content)

        function_calls = response.function_calls

        # ----------------------------------------------------
        # Agent finished
        # ----------------------------------------------------

        if not function_calls:

            return {
                "success": True,

                "action": action or "completed",

                "report_id": report_id,

                "final_response":
                    response.text,

                "nearby_reports":
                    nearby_reports
            }

        # ----------------------------------------------------
        # Execute requested tools
        # ----------------------------------------------------

        function_response_parts = []

        for function_call in function_calls:

            function_name = function_call.name

            # Gemini returns the arguments as an object,
            # not as a JSON string.
            arguments = dict(function_call.args or {})

            # Whole numbers can arrive as 8.0 - keep them as integers.
            for key in (
                "priority_score",
                "new_priority_score",
                "report_id"
            ):
                if (
                    isinstance(arguments.get(key), float)
                    and arguments[key].is_integer()
                ):
                    arguments[key] = int(arguments[key])

            print(
                f"Gemini requested tool: "
                f"{function_name}"
            )

            print(
                json.dumps(
                    arguments,
                    indent=2
                )
            )

            # ------------------------------------------------
            # Find nearby reports
            # ------------------------------------------------

            if function_name == "find_nearby_reports":

                result = find_nearby_reports(
                    latitude=arguments["latitude"],
                    longitude=arguments["longitude"],
                    radius_km=arguments.get(
                        "radius_km",
                        1
                    )
                )

            # ------------------------------------------------
            # Save report
            # ------------------------------------------------

            elif function_name == "save_civic_report":

                result = save_civic_report(
                    **arguments
                )

                if result["success"]:

                    action = "created"

                    report_id = (
                        result["report_id"]
                    )

            # ------------------------------------------------
            # Update report
            # ------------------------------------------------

            elif function_name == "update_civic_report":

                result = update_civic_report(
                    **arguments
                )

                if result["success"]:

                    action = "updated"

                    report_id = (
                        result["report_id"]
                    )

            # ------------------------------------------------
            # Unknown tool
            # ------------------------------------------------

            else:

                result = {
                    "success": False,
                    "error":
                        f"Unknown tool: "
                        f"{function_name}"
                }

            print(
                "Tool result:",
                json.dumps(
                    result,
                    indent=2
                )
            )

            # ------------------------------------------------
            # Send result back to Gemini
            # ------------------------------------------------

            function_response_parts.append(

                types.Part.from_function_response(

                    name=function_name,

                    response={"result": result}
                )
            )

        contents.append(

            types.Content(

                role="user",

                parts=function_response_parts
            )
        )

    # --------------------------------------------------------
    # Maximum iterations reached
    # --------------------------------------------------------

    return {

        "success": False,

        "action": action,

        "report_id": report_id,

        "final_response":
            "CivicLens agent reached "
            "the maximum number of steps.",

        "nearby_reports":
            nearby_reports
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "message":
            "CivicLens AI Backend is running!",

        "status":
            "online"
    })


@app.route("/health")
def health():

    return jsonify({

        "status":
            "healthy",

        "service":
            "CivicLens AI Backend",

        "model":
            GEMINI_MODEL,

        "reports_saved":
            len(civic_reports),

        "admin_configured":
            admin_configured()
    })



# ============================================================
# ANALYZE IMAGE API
# ============================================================

# Remembers finished submissions for 10 minutes, keyed by an id the
# browser generates per click. If the browser retries after a dropped
# connection, it gets the SAME answer instead of creating or updating a
# report a second time.
_recent_submissions = {}

SUBMISSION_TTL_SECONDS = 600


def _remember_submission(request_id, payload):

    now = time.time()

    for key in [
        k for k, (t, _) in _recent_submissions.items()
        if now - t > SUBMISSION_TTL_SECONDS
    ]:
        _recent_submissions.pop(key, None)

    _recent_submissions[request_id] = (now, payload)


@app.route("/analyze", methods=["POST"])
def analyze():

    try:

        request_id = (
            request.form.get("client_request_id", "").strip()[:64]
        )

        if request_id and request_id in _recent_submissions:

            _, cached = _recent_submissions[request_id]

            cached = dict(cached)

            cached["reports"] = [
                public_report(r) for r in civic_reports
            ]

            return jsonify(cached)

        # ----------------------------------------------------
        # Check image
        # ----------------------------------------------------

        if "image" not in request.files:

            return jsonify({
                "success": False,
                "error": "No image uploaded."
            }), 400

        image = request.files["image"]

        if (
            image.mimetype
            and not image.mimetype.startswith("image/")
        ):

            return jsonify({
                "success": False,
                "error": "Please upload an image file."
            }), 400

        if image.filename == "":

            return jsonify({
                "success": False,
                "error": "No image selected."
            }), 400

        # ----------------------------------------------------
        # Get GPS coordinates from frontend
        # ----------------------------------------------------

        latitude = request.form.get(
            "latitude",
            type=float
        )

        longitude = request.form.get(
            "longitude",
            type=float
        )

        accuracy = request.form.get(
            "accuracy",
            type=float
        )

        print("\n========== LOCATION ==========")
        print("Frontend Latitude:", latitude)
        print("Frontend Longitude:", longitude)
        print("Frontend Accuracy:", accuracy)

        # ----------------------------------------------------
        # Get location
        # ----------------------------------------------------

        location_result = get_location(
            latitude=latitude,
            longitude=longitude
        )

        location = location_result["location"]

        # Get final coordinates
        latitude = location["latitude"]
        longitude = location["longitude"]

        print("Final Latitude:", latitude)
        print("Final Longitude:", longitude)

        # ----------------------------------------------------
        # GEMINI VISION
        # ----------------------------------------------------

        print(
            "\n========== GEMINI VISION ==========\n"
        )

        report = analyze_image_with_gemini(
            image
        )

        print(
            json.dumps(
                report,
                indent=2
            )
        )

        # ----------------------------------------------------
        # Add COMPLETE location to report
        # ----------------------------------------------------

        report["location"] = {

            "latitude": latitude,

            "longitude": longitude,

            "accuracy": accuracy,

            "address": location.get(
                "address"
            ),

            "address_details":
                location.get(
                    "address_details",
                    {}
                )
        }

        # ----------------------------------------------------
        # CIVICLENS AGENT
        # ----------------------------------------------------

        print(
            "\n========== CIVICLENS AGENT ==========\n"
        )

        try:

            agent_result = run_civiclens_agent(

                report=report,

                latitude=latitude,

                longitude=longitude
            )

        except Exception as agent_error:

            print(f"Agent failed: {agent_error!r}")

            agent_result = {
                "success": False,
                "action": None,
                "report_id": None,
                "final_response": str(agent_error),
                "nearby_reports": []
            }

        # Safety net: if the agent could not save or update anything
        # (rate limit, max steps, bad tool call) the citizen's photo is
        # still saved as a new report, so a submission is never lost.
        if agent_result.get("report_id") is None:

            print("Agent saved nothing - saving the report directly.")

            fallback = save_civic_report(
                problem=report["problem"],
                category=report["category"],
                severity=report["severity"],
                priority_score=report["priority_score"],
                responsible_department=report[
                    "responsible_department"
                ],
                description=report["description"],
                risk=report["risk"],
                recommended_action=report["recommended_action"],
                latitude=latitude,
                longitude=longitude
            )

            agent_result["report_id"] = fallback["report_id"]

            agent_result["action"] = "created"

            agent_result["success"] = True

        # ----------------------------------------------------
        # Keep the address and the photo for the admin inbox
        # ----------------------------------------------------

        attach_evidence(
            agent_result.get("report_id"),
            location.get("address"),
            image
        )

        # ----------------------------------------------------
        # RETURN TO NEXT.JS
        # ----------------------------------------------------

        payload = {

            "success": True,

            "analysis": report,

            "agent": agent_result,

            "location": location,

            "reports": [
                public_report(r) for r in civic_reports
            ]

        }

        if request_id:
            _remember_submission(request_id, payload)

        return jsonify(payload)

    except Exception as e:

        print(
            "\n========== ERROR ==========\n"
        )

        print(
            str(e)
        )

        return jsonify({

            "success": False,

            "error": str(e)

        }), 500

# ============================================================
# GET ALL REPORTS
# ============================================================

@app.route(
    "/reports",
    methods=["GET"]
)
def get_reports():

    return jsonify({

        "success": True,

        "count":
            len(civic_reports),

        "reports":
            [public_report(r) for r in civic_reports]
    })


# ============================================================
# ADMIN SYSTEM
# ============================================================
#
# Authentication is verified HERE, on the server:
#
#   * The password is never stored - only a salted hash
#     (ADMIN_PASSWORD_HASH, made by setup_admin.py).
#   * POST /admin/login checks username + password and returns a
#     signed token that expires after ADMIN_SESSION_HOURS.
#   * Every other /admin/... route requires that token in the
#     "Authorization: Bearer <token>" header. Without a valid one
#     the server answers 401, no matter what the frontend does.

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")

ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")

ADMIN_SESSION_HOURS = 8

ADMIN_STATUSES = ["Pending", "In Progress", "Resolved"]

LOGIN_MAX_FAILURES = 5

LOGIN_WINDOW_SECONDS = 600

_login_failures = {}


def safe_equals(a, b):
    """Constant-time comparison that also accepts non-ASCII text."""

    return hmac.compare_digest(
        str(a).encode("utf-8"),
        str(b or "").encode("utf-8")
    )


def admin_configured():

    return bool(
        ADMIN_USERNAME
        and ADMIN_PASSWORD_HASH
        and ADMIN_SECRET_KEY
    )


def client_ip():
    """
    Visitor IP. Behind PythonAnywhere's proxy the LAST entry of
    X-Forwarded-For is the one the proxy itself added.
    """

    forwarded = request.headers.get("X-Forwarded-For", "")

    if forwarded:
        return forwarded.split(",")[-1].strip()

    return request.remote_addr or "unknown"


def recent_failures(ip):

    now = time.time()

    attempts = [
        t for t in _login_failures.get(ip, [])
        if now - t < LOGIN_WINDOW_SECONDS
    ]

    _login_failures[ip] = attempts

    return attempts


def token_serializer():

    return URLSafeTimedSerializer(
        ADMIN_SECRET_KEY,
        salt="civiclens-admin-session"
    )


def create_admin_token(username):

    return token_serializer().dumps({"u": username})


def verify_admin_token(token):
    """Return the admin username if the token is valid, else None."""

    try:
        data = token_serializer().loads(
            token,
            max_age=ADMIN_SESSION_HOURS * 3600
        )
    except BadSignature:
        # also covers expired tokens
        return None

    username = str(data.get("u", ""))

    if not safe_equals(username, ADMIN_USERNAME):
        return None

    return username


def admin_required(view):

    @wraps(view)
    def wrapper(*args, **kwargs):

        if not admin_configured():
            return jsonify({
                "success": False,
                "error": "Admin access is not configured on this server."
            }), 503

        header = request.headers.get("Authorization", "")

        if not header.startswith("Bearer "):
            return jsonify({
                "success": False,
                "error": "Login required."
            }), 401

        username = verify_admin_token(header[7:].strip())

        if username is None:
            return jsonify({
                "success": False,
                "error": "Session expired or invalid. Please log in again."
            }), 401

        g.admin_username = username

        return view(*args, **kwargs)

    return wrapper


def admin_report(saved_report):
    """Full report for the admin inbox."""

    out = dict(saved_report)

    out["photo_count"] = saved_report.get("photo_count", 0)

    return out


@app.route("/admin/login", methods=["POST"])
def admin_login():

    if not admin_configured():
        return jsonify({
            "success": False,
            "error": "Admin access is not configured on this server."
        }), 503

    ip = client_ip()

    if len(recent_failures(ip)) >= LOGIN_MAX_FAILURES:
        return jsonify({
            "success": False,
            "error": "Too many failed attempts. Try again in 10 minutes."
        }), 429

    body = request.get_json(silent=True) or {}

    username = str(body.get("username", ""))

    password = str(body.get("password", ""))

    # Always check the hash (even for a wrong username) so response
    # time does not reveal whether the username exists.
    password_ok = check_password_hash(ADMIN_PASSWORD_HASH, password)

    username_ok = safe_equals(username, ADMIN_USERNAME)

    if not (password_ok and username_ok):

        _login_failures.setdefault(ip, []).append(time.time())

        time.sleep(0.4)

        return jsonify({
            "success": False,
            "error": "Invalid username or password."
        }), 401

    _login_failures.pop(ip, None)

    return jsonify({
        "success": True,
        "token": create_admin_token(ADMIN_USERNAME),
        "username": ADMIN_USERNAME,
        "expires_in_hours": ADMIN_SESSION_HOURS
    })


@app.route("/admin/me", methods=["GET"])
@admin_required
def admin_me():

    return jsonify({
        "success": True,
        "username": g.admin_username
    })


@app.route("/admin/reports", methods=["GET"])
@admin_required
def admin_list_reports():

    reports = sorted(
        civic_reports,
        key=lambda r: r.get("created_at", ""),
        reverse=True
    )

    return jsonify({
        "success": True,
        "count": len(reports),
        "reports": [admin_report(r) for r in reports]
    })


@app.route("/admin/reports/<int:report_id>/photo", methods=["GET"])
@admin_required
def admin_report_photo(report_id):

    saved_report = find_report(report_id)

    n = request.args.get("n", default=0, type=int)

    if (
        saved_report is None
        or n < 0
        or n >= saved_report.get("photo_count", 0)
        or not os.path.exists(photo_path(report_id, n))
    ):
        return jsonify({
            "success": False,
            "error": "No photo."
        }), 404

    with open(photo_path(report_id, n), "rb") as f:
        data = f.read()

    return Response(
        data,
        mimetype="image/jpeg",
        headers={"Cache-Control": "private, max-age=600"}
    )


@app.route("/admin/reports/<int:report_id>/status", methods=["PATCH"])
@admin_required
def admin_update_status(report_id):

    body = request.get_json(silent=True) or {}

    new_status = body.get("status")

    if new_status not in ADMIN_STATUSES:
        return jsonify({
            "success": False,
            "error": f"Status must be one of {ADMIN_STATUSES}."
        }), 400

    note = str(body.get("note", "")).strip()[:300]

    with _store_lock:

        saved_report = find_report(report_id)

        if saved_report is None:
            return jsonify({
                "success": False,
                "error": f"Report {report_id} not found."
            }), 404

        now_iso = datetime.now(timezone.utc).isoformat()

        saved_report["status"] = new_status

        saved_report.setdefault("status_history", []).append({
            "status": new_status,
            "at": now_iso,
            "note": note,
            "by": g.admin_username
        })

        if new_status == "Resolved":
            saved_report["resolved_at"] = now_iso
        else:
            saved_report.pop("resolved_at", None)

        persist_reports()

        return jsonify({
            "success": True,
            "report": admin_report(saved_report)
        })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    # Local development only.  On PythonAnywhere the WSGI file imports
    # `app` and this block is never executed.
    #
    # debug is OFF by default: with debug=True and host=0.0.0.0 anybody on
    # the same Wi-Fi can open the Werkzeug debugger and run code on your
    # PC, and the auto-reloader can restart the server in the middle of a
    # request (the browser then shows "Failed to fetch").
    # Turn it on only when you need it:  set FLASK_DEBUG=1

    debug_mode = os.getenv("FLASK_DEBUG") == "1"

    port = int(os.getenv("PORT", "5000"))

    print("\n========================================")
    print("       CIVICLENS AI BACKEND")
    print("========================================")
    print(f"Gemini model: {GEMINI_MODEL}")
    print(f"Server:       http://127.0.0.1:{port}")
    print(f"Debug mode:   {debug_mode}")
    print(f"Admin login:  {'configured' if admin_configured() else 'NOT configured - run setup_admin.py'}")
    print("========================================\n")

    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        debug=debug_mode,
        use_reloader=False
    )
