# SPDX-License-Identifier: MIT
# pyright: reportAttributeAccessIssue=false
"""Строки интерфейса Translate Bar (RU/EN)."""

from __future__ import annotations

import json

from paths import settings_path

SETTINGS_FILE_FALLBACK = settings_path()

SUPPORTED_UI_LANGS = ("ru", "en")

STRINGS: dict[str, dict[str, str]] = {
    "menu_open": {"ru": "Открыть переводчик", "en": "Open Translator"},
    "menu_settings": {"ru": "Настройки...", "en": "Settings..."},
    "menu_quit": {"ru": "Выйти", "en": "Quit"},
    "appmenu_quit": {"ru": "Выйти из Translate Bar", "en": "Quit Translate Bar"},
    "tip_swap": {"ru": "Поменять направление", "en": "Swap languages"},
    "tip_settings": {"ru": "Настройки", "en": "Settings"},
    "tip_copy": {"ru": "Скопировать перевод", "en": "Copy translation"},
    "tip_clear_text": {"ru": "Очистить текст", "en": "Clear text"},
    "placeholder": {"ru": "Введите текст…", "en": "Type text to translate…"},
    "recent": {"ru": "Недавние", "en": "Recent"},
    "clear": {"ru": "Очистить", "en": "Clear"},
    "history_empty": {"ru": "История пуста", "en": "No history yet"},
    "copied": {"ru": "Скопировано ✓", "en": "Copied ✓"},
    "translating": {"ru": "Перевожу…", "en": "Translating…"},
    "error_prefix": {"ru": "Ошибка", "en": "Error"},
    "no_connection": {
        "ru": "Нет связи с сервисами перевода (Google перегружен, MyMemory недоступен). Подождите минуту и попробуйте снова.",
        "en": "Translation services unreachable (Google is overloaded, MyMemory is down). Wait a minute and try again.",
    },
    "earlier": {"ru": "ранее", "en": "earlier"},
    "settings_title": {"ru": "Настройки", "en": "Settings"},
    "autostart": {"ru": "Запускать при входе в macOS", "en": "Launch at macOS login"},
    "autostart_hint": {
        "ru": "Иконка появится в menu bar после входа",
        "en": "The icon will appear in the menu bar after login",
    },
    "ui_language": {"ru": "Язык интерфейса", "en": "Interface language"},
    "ui_lang_system": {"ru": "Система", "en": "System"},
    "ui_lang_note": {
        "ru": "Применится после перезапуска",
        "en": "Applies after restart",
    },
    "version_line": {"ru": "Translate Bar · версия {v}", "en": "Translate Bar · version {v}"},
    "autostart_error_title": {
        "ru": "Не удалось изменить автозапуск",
        "en": "Could not change login item",
    },
    "autostart_denied": {
        "ru": "Не удалось добавить в объекты входа: {e}",
        "en": "Could not add login item: {e}",
    },
    "autostart_approval": {
        "ru": "Подтвердите в Системных настройках → Основные → Объекты входа",
        "en": "Approve in System Settings → General → Login Items",
    },
    "autostart_unsupported": {
        "ru": "Нужен macOS 13+ и модуль ServiceManagement",
        "en": "Requires macOS 13+ and the ServiceManagement module",
    },
    "autostart_on": {"ru": "Автозапуск включён", "en": "Launch at login enabled"},
    "autostart_off": {"ru": "Автозапуск выключен", "en": "Launch at login disabled"},
    "already_running": {
        "ru": "Переводчик уже запущен (иконка в menu bar).",
        "en": "Translator is already running (menu bar icon).",
    },
}

LANG_NAMES: dict[str, dict[str, str]] = {
    "ru": {
        "auto": "Авто",
        "en": "Английский",
        "ru": "Русский",
        "fr": "Французский",
        "de": "Немецкий",
        "es": "Испанский",
        "it": "Итальянский",
        "pt": "Португальский",
        "pl": "Польский",
        "uk": "Украинский",
        "ja": "Японский",
        "zh": "Китайский",
        "ko": "Корейский",
    },
    "en": {
        "auto": "Auto",
        "en": "English",
        "ru": "Russian",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "pl": "Polish",
        "uk": "Ukrainian",
        "ja": "Japanese",
        "zh": "Chinese",
        "ko": "Korean",
    },
}

TIME_FORMS: dict[str, dict[str, tuple[str, str, str]]] = {
    "ru": {
        "just_now": ("только что", "", ""),
        "ago": ("назад", "", ""),
        "earlier": ("ранее", "", ""),
        "minute": ("минуту", "минуты", "минут"),
        "hour": ("час", "часа", "часов"),
    },
    "en": {
        "just_now": ("just now", "", ""),
        "ago": ("ago", "", ""),
        "earlier": ("earlier", "", ""),
        "minute": ("minute", "minutes", "minutes"),
        "hour": ("hour", "hours", "hours"),
    },
}

_ui_lang: str | None = None


def _system_lang() -> str:
    try:
        import AppKit

        preferred = AppKit.NSLocale.preferredLanguages()
        if preferred and str(preferred[0]).lower().startswith("ru"):
            return "ru"
    except Exception:
        pass
    return "en"


def get_ui_lang() -> str:
    global _ui_lang
    if _ui_lang is not None:
        return _ui_lang
    saved = ""
    try:
        data = json.loads(SETTINGS_FILE_FALLBACK.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            saved = str(data.get("ui_lang", "system")).lower()
    except (OSError, ValueError, AttributeError):
        pass
    _ui_lang = saved if saved in SUPPORTED_UI_LANGS else _system_lang()
    return _ui_lang


def reset_ui_lang() -> None:
    global _ui_lang
    _ui_lang = None


def t(key: str, **kwargs) -> str:
    lang = get_ui_lang()
    entry = STRINGS.get(key, {})
    text = entry.get(lang) or entry.get("ru") or key
    return text.format(**kwargs) if kwargs else text


def lang_name(code: str, lang: str | None = None) -> str:
    lang = lang or get_ui_lang()
    base = code.lower().split("-")[0]
    names = LANG_NAMES.get(lang, LANG_NAMES["ru"])
    return names.get(base, code)
