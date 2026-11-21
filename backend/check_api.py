"""
CivicLens - check the Gemini API connection.

    python check_api.py

Runs the same three things the app does (text, photo -> JSON, tool calling)
and says in plain words what is wrong if one fails.
"""

import io
import json
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GEMINI_MODEL = "gemini-3.1-flash-lite"   # keep the same as app.py


def explain(error):
    text = str(error)
    low = text.lower()

    if "api key not valid" in low or "api_key_invalid" in low or "401" in low or "403" in low:
        return "The key was rejected (or the API is not allowed for it). Create a new key in Google AI Studio."
    if "429" in low or "quota" in low or "resource_exhausted" in low:
        return "Rate limit or free quota reached. Wait a minute and try again."
    if "404" in low or "not found" in low:
        return f"The model '{GEMINI_MODEL}' was not found for this key."
    if "connect" in low or "timeout" in low or "resolve" in low or "tunnel" in low:
        return "Could not reach Google. Check the internet connection (PythonAnywhere free accounts only reach an allow-list of sites)."

    return text


def step(name, fn):
    print(f"- {name} ... ", end="", flush=True)

    try:
        print(f"OK  ({fn()})")
        return True
    except Exception as e:
        print("FAILED")
        print(f"    {explain(e)}")
        return False


def main():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY is missing.")
        print("Add this line to backend/.env :  GEMINI_API_KEY=your-key")
        sys.exit(1)

    base_url = os.getenv("GEMINI_BASE_URL")   # only used for testing

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(base_url=base_url) if base_url else None
    )

    print(f"Model: {GEMINI_MODEL}")
    print(f"Key:   {api_key[:4]}...{api_key[-4:]}\n")

    def text_call():
        r = client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Reply with the single word: ready"
        )
        return (r.text or "").strip()[:40]

    def vision_call():
        img = Image.new("RGB", (320, 240), (90, 90, 95))
        ImageDraw.Draw(img).ellipse((100, 80, 220, 170), fill=(20, 20, 20))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")

        r = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                'This is a test picture of a road. Return ONLY JSON like {"problem": "..."}',
                types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        json.loads(r.text)
        return "image understood, valid JSON"

    def tool_call():
        tool = types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="find_nearby_reports",
                description="Find civic reports near a location",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "latitude": types.Schema(type=types.Type.NUMBER),
                        "longitude": types.Schema(type=types.Type.NUMBER),
                    },
                    required=["latitude", "longitude"],
                ),
            )
        ])
        r = client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Use the tool to look for reports near latitude 34.01, longitude 71.52.",
            config=types.GenerateContentConfig(
                tools=[tool],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        calls = r.function_calls
        if not calls:
            raise RuntimeError("the model did not call the tool")
        return f"agent tool call: {calls[0].name}"

    results = [
        step("Text request", text_call),
        step("Vision request (photo -> JSON)", vision_call),
        step("Agent tool-calling", tool_call),
    ]

    print()
    if all(results):
        print("All good - CivicLens can talk to Gemini.")
    else:
        print("Something needs fixing (see above), then run this again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
