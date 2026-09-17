import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY or API_KEY == "your_api_key_here":
    print("")
    print("ERROR: GEMINI_API_KEY is not configured.")
    print("")
    print("Open .env and add your Gemini API key.")
    print("")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

print("")
print("=" * 50)
print("VideoAIEngine - Gemini Connection Test")
print("=" * 50)
print("")

try:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents="Answer in one short sentence: Gemini connection works."
    )

    print("SUCCESS")
    print("")
    print(response.text)
    print("")
    print("=" * 50)

except Exception as e:
    print("")
    print("ERROR")
    print("")
    print(str(e))
    print("")
    print("=" * 50)
