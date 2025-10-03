# utils/ai_client.py
import os
from google import genai
from google.genai import types

# Ưu tiên env GOOGLE_API_KEY, sau đó GEMINI_API_KEY (SDK đã hỗ trợ)
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("Missing GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

# Model names có thể override qua env
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gemini-2.0-flash-001")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")