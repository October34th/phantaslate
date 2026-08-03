"""
Phantaslate Relay
=================
A stateless translation relay. It receives text, calls one LLM API, returns the
translation, and stores nothing. There is no database and no logging of request
content — by design. What you read here is what runs.

  Extension  ->  Relay  ->  LLM API  ->  translation  ->  Extension renders
  Website    ->  Relay  ->  LLM API  ->  translation  ->  Website renders
                   |
                   +-- stores nothing

Two clients, one relay. They are told apart by the Origin header and given
different caps (see PROFILES below). Nothing else about their handling
differs — same statelessness, same provider, same no-logging promise.

Configuration (environment variables):
  DEEPSEEK_API_KEY    required — your DeepSeek API key
  PHANTASLATE_MODEL   optional — model name (default: deepseek-v4-flash)
  DEEPSEEK_BASE_URL   optional — API base (default: https://api.deepseek.com)
  PHANTASLATE_ORIGINS optional — comma-separated allowed EXTENSION origins
                                 (chrome-extension://... ids)
  PHANTASLATE_WEB_ORIGINS optional — comma-separated allowed WEBSITE origins
                                 (default: https://phantaslate.com and www)

Rate limiting (see ratelimit.py):
  PHANTASLATE_SALT_SECRET    set in production — otherwise quotas reset on
                             every deploy
  PHANTASLATE_DAILY_CHARS      optional — per-install daily cap (default 20000)
  PHANTASLATE_WEB_DAILY_CHARS  optional — per-website-session cap (default 5000)
  PHANTASLATE_WEB_MAX_CHARS    optional — per-request cap on the website
                               (default 1000; the extension keeps 5000)
  PHANTASLATE_IP_MULTIPLIER    optional — network ceiling multiple (default 5)
"""

import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from ratelimit import limiter, client_ip

# --- Configuration -----------------------------------------------------------

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("PHANTASLATE_MODEL", "deepseek-v4-flash")
ORIGINS = [o.strip() for o in os.environ.get("PHANTASLATE_ORIGINS", "*").split(",") if o.strip()]

# The website's own origins. Kept separate from PHANTASLATE_ORIGINS so that
# adding the site cannot accidentally widen what counts as the extension —
# the two get different caps, and the distinction is drawn from this list.
WEB_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "PHANTASLATE_WEB_ORIGINS",
        "https://phantaslate.com,https://www.phantaslate.com",
    ).split(",")
    if o.strip()
}

# Per-request ceilings. The extension handles longer passages; the website is
# a try-before-you-install surface and is capped lower.
MAX_CHARS = 5000
WEB_MAX_CHARS = int(os.environ.get("PHANTASLATE_WEB_MAX_CHARS", "1000"))

REQUEST_TIMEOUT = 30.0

# Language codes the extension sends -> names the model understands.
LANGUAGE_NAMES = {
    "en": "English",
    "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "vi": "Vietnamese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

# --- App ---------------------------------------------------------------------

app = FastAPI(
    title="Phantaslate Relay",
    version="0.1.0",
    description="Stateless, no-logs translation relay.",
)

app.add_middleware(
    CORSMiddleware,
    # Both clients must appear here or the browser blocks them before any of
    # this code runs. A missing website origin shows up as a generic network
    # failure in the browser, not as an error from this relay.
    allow_origins=(ORIGINS if ORIGINS == ["*"] else ORIGINS + sorted(WEB_ORIGINS)),
    allow_methods=["GET", "POST", "OPTIONS"],
    # Both custom headers must be listed, or the browser's preflight rejects
    # the request before it ever reaches the handler. X-Phantaslate-Install
    # is the extension's; X-Phantaslate-Session is the website's.
    allow_headers=["Content-Type", "X-Phantaslate-Install", "X-Phantaslate-Session"],
    # Without expose_headers the extension can send requests fine but cannot
    # *read* the quota headers off the response.
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


class TranslateRequest(BaseModel):
    # Validated against the larger of the two ceilings here; the website's
    # tighter limit is applied in the handler, once the caller is known.
    text: str = Field(..., min_length=1, max_length=MAX_CHARS)
    source_lang: str = "auto"
    target_lang: str = "en"


class TranslateResponse(BaseModel):
    translation: str
    detected_lang: str | None = None
    detected_code: str | None = None
    source_mismatch: bool = False


# Maps the many ways a model may name a language back to our codes. Detection is
# only actionable if we can resolve it to a code we support.
NAME_TO_CODE = {
    "english": "en",
    "simplified chinese": "zh-Hans",
    "chinese simplified": "zh-Hans",
    "mandarin chinese": "zh-Hans",
    "mandarin": "zh-Hans",
    "traditional chinese": "zh-Hant",
    "chinese traditional": "zh-Hant",
    "cantonese": "zh-Hant",
    "japanese": "ja",
    "korean": "ko",
    "vietnamese": "vi",
    "spanish": "es",
    "castilian": "es",
    "french": "fr",
    "german": "de",
}

# "Chinese" without a script is ambiguous — it should not trigger a mismatch
# against either Chinese variant.
AMBIGUOUS_NAMES = {"chinese"}


def normalize_name(name: str) -> str:
    """Lowercase and strip punctuation so 'Chinese (Simplified)' matches."""
    cleaned = re.sub(r"[()\[\],.;:]", " ", (name or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def code_from_name(name: str) -> str | None:
    """Resolve a detected language name to one of our codes, if we recognize it."""
    norm = normalize_name(name)
    if not norm or norm in AMBIGUOUS_NAMES:
        return None
    if norm in NAME_TO_CODE:
        return NAME_TO_CODE[norm]
    # Try the reversed word order, e.g. "chinese, simplified".
    reversed_words = " ".join(reversed(norm.split()))
    return NAME_TO_CODE.get(reversed_words)


def is_mismatch(stated_code: str, detected_name: str) -> tuple[bool, str | None]:
    """Decide whether the detected language contradicts the stated source.

    Returns (mismatch, detected_code). Errs toward reporting no mismatch: an
    unrecognized or ambiguous detection must never raise a false alarm.
    """
    detected_code = code_from_name(detected_name)
    if detected_code is None:
        return False, None
    if stated_code not in LANGUAGE_NAMES:
        return False, detected_code
    return detected_code != stated_code, detected_code


# Marker used to return the detected language alongside the translation when
# source_lang is "auto". Parsing is defensive: if the model ignores the format,
# the whole reply is treated as the translation.
DETECT_SEPARATOR = "---"


LANG_LINE = re.compile(r"^\s*LANG\s*[:：]\s*(.*?)\s*$", re.IGNORECASE)
SEPARATOR_LINE = re.compile(r"^\s*[-–—_=*]{2,}\s*$")
FENCE_LINE = re.compile(r"^\s*```")


def parse_auto_reply(raw: str) -> tuple[str | None, str]:
    """Split a language-tagged reply into (detected_language, translation).

    Models do not follow the requested envelope reliably — the separator line is
    frequently dropped, and replies are sometimes wrapped in code fences. Parsing
    is therefore line-based and forgiving: the tag is honoured wherever it can be
    recognised, and anything unparseable falls back to treating the whole reply
    as the translation, so a formatting slip never costs the user their result.
    """
    text = (raw or "").strip()
    if not text:
        return None, text

    lines = text.split("\n")

    # Drop a leading code fence, and a matching trailing one.
    if lines and FENCE_LINE.match(lines[0]):
        lines = lines[1:]
        while lines and FENCE_LINE.match(lines[-1]):
            lines = lines[:-1]

    # Skip blank lines before the tag.
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines):
        return None, text

    match = LANG_LINE.match(lines[start])
    if not match:
        return None, text

    detected = match.group(1).strip() or None
    rest = lines[start + 1:]

    # Drop separator lines and blank padding between the tag and the translation.
    while rest and (SEPARATOR_LINE.match(rest[0]) or not rest[0].strip()):
        rest.pop(0)
    while rest and not rest[-1].strip():
        rest.pop()

    translation = "\n".join(rest).strip()
    if not translation:
        return None, text

    return detected, translation


def build_system_prompt(source_lang: str, target_lang: str) -> str:
    """Construct an instruction that yields the detected language and translation.

    Detection is requested in every case — including when the user names a source
    language — so a wrong source setting can be caught rather than silently
    trusted.
    """
    target = LANGUAGE_NAMES.get(target_lang, target_lang)
    common = (
        "Do not add explanations, notes, labels, or surrounding quotation marks. "
        "Preserve line breaks, numbers, and inline formatting. If the text is "
        "already in the target language, return it unchanged."
    )
    envelope = (
        "Reply in exactly this format and nothing else:\n"
        "LANG: <the name of the language the message is actually written in, in English>\n"
        f"{DETECT_SEPARATOR}\n"
        "<the translated text>\n"
        "The language name must always be in English (for example: Japanese, "
        "not 日本語). "
    )

    if source_lang == "auto" or source_lang not in LANGUAGE_NAMES:
        return (
            "You are Phantaslate, a translation engine. Detect the language of the "
            f"user's message and translate it into {target}. " + envelope + common
        )

    source = LANGUAGE_NAMES[source_lang]
    return (
        "You are Phantaslate, a translation engine. Translate the user's message "
        f"into {target}. The user states the source language is {source}, but you "
        "must report the language the message is genuinely written in — if it "
        "differs, report the real one. " + envelope + common
    )


@app.get("/health")
def health():
    """Liveness check. Reveals no request content."""
    return {"status": "ok", "model": MODEL, "stateless": True}


@app.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest, request: Request, response: Response):
    # Cheap validation first. These failures cost nothing upstream, so there is
    # no reason to spend the caller's daily quota on them.
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Relay is not configured: missing API key.")
    if req.target_lang == "auto":
        raise HTTPException(status_code=400, detail="target_lang cannot be 'auto'.")

    # --- Which caller is this? -----------------------------------------------
    # The website and the extension share this relay but get different caps.
    # Origin is set by the browser and cannot be forged by page JavaScript;
    # a non-browser caller can send anything, which is why the IP ceiling in
    # ratelimit.py — not this check — is the actual abuse defence.
    origin = (request.headers.get("origin") or "").rstrip("/")
    is_web = origin in WEB_ORIGINS

    if is_web:
        profile = "web"
        caller_token = request.headers.get("x-phantaslate-session")
        if len(req.text) > WEB_MAX_CHARS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Text is over the {WEB_MAX_CHARS:,}-character limit for the "
                    f"website. The extension handles {MAX_CHARS:,} per translation."
                ),
            )
    else:
        profile = "extension"
        caller_token = request.headers.get("x-phantaslate-install")

    # --- Rate limit ----------------------------------------------------------
    # Checked before the upstream call so rejected traffic costs nothing.
    verdict = limiter.check_and_consume(
        client_ip(request),
        caller_token,
        len(req.text),
        profile=profile,
    )

    quota_headers = {
        "X-RateLimit-Limit": str(verdict.limit),
        "X-RateLimit-Remaining": str(verdict.remaining),
        "X-RateLimit-Reset": str(verdict.reset_at),
    }
    # Set on the success path. HTTPException discards this Response object, so
    # the 429 below carries the same headers explicitly.
    response.headers.update(quota_headers)

    if not verdict.allowed:
        if verdict.scope == "network":
            detail = "This network has reached today's shared limit. It resets at midnight UTC."
        else:
            detail = "You've reached today's translation limit. It resets at midnight UTC."

        if is_web:
            # A website visitor who hits the cap has a genuinely better
            # option available, so say so rather than just refusing.
            detail += " The browser extension has its own, larger allowance — free, no account."

        raise HTTPException(status_code=429, detail=detail, headers=quota_headers)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(req.source_lang, req.target_lang)},
            {"role": "user", "content": req.text},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)
    except httpx.RequestError:
        # Network/timeout reaching the model provider.
        raise HTTPException(status_code=502, detail="Could not reach the translation model.")

    if resp.status_code != 200:
        # Surface a generic upstream error without echoing provider internals.
        raise HTTPException(status_code=502, detail=f"Translation model error ({resp.status_code}).")

    try:
        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Unexpected response from the translation model.")

    detected, translation = parse_auto_reply(raw)

    mismatch = False
    detected_code = None
    if detected:
        detected_code = code_from_name(detected)
        if req.source_lang != "auto":
            mismatch, detected_code = is_mismatch(req.source_lang, detected)

    return TranslateResponse(
        translation=translation,
        detected_lang=detected,
        detected_code=detected_code,
        source_mismatch=mismatch,
    )
