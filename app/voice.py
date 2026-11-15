"""ElevenLabs voice: read-aloud (text-to-speech) and speech-to-text for check-ins. Optional: available() is False without a key."""
import os

import functools

import requests

from app import llm  # noqa: F401  (loads .env for local runs)

VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah, mature and reassuring (premade)
API = "https://api.elevenlabs.io/v1"


def available():
    return bool(os.getenv("ELEVENLABS_API_KEY"))


@functools.lru_cache(maxsize=256)
def speak(text):
    """Return mp3 bytes, or None if the service is unreachable."""
    try:
        r = requests.post(f"{API}/text-to-speech/{VOICE_ID}?output_format=mp3_44100_64",
                          headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
                          json={"text": text, "model_id": "eleven_multilingual_v2"}, timeout=40)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def transcribe(audio_bytes, filename="answer.wav", mime="audio/wav"):
    """Return (text, language_code) or (None, None)."""
    try:
        r = requests.post(f"{API}/speech-to-text", headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
                          data={"model_id": "scribe_v1"}, files={"file": (filename, audio_bytes, mime)}, timeout=60)
        r.raise_for_status()
        j = r.json()
        return (j.get("text") or "").strip() or None, j.get("language_code")
    except Exception:
        return None, None


# Map a spoken answer to Yes / Not sure / No. Unclear speech maps to "Not sure" so a person follows up.
_YES = ("yes", "yeah", "yep", "kyllä", "joo", "ja", "نعم", "أجل", "iya")
_NO = ("no", "nope", "ei", "nej", "لا")
_UNSURE = ("not sure", "don't know", "dont know", "maybe", "en tiedä", "vet inte", "لست متأكد", "لا أعرف")


def classify(text):
    t = (text or "").lower().strip(" .!?؟")
    if any(u in t for u in _UNSURE):
        return "Not sure"
    words = set(t.replace(",", " ").split())
    if words & set(_NO) and not words & set(_YES):
        return "No"
    if words & set(_YES) and not words & set(_NO):
        return "Yes"
    return "Not sure"
