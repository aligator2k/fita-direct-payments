"""
Lightweight Gemini client using direct HTTP requests.
Falls back across multiple models if one hits a quota limit,
retries transient errors with exponential backoff.
Remembers which model worked last and tries it first next time.
"""

import os
import time
import logging
import requests

log = logging.getLogger(__name__)

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30

# Module-level state: index into MODELS that worked last
_preferred_index = 0


class GeminiError(RuntimeError):
    pass


def _try_model(model, payload, headers, api_key):
    """Try a single model. Returns (text, True) on success, (None, False) on quota/auth,
    (None, None) on giving up after retries."""
    url = f"{BASE_URL}/{model}:generateContent?key={api_key}"

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)

            if r.status_code == 200:
                try:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"], True
                except (KeyError, IndexError) as e:
                    log.error(f"[{model}] parse error: {e}")
                    return None, None

            if r.status_code in (429, 403):
                return None, False

            if r.status_code >= 500:
                wait = 2 ** attempt
                log.warning(f"[{model}] server error {r.status_code}, retry {attempt + 1}/{MAX_RETRIES}")
                time.sleep(wait)
                continue

            log.error(f"[{model}] fatal {r.status_code}: {r.text[:200]}")
            raise GeminiError(f"Gemini {r.status_code}")

        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            log.warning(f"[{model}] network error: {type(e).__name__}, retry {attempt + 1}/{MAX_RETRIES}")
            time.sleep(wait)
            continue

    return None, None


def ask_gemini(prompt: str) -> str:
    global _preferred_index

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY not set in environment")

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"Content-Type": "application/json"}

    # Try preferred model first, then walk through the rest in order
    order = [_preferred_index] + [i for i in range(len(MODELS)) if i != _preferred_index]

    for idx in order:
        model = MODELS[idx]
        text, ok = _try_model(model, payload, headers, api_key)
        if ok:
            _preferred_index = idx
            return text
        if ok is False:
            log.info(f"[{model}] quota hit, falling back")

    raise GeminiError("All Gemini models failed or hit quota")