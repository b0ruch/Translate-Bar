# SPDX-License-Identifier: MIT
# pyright: reportAttributeAccessIssue=false
"""Строки интерфейса Translate Bar (RU/EN/DE/FR/JA/ZH-Hans)."""

from __future__ import annotations

import json

from paths import settings_path

SETTINGS_FILE_FALLBACK = settings_path()

SUPPORTED_UI_LANGS = ("ru", "en", "de", "fr", "ja", "zh-Hans")

UI_LANG_NATIVE = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "ja": "日本語",
    "zh-Hans": "简体中文",
}


def ui_lang_options() -> list[str]:
    """Коды языков для селектора: system первая, остальные по алфавиту."""
    rest = sorted(
        (c for c in SUPPORTED_UI_LANGS), key=lambda c: UI_LANG_NATIVE[c].lower()
    )
    return ["system"] + rest


STRINGS: dict[str, dict[str, str]] = {
    "menu_open": {
        "ru": "Открыть переводчик",
        "en": "Open Translator",
        "de": "Übersetzer öffnen",
        "fr": "Ouvrir le traducteur",
        "ja": "翻訳を開く",
        "zh-Hans": "打开翻译",
    },
    "menu_settings": {
        "ru": "Настройки...",
        "en": "Settings...",
        "de": "Einstellungen...",
        "fr": "Réglages...",
        "ja": "設定...",
        "zh-Hans": "设置...",
    },
    "menu_quit": {
        "ru": "Выйти",
        "en": "Quit",
        "de": "Beenden",
        "fr": "Quitter",
        "ja": "終了",
        "zh-Hans": "退出",
    },
    "appmenu_quit": {
        "ru": "Выйти из Translate Bar",
        "en": "Quit Translate Bar",
        "de": "Translate Bar beenden",
        "fr": "Quitter Translate Bar",
        "ja": "Translate Bar を終了",
        "zh-Hans": "退出 Translate Bar",
    },
    "menu_edit": {
        "ru": "Правка",
        "en": "Edit",
        "de": "Bearbeiten",
        "fr": "Édition",
        "ja": "編集",
        "zh-Hans": "编辑",
    },
    "edit_undo": {
        "ru": "Отменить",
        "en": "Undo",
        "de": "Rückgängig",
        "fr": "Annuler",
        "ja": "元に戻す",
        "zh-Hans": "撤销",
    },
    "edit_redo": {
        "ru": "Повторить",
        "en": "Redo",
        "de": "Wiederholen",
        "fr": "Rétablir",
        "ja": "やり直す",
        "zh-Hans": "重做",
    },
    "edit_cut": {
        "ru": "Вырезать",
        "en": "Cut",
        "de": "Ausschneiden",
        "fr": "Couper",
        "ja": "切り取り",
        "zh-Hans": "剪切",
    },
    "edit_copy": {
        "ru": "Копировать",
        "en": "Copy",
        "de": "Kopieren",
        "fr": "Copier",
        "ja": "コピー",
        "zh-Hans": "复制",
    },
    "edit_paste": {
        "ru": "Вставить",
        "en": "Paste",
        "de": "Einfügen",
        "fr": "Coller",
        "ja": "貼り付け",
        "zh-Hans": "粘贴",
    },
    "edit_select_all": {
        "ru": "Выбрать всё",
        "en": "Select All",
        "de": "Alles auswählen",
        "fr": "Tout sélectionner",
        "ja": "すべて選択",
        "zh-Hans": "全选",
    },
    "tip_swap": {
        "ru": "Поменять направление",
        "en": "Swap languages",
        "de": "Sprachen tauschen",
        "fr": "Inverser les langues",
        "ja": "言語を入れ替え",
        "zh-Hans": "交换语言",
    },
    "tip_settings": {
        "ru": "Настройки",
        "en": "Settings",
        "de": "Einstellungen",
        "fr": "Réglages",
        "ja": "設定",
        "zh-Hans": "设置",
    },
    "tip_history_expand": {
        "ru": "Развернуть историю",
        "en": "Expand history",
        "de": "Verlauf einblenden",
        "fr": "Afficher l'historique",
        "ja": "履歴を展開",
        "zh-Hans": "展开历史记录",
    },
    "tip_history_collapse": {
        "ru": "Свернуть историю",
        "en": "Collapse history",
        "de": "Verlauf ausblenden",
        "fr": "Masquer l'historique",
        "ja": "履歴を折りたたむ",
        "zh-Hans": "收起历史记录",
    },
    "history_mode": {
        "ru": "История",
        "en": "History",
        "de": "Verlauf",
        "fr": "Historique",
        "ja": "履歴",
        "zh-Hans": "历史记录",
    },
    "history_mode_inline": {
        "ru": "Встроенная",
        "en": "Inline",
        "de": "Eingebettet",
        "fr": "Intégré",
        "ja": "インライン",
        "zh-Hans": "内嵌",
    },
    "history_mode_screen": {
        "ru": "Отдельный экран",
        "en": "Full view",
        "de": "Eigene Ansicht",
        "fr": "Plein écran",
        "ja": "全画面",
        "zh-Hans": "整页视图",
    },
    "tip_copy": {
        "ru": "Скопировать перевод",
        "en": "Copy translation",
        "de": "Übersetzung kopieren",
        "fr": "Copier la traduction",
        "ja": "翻訳をコピー",
        "zh-Hans": "复制译文",
    },
    "tip_clear_text": {
        "ru": "Очистить текст",
        "en": "Clear text",
        "de": "Text löschen",
        "fr": "Effacer le texte",
        "ja": "テキストをクリア",
        "zh-Hans": "清空文本",
    },
    "placeholder": {
        "ru": "Введите текст…",
        "en": "Type text to translate…",
        "de": "Text eingeben…",
        "fr": "Saisissez du texte…",
        "ja": "テキストを入力…",
        "zh-Hans": "输入文本…",
    },
    "recent": {
        "ru": "Недавние",
        "en": "Recent",
        "de": "Zuletzt",
        "fr": "Récents",
        "ja": "最近",
        "zh-Hans": "最近",
    },
    "clear": {
        "ru": "Очистить",
        "en": "Clear",
        "de": "Löschen",
        "fr": "Effacer",
        "ja": "クリア",
        "zh-Hans": "清除",
    },
    "history_empty": {
        "ru": "История пуста",
        "en": "No history yet",
        "de": "Noch kein Verlauf",
        "fr": "Historique vide",
        "ja": "履歴はまだありません",
        "zh-Hans": "暂无历史记录",
    },
    "copied": {
        "ru": "Скопировано ✓",
        "en": "Copied ✓",
        "de": "Kopiert ✓",
        "fr": "Copié ✓",
        "ja": "コピーしました ✓",
        "zh-Hans": "已复制 ✓",
    },
    "translating": {
        "ru": "Перевожу…",
        "en": "Translating…",
        "de": "Übersetze…",
        "fr": "Traduction…",
        "ja": "翻訳中…",
        "zh-Hans": "翻译中…",
    },
    "error_prefix": {
        "ru": "Ошибка",
        "en": "Error",
        "de": "Fehler",
        "fr": "Erreur",
        "ja": "エラー",
        "zh-Hans": "错误",
    },
    "no_connection": {
        "ru": "Нет связи с сервисами перевода (Google перегружен, MyMemory недоступен). Подождите минуту и попробуйте снова.",
        "en": "Translation services unreachable (Google is overloaded, MyMemory is down). Wait a minute and try again.",
        "de": "Übersetzungsdienste nicht erreichbar (Google ist überlastet, MyMemory ist down). Warte eine Minute und versuche es erneut.",
        "fr": "Services de traduction inaccessibles (Google est surchargé, MyMemory est indisponible). Patientez une minute et réessayez.",
        "ja": "翻訳サービスに接続できません（Google が混雑しているか、MyMemory が利用できません）。1分ほど待ってから再試行してください。",
        "zh-Hans": "无法连接翻译服务（Google 繁忙，MyMemory 不可用）。请稍候一分钟后重试。",
    },
    "earlier": {
        "ru": "ранее",
        "en": "earlier",
        "de": "früher",
        "fr": "auparavant",
        "ja": "以前",
        "zh-Hans": "更早",
    },
    "settings_title": {
        "ru": "Настройки",
        "en": "Settings",
        "de": "Einstellungen",
        "fr": "Réglages",
        "ja": "設定",
        "zh-Hans": "设置",
    },
    "autostart": {
        "ru": "Запускать при входе в macOS",
        "en": "Launch at macOS login",
        "de": "Bei der Anmeldung starten",
        "fr": "Ouvrir à la connexion",
        "ja": "ログイン時に起動",
        "zh-Hans": "登录时启动",
    },
    "autostart_hint": {
        "ru": "Иконка появится в menu bar после входа",
        "en": "The icon will appear in the menu bar after login",
        "de": "Das Symbol erscheint nach der Anmeldung in der Menüleiste",
        "fr": "L'icône apparaîtra dans la barre des menus après la connexion",
        "ja": "ログイン後にメニューバーにアイコンが表示されます",
        "zh-Hans": "登录后图标将显示在菜单栏中",
    },
    "ui_language": {
        "ru": "Язык интерфейса",
        "en": "Interface language",
        "de": "Sprache",
        "fr": "Langue de l'interface",
        "ja": "表示言語",
        "zh-Hans": "界面语言",
    },
    "ui_lang_system": {
        "ru": "Система",
        "en": "System",
        "de": "System",
        "fr": "Système",
        "ja": "システム",
        "zh-Hans": "系统",
    },
    "ui_lang_note": {
        "ru": "Применится после перезапуска",
        "en": "Applies after restart",
        "de": "Wird nach Neustart übernommen",
        "fr": "Appliqué après redémarrage",
        "ja": "再起動後に適用されます",
        "zh-Hans": "重启后生效",
    },
    "version_line": {
        "ru": "Translate Bar · версия {v}",
        "en": "Translate Bar · version {v}",
        "de": "Translate Bar · Version {v}",
        "fr": "Translate Bar · version {v}",
        "ja": "Translate Bar · バージョン {v}",
        "zh-Hans": "Translate Bar · 版本 {v}",
    },
    "autostart_error_title": {
        "ru": "Не удалось изменить автозапуск",
        "en": "Could not change login item",
        "de": "Autostart konnte nicht geändert werden",
        "fr": "Impossible de modifier l'ouverture à la connexion",
        "ja": "ログイン項目を変更できませんでした",
        "zh-Hans": "无法更改登录启动项",
    },
    "autostart_denied": {
        "ru": "Не удалось добавить в объекты входа: {e}",
        "en": "Could not add login item: {e}",
        "de": "Anmeldeobjekt konnte nicht hinzugefügt werden: {e}",
        "fr": "Impossible d'ajouter l'élément d'ouverture : {e}",
        "ja": "ログイン項目を追加できませんでした: {e}",
        "zh-Hans": "无法添加登录启动项：{e}",
    },
    "autostart_approval": {
        "ru": "Подтвердите в Системных настройках → Основные → Объекты входа",
        "en": "Approve in System Settings → General → Login Items",
        "de": "Bestätige unter Systemeinstellungen → Allgemein → Anmeldeobjekte",
        "fr": "Validez dans Réglages Système → Général → Ouverture",
        "ja": "システム設定 → 一般 → ログイン項目 で許可してください",
        "zh-Hans": "请在系统设置 → 通用 → 登录项中确认",
    },
    "autostart_unsupported": {
        "ru": "Нужен macOS 13+ и модуль ServiceManagement",
        "en": "Requires macOS 13+ and the ServiceManagement module",
        "de": "Erfordert macOS 13+ und das ServiceManagement-Modul",
        "fr": "Nécessite macOS 13+ et le module ServiceManagement",
        "ja": "macOS 13以降とServiceManagementモジュールが必要です",
        "zh-Hans": "需要 macOS 13 及以上和 ServiceManagement 模块",
    },
    "autostart_on": {
        "ru": "Автозапуск включён",
        "en": "Launch at login enabled",
        "de": "Autostart aktiviert",
        "fr": "Ouverture à la connexion activée",
        "ja": "ログイン時の起動を有効にしました",
        "zh-Hans": "已启用登录时启动",
    },
    "autostart_off": {
        "ru": "Автозапуск выключен",
        "en": "Launch at login disabled",
        "de": "Autostart deaktiviert",
        "fr": "Ouverture à la connexion désactivée",
        "ja": "ログイン時の起動を無効にしました",
        "zh-Hans": "已关闭登录时启动",
    },
    "already_running": {
        "ru": "Переводчик уже запущен (иконка в menu bar).",
        "en": "Translator is already running (menu bar icon).",
        "de": "Der Übersetzer läuft bereits (Menüleistensymbol).",
        "fr": "Le traducteur est déjà en cours d'exécution (icône de la barre des menus).",
        "ja": "翻訳はすでに実行中です（メニューバーのアイコン）。",
        "zh-Hans": "翻译器已在运行（菜单栏图标）。",
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
    "de": {
        "auto": "Auto",
        "en": "Englisch",
        "ru": "Russisch",
        "fr": "Französisch",
        "de": "Deutsch",
        "es": "Spanisch",
        "it": "Italienisch",
        "pt": "Portugiesisch",
        "pl": "Polnisch",
        "uk": "Ukrainisch",
        "ja": "Japanisch",
        "zh": "Chinesisch",
        "ko": "Koreanisch",
    },
    "fr": {
        "auto": "Auto",
        "en": "Anglais",
        "ru": "Russe",
        "fr": "Français",
        "de": "Allemand",
        "es": "Espagnol",
        "it": "Italien",
        "pt": "Portugais",
        "pl": "Polonais",
        "uk": "Ukrainien",
        "ja": "Japonais",
        "zh": "Chinois",
        "ko": "Coréen",
    },
    "ja": {
        "auto": "自動",
        "en": "英語",
        "ru": "ロシア語",
        "fr": "フランス語",
        "de": "ドイツ語",
        "es": "スペイン語",
        "it": "イタリア語",
        "pt": "ポルトガル語",
        "pl": "ポーランド語",
        "uk": "ウクライナ語",
        "ja": "日本語",
        "zh": "中国語",
        "ko": "韓国語",
    },
    "zh-Hans": {
        "auto": "自动",
        "en": "英语",
        "ru": "俄语",
        "fr": "法语",
        "de": "德语",
        "es": "西班牙语",
        "it": "意大利语",
        "pt": "葡萄牙语",
        "pl": "波兰语",
        "uk": "乌克兰语",
        "ja": "日语",
        "zh": "中文",
        "ko": "韩语",
    },
}

TIME_FORMS: dict[str, dict[str, object]] = {
    "ru": {
        "template": "{n} {unit} {ago}",
        "just_now": ("только что", "", ""),
        "ago": ("назад", "", ""),
        "earlier": ("ранее", "", ""),
        "minute": ("минуту", "минуты", "минут"),
        "hour": ("час", "часа", "часов"),
    },
    "en": {
        "template": "{n} {unit} {ago}",
        "just_now": ("just now", "", ""),
        "ago": ("ago", "", ""),
        "earlier": ("earlier", "", ""),
        "minute": ("minute", "minutes", "minutes"),
        "hour": ("hour", "hours", "hours"),
    },
    "de": {
        "template": "vor {n} {unit}",
        "just_now": ("gerade eben", "", ""),
        "ago": ("", "", ""),
        "earlier": ("früher", "", ""),
        "minute": ("Minute", "Minuten", "Minuten"),
        "hour": ("Stunde", "Stunden", "Stunden"),
    },
    "fr": {
        "template": "il y a {n} {unit}",
        "just_now": ("à l'instant", "", ""),
        "ago": ("", "", ""),
        "earlier": ("auparavant", "", ""),
        "minute": ("minute", "minutes", "minutes"),
        "hour": ("heure", "heures", "heures"),
    },
    "ja": {
        "template": "{n}{unit}前",
        "just_now": ("たった今", "", ""),
        "ago": ("", "", ""),
        "earlier": ("以前", "", ""),
        "minute": ("分", "分", "分"),
        "hour": ("時間", "時間", "時間"),
    },
    "zh-Hans": {
        "template": "{n}{unit}前",
        "just_now": ("刚刚", "", ""),
        "ago": ("", "", ""),
        "earlier": ("更早", "", ""),
        "minute": ("分钟", "分钟", "分钟"),
        "hour": ("小时", "小时", "小时"),
    },
}

_ui_lang: str | None = None


def _normalize_ui_lang(code: str) -> str:
    c = code.strip().lower().replace("_", "-")
    if c.startswith("zh"):
        return "zh-Hans"
    for supported in SUPPORTED_UI_LANGS:
        if c == supported.lower() or c.startswith(supported.lower() + "-"):
            return supported
    return ""


def _system_lang() -> str:
    try:
        import AppKit

        preferred = AppKit.NSLocale.preferredLanguages() or []
        for entry in preferred:
            code = _normalize_ui_lang(str(entry))
            if code:
                return code
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
            saved = str(data.get("ui_lang", "system"))
    except (OSError, ValueError, AttributeError):
        pass
    _ui_lang = _normalize_ui_lang(saved) or _system_lang()
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
