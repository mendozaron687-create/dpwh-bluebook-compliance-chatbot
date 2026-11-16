"""Minimal OpenRouter client."""
import time

import httpx

from config import OPENROUTER_API_KEY, OPENROUTER_EMBED_URL, OPENROUTER_URL


def _headers():
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set (put it in chatbot/.env)")
    return {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}


def chat(model, messages, temperature=0.0, max_tokens=800, retries=3):
    """Returns (text, seconds)."""
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    last = None
    for attempt in range(retries):
        start = time.perf_counter()
        try:
            r = httpx.post(OPENROUTER_URL, headers=_headers(), json=payload, timeout=90)
            r.raise_for_status()
            elapsed = time.perf_counter() - start
            return r.json()["choices"][0]["message"]["content"] or "", elapsed
        except (httpx.HTTPError, KeyError, IndexError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"OpenRouter call failed for {model}: {last}")


def embed(model, texts):
    r = httpx.post(OPENROUTER_EMBED_URL, headers=_headers(), json={"model": model, "input": texts}, timeout=90)
    r.raise_for_status()
    return [d["embedding"] for d in r.json()["data"]]
