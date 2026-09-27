# SPDX-License-Identifier: MIT
"""Логика перевода и истории Translate Bar."""

import json
import os
import re
import threading
import time
import urllib.parse

import requests
from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import RequestError, TooManyRequests
from langdetect import DetectorFactory, LangDetectException, detect_langs

from paths import history_path
from strings import TIME_FORMS, get_ui_lang

DetectorFactory.seed = 0

TARGET_LANG_GOOGLE = "ru"
TARGET_LANG_MYMEMORY = "russian"

TARGET_LANGUAGES = [
    ("Русский", "ru", "russian"),
    ("English", "en", "english"),
    ("Français", "fr", "french"),
    ("Deutsch", "de", "german"),
    ("Español", "es", "spanish"),
    ("Italiano", "it", "italian"),
    ("Português", "pt", "portuguese"),
    ("Polski", "pl", "polish"),
    ("Українська", "uk", "ukrainian"),
    ("日本語", "ja", "japanese"),
    ("中文", "zh-CN", "chinese simplified"),
    ("한국어", "ko", "korean"),
]

MIN_PAUSE_BETWEEN_REQUESTS = 0.4
_last_request_time: float = 0.0
_throttle_lock = threading.Lock()

_CHROME_TRANSLATE_URL = "https://clients5.google.com/translate_a/t"
_CHROME_CLIENT = "dict-chrome-ex"
_CHROME_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}
_CHROME_TIMEOUT = 12
_CHROME_CHUNK_LIMIT = 1000

_MYMEMORY_ERROR_MARKERS = (
    "invalid email",
    "query length limit",
    "no query specified",
    "mymemory warning",
    "you used all available free translations",
)

ISO_TO_MYMEMORY = {
    "en": "english",
    "ru": "russian",
    "fr": "french",
    "de": "german",
    "es": "spanish",
    "it": "italian",
    "pt": "portuguese",
    "pl": "polish",
    "uk": "ukrainian",
    "ja": "japanese",
    "zh": "chinese simplified",
    "zh-cn": "chinese simplified",
    "ko": "korean",
    "ar": "arabic",
    "tr": "turkish",
    "cs": "czech",
}

FALSE_FRIENDS = {"nl", "fi", "no", "ca", "cy", "sv", "da", "af", "so", "sw", "nn", "nb"}

MIN_DETECT_CONFIDENCE = 0.85

CYRILLIC_LANGS = {"ru", "uk", "be", "bg", "mk", "sr", "kk", "ky", "tg", "mn"}

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

HISTORY_FILE = history_path()
HISTORY_LIMIT = 50
HISTORY_PREVIEW_LEN = 40


def resolve_target(target: str) -> tuple[str, str]:
    t = target.strip().lower()
    for label, google, mymemory in TARGET_LANGUAGES:
        if t in (google.lower(), mymemory, label.lower()):
            return google, mymemory
    return TARGET_LANG_GOOGLE, TARGET_LANG_MYMEMORY


SOURCE_AUTO = "auto"

SOURCE_LANGUAGES = [("Авто", "auto", "auto")] + list(TARGET_LANGUAGES)


def resolve_source(source: str) -> tuple[str, str]:
    t = source.strip().lower()
    if t in ("auto", "авто"):
        return SOURCE_AUTO, SOURCE_AUTO
    for label, google, mymemory in SOURCE_LANGUAGES:
        if t in (google.lower(), mymemory, label.lower()):
            return google, mymemory
    return SOURCE_AUTO, SOURCE_AUTO


def is_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text))


def detect_iso(text: str) -> str:
    cyr = is_cyrillic(text)
    try:
        langs = detect_langs(text)
    except LangDetectException:
        return "ru" if cyr else "en"
    if not langs:
        return "ru" if cyr else "en"
    best = langs[0]
    if best.lang in FALSE_FRIENDS or best.prob < MIN_DETECT_CONFIDENCE:
        return "ru" if cyr else "en"
    if cyr and best.lang not in CYRILLIC_LANGS:
        return "ru"
    return best.lang


def to_str(value: str | list) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def throttle() -> None:
    global _last_request_time
    with _throttle_lock:
        elapsed = time.time() - _last_request_time
        wait = MIN_PAUSE_BETWEEN_REQUESTS - elapsed
    if wait > 0:
        time.sleep(wait)


def mark_request_done() -> None:
    global _last_request_time
    with _throttle_lock:
        _last_request_time = time.time()


def _same_lang(iso: str, google_code: str) -> bool:
    return iso.lower().split("-")[0] == google_code.lower().split("-")[0]


def _parse_chrome_response(data) -> tuple[str, str]:
    segments = data[0] if isinstance(data, list) and data else []
    if isinstance(segments, str):
        return segments, "auto"
    if not isinstance(segments, list) or not segments:
        return "", "auto"
    if isinstance(segments[0], str):
        src = str(segments[1]) if len(segments) > 1 and segments[1] else "auto"
        return str(segments[0]), src
    parts: list[str] = []
    src = "auto"
    for seg in segments:
        if not isinstance(seg, list) or not seg:
            continue
        if seg[0]:
            parts.append(str(seg[0]))
        if len(seg) > 1 and seg[1] and src == "auto":
            src = str(seg[1])
    return "".join(parts), src


def _split_chunks(text: str, limit: int = _CHROME_CHUNK_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = re.split(r"(?<=[.!?…\n])\s+", text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= limit:
            current += part + " "
        else:
            if current:
                chunks.append(current.rstrip())
            while len(part) > limit:
                chunks.append(part[:limit])
                part = part[limit:]
            current = part + " " if part else ""
    if current.strip():
        chunks.append(current.rstrip())
    return chunks or [text]


def _chrome_request(chunk: str, google: str, source: str) -> tuple[str, str] | None:
    params = {
        "client": _CHROME_CLIENT,
        "sl": source,
        "tl": google,
        "q": chunk,
    }
    url = _CHROME_TRANSLATE_URL + "?" + urllib.parse.urlencode(params)
    for attempt in (0, 1):
        try:
            resp = requests.get(url, headers=_CHROME_HEADERS, timeout=_CHROME_TIMEOUT)
        except requests.RequestException:
            return None
        if resp.status_code == 429 and attempt == 0:
            time.sleep(1.2)
            continue
        if resp.status_code != 200:
            return None
        try:
            result, src = _parse_chrome_response(resp.json())
        except ValueError:
            return None
        mark_request_done()
        if not result:
            return None
        return result, src
    return None


def translate_via_google_chrome(
    text: str, target: str = TARGET_LANG_GOOGLE, source: str = SOURCE_AUTO
) -> tuple[str, str] | None:
    google, _ = resolve_target(target)
    src_google, _ = resolve_source(source)
    chunks = _split_chunks(text)
    translated: list[str] = []
    src = "auto"
    for i, chunk in enumerate(chunks):
        if i > 0:
            throttle()
        one = _chrome_request(chunk, google, src_google)
        if one is None:
            return None
        translated.append(one[0])
        if src == "auto" and one[1] != "auto":
            src = one[1]
    if src_google != SOURCE_AUTO:
        src = src_google
    return "".join(translated), src


def translate_via_google(
    text: str, target: str = TARGET_LANG_GOOGLE, source: str = SOURCE_AUTO
) -> str | None:
    google, _ = resolve_target(target)
    src_google, _ = resolve_source(source)
    try:
        result = to_str(
            GoogleTranslator(source=src_google, target=google).translate(text)
        )
        mark_request_done()
        if not result.strip():
            return None
        if result.strip().lower() == text.strip().lower():
            iso = detect_iso(text)
            if _same_lang(iso, google):
                return result
            return None
        return result
    except (TooManyRequests, RequestError):
        return None
    except Exception:
        return None


def translate_via_mymemory(
    text: str, target: str = TARGET_LANG_GOOGLE, source: str = SOURCE_AUTO
) -> str | None:
    google, mymemory = resolve_target(target)
    src_google, _ = resolve_source(source)
    iso = src_google if src_google != SOURCE_AUTO else detect_iso(text)
    if _same_lang(iso, google) or (google == "ru" and iso in CYRILLIC_LANGS):
        return text
    try:
        result = to_str(
            MyMemoryTranslator(
                source=ISO_TO_MYMEMORY.get(
                    iso, "russian" if iso in CYRILLIC_LANGS else "english"
                ),
                target=mymemory,
            ).translate(text)
        )
    except Exception:
        return None
    mark_request_done()
    if not result:
        return None
    if result.strip().lower().startswith(_MYMEMORY_ERROR_MARKERS):
        return None
    return result


def translate_with_meta(
    text: str, target: str = TARGET_LANG_GOOGLE, source: str = SOURCE_AUTO
) -> tuple[str, str, str]:
    if not text.strip():
        return "", detect_iso(text), "none"
    google, _ = resolve_target(target)
    src_google, _ = resolve_source(source)
    if src_google != SOURCE_AUTO and _same_lang(src_google, google):
        return text.strip(), src_google, "same"
    throttle()
    chrome = translate_via_google_chrome(text, target, source)
    if chrome is not None:
        result, src = chrome
        return result, src, "google"
    fallback = translate_via_google(text, target, source)
    if fallback is not None:
        src = src_google if src_google != SOURCE_AUTO else detect_iso(text)
        return fallback, src, "google"
    memo = translate_via_mymemory(text, target, source)
    if memo is not None:
        src = src_google if src_google != SOURCE_AUTO else detect_iso(text)
        return memo, src, "mymemory"
    # Sentinel key: menubar maps it to the localized message.
    raise RuntimeError("NO_CONNECTION")


def detect_and_translate(
    text: str, target: str = TARGET_LANG_GOOGLE, source: str = SOURCE_AUTO
) -> str:
    result, _, _ = translate_with_meta(text, target, source)
    return result


def load_history() -> list[dict]:
    try:
        if not HISTORY_FILE.exists():
            return []
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict) and "src" in d and "dst" in d][
            :HISTORY_LIMIT
        ]
    except (OSError, ValueError):
        return []


def lookup_history(
    history: list[dict], src: str, dst_lang: str, src_lang: str = SOURCE_AUTO
) -> tuple[str, str] | None:
    src = src.strip()
    if not src:
        return None
    want = dst_lang.strip().lower()
    want_src = src_lang.strip().lower()
    for item in history:
        if item.get("src", "").strip() != src:
            continue
        if item.get("dst_lang", "ru").lower() != want:
            continue
        recorded = item.get("src_lang", "").lower()
        if want_src != SOURCE_AUTO and recorded and recorded != want_src:
            continue
        return item.get("dst", ""), item.get("src_lang", "auto")
    return None


def save_history(history: list[dict]) -> None:
    try:
        tmp = HISTORY_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, HISTORY_FILE)
    except OSError:
        pass


def add_to_history(
    history: list[dict],
    src: str,
    dst: str,
    src_lang: str = "",
    dst_lang: str = "",
    provider: str = "",
    ts: float | None = None,
) -> list[dict]:
    src, dst = src.strip(), dst.strip()
    if not src or not dst:
        return history
    if history and history[0].get("src") == src and history[0].get("dst") == dst:
        return history
    item: dict = {"src": src, "dst": dst}
    if src_lang:
        item["src_lang"] = src_lang
    if dst_lang:
        item["dst_lang"] = dst_lang
    if provider:
        item["via"] = provider
    item["ts"] = ts if ts is not None else time.time()
    return [item] + history[: HISTORY_LIMIT - 1]


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def relative_time(ts, lang: str | None = None) -> str:
    forms = TIME_FORMS.get(lang or get_ui_lang(), TIME_FORMS["ru"])
    try:
        delta = time.time() - float(ts)
    except (TypeError, ValueError):
        return forms["earlier"][0]
    if delta < 60:
        return forms["just_now"][0]
    minutes = int(delta // 60)
    if minutes < 60:
        return f"{minutes} {_plural(minutes, forms['minute'])} {forms['ago'][0]}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} {_plural(hours, forms['hour'])} {forms['ago'][0]}"
    try:
        return time.strftime("%d.%m.%Y", time.localtime(float(ts)))
    except (TypeError, ValueError, OverflowError):
        return forms["earlier"][0]


def format_history_item(item: dict) -> str:
    src, dst = item.get("src", ""), item.get("dst", "")
    if len(src) > HISTORY_PREVIEW_LEN:
        src = src[:HISTORY_PREVIEW_LEN] + "..."
    if len(dst) > HISTORY_PREVIEW_LEN:
        dst = dst[:HISTORY_PREVIEW_LEN] + "..."
    return f"{src} → {dst}"
