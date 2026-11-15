"""One helper: llm(prompt) -> (text, engine) or (None, 'offline').
Chain: Verda Nemotron -> Gemini Flash Lite -> Featherless Gemma 4 31B -> Gemma E4B -> Qwen -> caller's template.
Keys come from the environment (Modal secret 'hoitovirta' or local .env). Keys are never logged."""
import os
import time

import requests

try:  # local runs only; on Modal the secret is already in the environment
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

FEATHERLESS_URL = "https://api.featherless.ai/v1"
PROVIDER_TIMEOUT_SECONDS = 4
CHAIN_TIMEOUT_SECONDS = 8


def _chat(url, key, model, messages, max_tokens, timeout, extra=None):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
    body.update(extra or {})
    r = requests.post(url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=timeout)
    r.raise_for_status()
    text = (r.json()["choices"][0]["message"].get("content") or "").strip()
    return text or None


def llm(prompt, system=None, max_tokens=500, deadline=None):
    """Return (text, engine); cap each provider attempt at 4s and the whole chain at 8s."""
    started = time.monotonic()
    def timeout_left():
        return min(PROVIDER_TIMEOUT_SECONDS, CHAIN_TIMEOUT_SECONDS - (time.monotonic() - started))
    def budget_remaining():
        local = CHAIN_TIMEOUT_SECONDS - (time.monotonic() - started)
        return min(local, deadline - time.monotonic()) if deadline is not None else local
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    key, base, model = os.getenv("VERDA_INFERENCE_KEY"), os.getenv("VERDA_BASE_URL"), os.getenv("VERDA_MODEL")
    if key and base and model and budget_remaining() > 0:
        try:
            t = _chat(base, key, model, msgs, max_tokens, timeout_left(), {"chat_template_kwargs": {"enable_thinking": False}})
            if t:
                return t, "Nemotron"
        except Exception:
            pass
    gkey = os.getenv("GEMINI_API_KEY")
    if gkey and budget_remaining() > 0:
        try:
            structured = "JSON only" in prompt or "JSON-only" in prompt or "json only" in prompt.lower()
            generation = {"temperature": 0.2, "maxOutputTokens": max_tokens}
            if structured:
                generation["responseMimeType"] = "application/json"
                generation["responseSchema"] = {
                    "type": "OBJECT", "properties": {
                        "reply": {"type": "STRING"}, "intent": {"type": "STRING"},
                        "need": {"type": "STRING", "nullable": True}, "escalate": {"type": "STRING"},
                        "sources": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "offer_buttons": {"type": "ARRAY", "items": {"type": "STRING"}},
                    }, "required": ["reply", "intent", "need", "escalate", "sources", "offer_buttons"]}
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": generation}
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
                headers={"x-goog-api-key": gkey, "Content-Type": "application/json"},
                json=body, timeout=timeout_left())
            response.raise_for_status()
            candidates = response.json().get("candidates", [])
            content = "".join(part.get("text", "") for part in (candidates[0].get("content", {}).get("parts", []) if candidates else [])).strip()
            if content:
                return content, "Gemini"
        except Exception:
            pass
    fkey = os.getenv("FEATHERLESS_API_KEY")
    if fkey:
        for model_name, provider_name, env_name, default in (
            ("gemma31", "Gemma 31B", "FEATHERLESS_GEMMA_MODEL", "google/gemma-4-31B-it"),
            ("gemma_e4b", "Gemma E4B", "FEATHERLESS_GEMMA_E4B_MODEL", "google/gemma-4-E4B-it"),
            ("qwen", "Featherless", "FEATHERLESS_MODEL", "Qwen/Qwen3.8-Flash-Next"),
        ):
            if budget_remaining() <= 0:
                break
            try:
                t = _chat(FEATHERLESS_URL, fkey, os.getenv(env_name, default), msgs, max_tokens, timeout_left())
                if t:
                    return t, provider_name
            except Exception:
                pass
    return None, "offline"
