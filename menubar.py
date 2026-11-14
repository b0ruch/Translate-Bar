# SPDX-License-Identifier: MIT
# pyright: reportAttributeAccessIssue=false
# PyObjC resolves AppKit/Foundation symbols at runtime, invisible to static analysis.
"""Translate Bar: menu bar translator for macOS."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

try:
    import AppKit
    import objc
    from Foundation import NSObject
except ImportError as exc:
    raise SystemExit(
        "Нужен PyObjC (AppKit). Запустите через окружение проекта: "
        ".venv/bin/python menubar.py"
    ) from exc

try:
    from ServiceManagement import SMAppService
except ImportError:
    SMAppService = None

from translator_core import (
    SOURCE_AUTO,
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
    add_to_history,
    format_history_item,
    load_history,
    lookup_history,
    relative_time,
    save_history,
    translate_with_meta,
)
from paths import settings_path
from strings import UI_LANG_NATIVE, lang_name, t, ui_lang_options

POPOVER_W, POPOVER_H = 360, 468
SETTINGS_W, SETTINGS_H = 320, 268
DEBOUNCE_INTERVAL = 0.6
FADE_DURATION = 0.1
FADE_STEP = 1.0 / 60.0
DIVIDER_LINE_THRESHOLD = 5
APP_VERSION = "1.2.0"
APP_NAME = "Translate Bar"
LAUNCH_LABEL = "com.translatebar.menubar"
LAUNCH_AGENT_PATH = (
    Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_LABEL}.plist"
)
_LOCK_PATH = os.path.join(tempfile.gettempdir(), "translate_bar_menubar.lock")
SETTINGS_FILE = settings_path()
DEFAULT_TARGET = "en"
CLICK_DEBOUNCE = 0.3


def _read_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _write_settings(patch: dict) -> None:
    try:
        data = _read_settings()
        data.update(patch)
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _valid_code(code: str, languages: list, default: str) -> str:
    for _, google, _ in languages:
        if code.lower() == google.lower():
            return google
    return default


def load_target_lang() -> str:
    return _valid_code(
        str(_read_settings().get("target_lang", DEFAULT_TARGET)),
        TARGET_LANGUAGES,
        DEFAULT_TARGET,
    )


def save_target_lang(code: str) -> None:
    _write_settings({"target_lang": code})


def load_source_lang() -> str:
    return _valid_code(
        str(_read_settings().get("source_lang", SOURCE_AUTO)),
        SOURCE_LANGUAGES,
        SOURCE_AUTO,
    )


def save_source_lang(code: str) -> None:
    _write_settings({"source_lang": code})


HISTORY_MODES = ("inline", "screen")
HISTORY_MODE_DEFAULT = "screen"


def load_history_mode() -> str:
    mode = str(_read_settings().get("history_mode", HISTORY_MODE_DEFAULT)).lower()
    return mode if mode in HISTORY_MODES else HISTORY_MODE_DEFAULT


def save_history_mode(mode: str) -> None:
    _write_settings(
        {"history_mode": mode if mode in HISTORY_MODES else HISTORY_MODE_DEFAULT}
    )


def load_history_expanded() -> bool:
    return bool(_read_settings().get("history_expanded", False))


def save_history_expanded(expanded: bool) -> None:
    _write_settings({"history_expanded": expanded})


def ensure_single_instance():
    fh = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def _scroll_with_text(rect, editable, bordered=True):
    scroll = AppKit.NSScrollView.alloc().initWithFrame_(rect)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    if not bordered:
        scroll.setBorderType_(AppKit.NSNoBorder)
        scroll.setDrawsBackground_(False)
        scroll.setScrollerStyle_(AppKit.NSScrollerStyleOverlay)
    view = AppKit.NSTextView.alloc().initWithFrame_(rect)
    view.setMinSize_(AppKit.NSMakeSize(0, 0))
    view.setMaxSize_(AppKit.NSMakeSize(1e7, 1e7))
    view.setVerticallyResizable_(True)
    view.setHorizontallyResizable_(False)
    view.setAutoresizingMask_(AppKit.NSViewWidthSizable)
    view.setFont_(AppKit.NSFont.systemFontOfSize_(14))
    view.setRichText_(False)
    view.setImportsGraphics_(False)
    view.setEditable_(editable)
    view.setSelectable_(True)
    if not bordered:
        view.setDrawsBackground_(False)
        view.setTextColor_(AppKit.NSColor.labelColor())
        view.setTextContainerInset_(AppKit.NSMakeSize(4.0, 6.0))
    scroll.setDocumentView_(view)
    return scroll, view


def _symbol(name, size=14):
    try:
        img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            name, name
        )
    except (AttributeError, objc.error):
        return None
    if img is None:
        return None
    img.setTemplate_(True)
    img.setSize_(AppKit.NSMakeSize(size, size))
    return img


def _icon_button(rect, symbol, fallback_title, action, target, tip="", size=14):
    button = AppKit.NSButton.alloc().initWithFrame_(rect)
    img = _symbol(symbol, size)
    if img is not None:
        button.setImage_(img)
        button.setImagePosition_(AppKit.NSImageOnly)
    else:
        button.setTitle_(fallback_title)
    button.setBordered_(False)
    button.setTarget_(target)
    button.setAction_(action)
    if tip:
        button.setToolTip_(tip)
    return button


def _secondary_label(rect, text):
    label = _label(rect, text)
    label.setFont_(AppKit.NSFont.systemFontOfSize_(11))
    label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
    return label


UI_LANG_CODES = ui_lang_options()


class TranslatorViewController(AppKit.NSViewController):
    pass


def _popup(rect, titles, action, target, pulls_down=False):
    popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(rect, pulls_down)
    if pulls_down:
        # В pullsDown первый item — это заголовок кнопки, а не пункт меню:
        # добавляем пустой, иначе первый язык пропадёт из списка.
        popup.addItemWithTitle_("")
    popup.addItemsWithTitles_(titles)
    try:
        popup.setBezelStyle_(AppKit.NSInlineBezelStyle)
    except (AttributeError, objc.error):
        pass
    if action:
        popup.setTarget_(target)
        popup.setAction_(action)
    return popup


def _label(rect, text, centered=False):
    label = AppKit.NSTextField.alloc().initWithFrame_(rect)
    label.setStringValue_(text)
    label.setBordered_(False)
    label.setDrawsBackground_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    if centered:
        label.setAlignment_(AppKit.NSCenterTextAlignment)
    return label


def _menu_item(title, action, target):
    item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        title, action, ""
    )
    item.setTarget_(target)
    return item


def _pointer_cursor(view, owner, in_visible_rect=False):
    options = (
        AppKit.NSTrackingMouseEnteredAndExited | AppKit.NSTrackingActiveAlways
    )
    if in_visible_rect:
        options |= AppKit.NSTrackingInVisibleRect
    area = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
        view.bounds(), options, owner, None
    )
    view.addTrackingArea_(area)
    return area


def _install_main_menu():
    # AppKit routes ⌘C/⌘V/⌘X/⌘A through the main menu to the first responder.
    app = AppKit.NSApplication.sharedApplication()
    main_menu = AppKit.NSMenu.alloc().init()

    app_item = AppKit.NSMenuItem.alloc().init()
    app_menu = AppKit.NSMenu.alloc().init()
    app_menu.addItem_(
        AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            t("appmenu_quit"), "terminate:", "q"
        )
    )
    app_item.setSubmenu_(app_menu)
    main_menu.addItem_(app_item)

    edit_item = AppKit.NSMenuItem.alloc().init()
    edit_item.setTitle_(t("menu_edit"))
    edit_menu = AppKit.NSMenu.alloc().initWithTitle_(t("menu_edit"))
    for title, action, key in [
        (t("edit_undo"), "undo:", "z"),
        (t("edit_redo"), "redo:", "Z"),
        (t("edit_cut"), "cut:", "x"),
        (t("edit_copy"), "copy:", "c"),
        (t("edit_paste"), "paste:", "v"),
        (t("edit_select_all"), "selectAll:", "a"),
    ]:
        edit_menu.addItem_(
            AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, key
            )
        )
    edit_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_item)

    app.setMainMenu_(main_menu)


SM_TYPE_MAIN_APP = 0
SM_STATUS_REGISTERED = 1
SM_STATUS_APPROVAL = 2


def _login_service():
    if SMAppService is None:
        return None
    try:
        return SMAppService.alloc().initWithType_identifier_(SM_TYPE_MAIN_APP, LAUNCH_LABEL)
    except (AttributeError, objc.error):
        return None


def _sm_status() -> int | None:
    svc = _login_service()
    if svc is None:
        return None
    try:
        return int(svc.status())
    except (AttributeError, objc.error, TypeError):
        return None


def is_autostart_enabled() -> bool:
    return _sm_status() == SM_STATUS_REGISTERED


def _remove_legacy_agent() -> None:
    if not LAUNCH_AGENT_PATH.exists():
        return
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCH_LABEL}"],
            capture_output=True,
            timeout=15,
        )
    except OSError:
        pass
    try:
        LAUNCH_AGENT_PATH.unlink()
    except OSError:
        pass


def set_autostart(enabled: bool) -> tuple[bool, str]:
    svc = _login_service()
    if svc is None:
        return False, t("autostart_unsupported")
    if enabled:
        _remove_legacy_agent()
        try:
            ok, err = svc.registerAndReturnError_(None)
        except (AttributeError, objc.error) as exc:
            return False, t("autostart_denied", e=exc)
        if not ok:
            return False, t("autostart_denied", e=err or "?")
        status = _sm_status()
        if status == SM_STATUS_APPROVAL:
            return False, t("autostart_approval")
        if status == SM_STATUS_REGISTERED:
            return True, t("autostart_on")
        return False, t("autostart_denied", e=status)
    try:
        ok, err = svc.unregisterAndReturnError_(None)
    except (AttributeError, objc.error) as exc:
        return False, t("autostart_denied", e=exc)
    if not ok:
        return False, t("autostart_denied", e=err or "?")
    return True, t("autostart_off")


def _show_alert(message: str, informative: str = "") -> None:
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(message)
    if informative:
        alert.setInformativeText_(informative)
    alert.addButtonWithTitle_("OK")
    alert.runModal()


class AppDelegate(NSObject):
    def init(self):
        self = objc.super(AppDelegate, self).init()
        self.history = load_history()
        self.history_mode = load_history_mode()
        # Вариант А: в режиме отдельного экрана поповер всегда
        # открывается с перевода, сохранённое состояние игнорируется.
        self.history_expanded = (
            load_history_expanded() if self.history_mode == "inline" else False
        )
        self._last_click = 0.0
        self._prev_input = ""
        self._req_id = 0
        self._fade_timer = None
        self._fade_step = 0
        self._divider_timer = None
        self._divider_alpha = 0.0
        self._divider_wanted = 0.0
        self._build_status_item()
        self._build_popover()
        self._build_settings()
        self._restore_languages()
        self._refresh_history()
        return self

    def _build_status_item(self):
        self.status = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
            AppKit.NSVariableStatusItemLength
        )
        button = self.status.button()
        icon = _symbol("translate", 17)
        if icon is not None:
            button.setImage_(icon)
        else:
            button.setTitle_("🌐")
        button.setTarget_(self)
        button.setAction_("toggle:")
        # Status bar ignores RightMouseDown; RightMouseUp works.
        button.sendActionOn_(
            AppKit.NSEventMaskLeftMouseDown | AppKit.NSEventMaskRightMouseUp
        )

        self.context_menu = AppKit.NSMenu.alloc().init()
        self.context_menu.addItem_(_menu_item(t("menu_open"), "showPopover:", self))
        self.context_menu.addItem_(_menu_item(t("menu_settings"), "openSettings:", self))
        self.context_menu.addItem_(AppKit.NSMenuItem.separatorItem())
        self.context_menu.addItem_(_menu_item(t("menu_quit"), "quitApp:", self))

    def _build_popover(self):
        self.vc = TranslatorViewController.alloc().init()
        root = AppKit.NSView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, POPOVER_W, POPOVER_H)
        )
        effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(root.bounds())
        effect.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
        effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(AppKit.NSVisualEffectStateActive)
        effect.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        root.addSubview_(effect)
        self.vc.setView_(root)
        c = effect

        row_y = POPOVER_H - 38
        self.source_popup = _popup(
            AppKit.NSMakeRect(12, row_y, 131, 26),
            [lang_name(code) for _, code, _ in SOURCE_LANGUAGES],
            "sourceChanged:",
            self,
            pulls_down=True,
        )
        self.source_popup.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        c.addSubview_(self.source_popup)
        _pointer_cursor(self.source_popup, self)

        self.swap_btn = _icon_button(
            AppKit.NSMakeRect(149, row_y, 28, 26),
            "arrow.left.arrow.right",
            "⇄",
            "swapLanguages:",
            self,
            tip=t("tip_swap"),
        )
        c.addSubview_(self.swap_btn)
        _pointer_cursor(self.swap_btn, self)

        self.target_popup = _popup(
            AppKit.NSMakeRect(183, row_y, 131, 26),
            [lang_name(code) for _, code, _ in TARGET_LANGUAGES],
            "languageChanged:",
            self,
            pulls_down=True,
        )
        self.target_popup.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        c.addSubview_(self.target_popup)
        _pointer_cursor(self.target_popup, self)

        self.hist_toggle_btn = _icon_button(
            AppKit.NSMakeRect(320, row_y, 28, 26),
            "clock",
            "◷",
            "toggleHistory:",
            self,
            tip=t("tip_history_expand"),
            size=16,
        )
        c.addSubview_(self.hist_toggle_btn)
        _pointer_cursor(self.hist_toggle_btn, self)

        self.input_scroll, self.input_view = _scroll_with_text(
            AppKit.NSMakeRect(12, 322, POPOVER_W - 24, 100), True, bordered=False
        )
        self.input_view.setDelegate_(self)
        c.addSubview_(self.input_scroll)

        self.placeholder = _secondary_label(
            AppKit.NSMakeRect(19, 397, 220, 20), t("placeholder")
        )
        self.placeholder.setFont_(AppKit.NSFont.systemFontOfSize_(14))
        c.addSubview_(self.placeholder)

        # Layer-backed NSView: NSBox высотой 1pt в NSVisualEffectView после
        # смены alpha перестаёт перерисовываться.
        self.input_divider = AppKit.NSView.alloc().initWithFrame_(
            AppKit.NSMakeRect(12, 320, POPOVER_W - 24, 1)
        )
        self.input_divider.setWantsLayer_(True)
        cg = AppKit.NSColor.separatorColor().CGColor()
        self._divider_cgcolor = cg
        self.input_divider.layer().setBackgroundColor_(cg)
        self.input_divider.setAlphaValue_(0.0)
        c.addSubview_(self.input_divider)

        self.clear_text_btn = _icon_button(
            AppKit.NSMakeRect(288, 298, 28, 22),
            "xmark",
            "✕",
            "clearText:",
            self,
            tip=t("tip_clear_text"),
        )
        self.clear_text_btn.setAlphaValue_(0.0)
        c.addSubview_(self.clear_text_btn)
        _pointer_cursor(self.clear_text_btn, self)

        self.caption = _secondary_label(
            AppKit.NSMakeRect(12, 300, 268, 18), ""
        )
        c.addSubview_(self.caption)

        self.copy_btn = _icon_button(
            AppKit.NSMakeRect(320, 298, 28, 22),
            "doc.on.doc",
            "⧉",
            "copyResult:",
            self,
            tip=t("tip_copy"),
        )
        c.addSubview_(self.copy_btn)
        _pointer_cursor(self.copy_btn, self)

        self.output_scroll, self.output_view = _scroll_with_text(
            AppKit.NSMakeRect(12, 192, POPOVER_W - 24, 100), False, bordered=False
        )
        c.addSubview_(self.output_scroll)

        self.divider = AppKit.NSBox.alloc().initWithFrame_(
            AppKit.NSMakeRect(12, 184, POPOVER_W - 24, 1)
        )
        self.divider.setBoxType_(AppKit.NSBoxSeparator)
        c.addSubview_(self.divider)

        self.recent_label = _secondary_label(
            AppKit.NSMakeRect(12, 162, 150, 18), t("recent")
        )
        c.addSubview_(self.recent_label)

        self.clear_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(268, 162, 80, 18)
        )
        self.clear_btn.setTitle_(t("clear"))
        self.clear_btn.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        self.clear_btn.setBordered_(False)
        self.clear_btn.setAlignment_(AppKit.NSRightTextAlignment)
        self.clear_btn.setTarget_(self)
        self.clear_btn.setAction_("clearHistory:")
        self.clear_btn.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
        c.addSubview_(self.clear_btn)
        _pointer_cursor(self.clear_btn, self)

        self.table_scroll = AppKit.NSScrollView.alloc().initWithFrame_(
            AppKit.NSMakeRect(12, 16, POPOVER_W - 24, 140)
        )
        self.table_scroll.setBorderType_(AppKit.NSNoBorder)
        self.table_scroll.setDrawsBackground_(False)
        self.table_scroll.setHasVerticalScroller_(True)
        self.table_scroll.setAutohidesScrollers_(True)
        self.table_scroll.setHasHorizontalScroller_(False)

        self.hist_table = AppKit.NSTableView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, POPOVER_W - 24, 140)
        )
        col = AppKit.NSTableColumn.alloc().initWithIdentifier_("row")
        col.setWidth_(POPOVER_W - 24)
        self.hist_table.addTableColumn_(col)
        self.hist_table.setHeaderView_(None)
        self.hist_table.setRowHeight_(26)
        self.hist_table.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.hist_table.setGridStyleMask_(AppKit.NSTableViewGridNone)
        self.hist_table.setIntercellSpacing_(AppKit.NSMakeSize(0, 0))
        self.hist_table.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        self.table_scroll.setFocusRingType_(AppKit.NSFocusRingTypeNone)
        self.hist_table.setDataSource_(self)
        self.hist_table.setDelegate_(self)
        self.hist_table.setTarget_(self)
        self.table_scroll.setDocumentView_(self.hist_table)
        c.addSubview_(self.table_scroll)
        _pointer_cursor(self.hist_table, self, in_visible_rect=True)

        self.hist_empty = _secondary_label(
            AppKit.NSMakeRect(12, 76, POPOVER_W - 24, 20), t("history_empty")
        )
        self.hist_empty.setAlignment_(AppKit.NSCenterTextAlignment)
        c.addSubview_(self.hist_empty)

        self._apply_history_state()

        self.popover = AppKit.NSPopover.alloc().init()
        self.popover.setContentViewController_(self.vc)
        # Semitransient: closes on outside click, stays open for in-popover menus.
        self.popover.setBehavior_(AppKit.NSPopoverBehaviorSemitransient)
        self.popover.setDelegate_(self)
        self._debounce_timer = None
        self._last_caption = ""
        try:
            self._key_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                AppKit.NSKeyDownMask, self._cmd_enter_filter
            )
        except (AttributeError, objc.error):
            self._key_monitor = None
        try:
            self._outside_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                AppKit.NSLeftMouseDownMask, self._outside_click
            )
        except (AttributeError, objc.error):
            self._outside_monitor = None

    def _outside_click(self, event):
        if self.popover.isShown():
            self.popover.close()

    def _set_history_toggle_icon(self):
        img = _symbol("clock", 16)
        if img is not None:
            self.hist_toggle_btn.setImage_(img)
            self.hist_toggle_btn.setImagePosition_(AppKit.NSImageOnly)
        else:
            self.hist_toggle_btn.setImage_(None)
            self.hist_toggle_btn.setTitle_("◷")
        self.hist_toggle_btn.setToolTip_(
            t("tip_history_collapse" if self.history_expanded else "tip_history_expand")
        )

    def _stop_fade(self):
        if self._fade_timer is not None:
            self._fade_timer.invalidate()
            self._fade_timer = None
        self.output_scroll.setAlphaValue_(1.0)

    def _apply_history_state(self):
        window = self.vc.view().window()
        self._stop_fade()
        if self.history_mode == "screen" and self.history_expanded:
            # Отдельный экран истории: перевод скрыт, список на весь поповер.
            self.input_scroll.setHidden_(True)
            self.placeholder.setHidden_(True)
            self.clear_text_btn.setHidden_(True)
            self.caption.setHidden_(True)
            self.copy_btn.setHidden_(True)
            self.output_scroll.setHidden_(True)
            self.divider.setHidden_(True)
            if self._divider_timer is not None:
                self._divider_timer.invalidate()
                self._divider_timer = None
            self._divider_wanted = 0.0
            self._divider_alpha = 0.0
            self.input_divider.setAlphaValue_(0.0)
            self.input_divider.setHidden_(True)
            self.recent_label.setFrame_(
                AppKit.NSMakeRect(12, POPOVER_H - 70, 150, 18)
            )
            self.clear_btn.setFrame_(
                AppKit.NSMakeRect(268, POPOVER_H - 70, 80, 18)
            )
            self.table_scroll.setFrame_(
                AppKit.NSMakeRect(12, 16, POPOVER_W - 24, POPOVER_H - 92)
            )
            self.hist_empty.setFrame_(
                AppKit.NSMakeRect(12, 200, POPOVER_W - 24, 20)
            )
            self.recent_label.setHidden_(False)
            self.clear_btn.setHidden_(False)
            self.table_scroll.setHidden_(False)
        else:
            # Экран перевода: встроенная история снизу (или свёрнута).
            self.input_scroll.setHidden_(False)
            self.clear_text_btn.setHidden_(False)
            self.caption.setHidden_(False)
            self.copy_btn.setHidden_(False)
            self.output_scroll.setHidden_(False)
            self.placeholder.setHidden_(bool(self.input_view.string()))
            if self.history_expanded:
                self.output_scroll.setFrame_(
                    AppKit.NSMakeRect(12, 192, POPOVER_W - 24, 100)
                )
            else:
                self.output_scroll.setFrame_(
                    AppKit.NSMakeRect(12, 16, POPOVER_W - 24, 276)
                )
            self.divider.setFrame_(
                AppKit.NSMakeRect(12, 184, POPOVER_W - 24, 1)
            )
            self.recent_label.setFrame_(
                AppKit.NSMakeRect(12, 162, 150, 18)
            )
            self.clear_btn.setFrame_(
                AppKit.NSMakeRect(268, 162, 80, 18)
            )
            self.table_scroll.setFrame_(
                AppKit.NSMakeRect(12, 16, POPOVER_W - 24, 140)
            )
            self.hist_empty.setFrame_(
                AppKit.NSMakeRect(12, 76, POPOVER_W - 24, 20)
            )
            self.divider.setHidden_(not self.history_expanded)
            self.recent_label.setHidden_(not self.history_expanded)
            self.clear_btn.setHidden_(not self.history_expanded)
            self.table_scroll.setHidden_(not self.history_expanded)
        self.hist_empty.setHidden_(
            not self.history_expanded or bool(self.history)
        )
        if not (self.history_mode == "screen" and self.history_expanded):
            # На экране перевода линия зависит от числа строк ввода.
            self._update_input_divider(animate=False)
        elif self._divider_timer is not None:
            self._divider_timer.invalidate()
            self._divider_timer = None
        self._set_history_toggle_icon()
        if window is not None:
            # Поле ввода прячется вместе с фокусом — уводим его явно,
            # иначе кольцо фокуса падает на кнопки языков.
            try:
                if self.history_mode == "screen" and self.history_expanded:
                    window.makeFirstResponder_(self.hist_table)
                else:
                    window.makeFirstResponder_(self.input_view)
            except (AttributeError, objc.error):
                pass

    def toggleHistory_(self, sender):
        self.history_expanded = not self.history_expanded
        if self.history_mode == "inline":
            save_history_expanded(self.history_expanded)
        self._apply_history_state()

    def _build_settings(self):
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSFullSizeContentViewWindowMask
        )
        self.settings = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(0, 0, SETTINGS_W, SETTINGS_H),
            style,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.settings.setTitle_(t("settings_title"))
        self.settings.setTitlebarAppearsTransparent_(True)
        self.settings.setTitleVisibility_(AppKit.NSWindowTitleHidden)
        self.settings.setReleasedWhenClosed_(False)
        self.settings.setLevel_(AppKit.NSFloatingWindowLevel)

        effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, SETTINGS_W, SETTINGS_H)
        )
        effect.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
        effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(AppKit.NSVisualEffectStateActive)
        effect.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        self.settings.setContentView_(effect)
        c = effect

        header = _label(AppKit.NSMakeRect(20, SETTINGS_H - 50, 200, 22), t("settings_title"))
        header.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
        c.addSubview_(header)

        self.autostart_box = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, SETTINGS_H - 72, 280, 22)
        )
        self.autostart_box.setButtonType_(AppKit.NSSwitchButton)
        self.autostart_box.setTitle_(t("autostart"))
        self.autostart_box.setTarget_(self)
        self.autostart_box.setAction_("autostartToggled:")
        c.addSubview_(self.autostart_box)
        _pointer_cursor(self.autostart_box, self)

        hint = _secondary_label(
            AppKit.NSMakeRect(20, SETTINGS_H - 94, 280, 18),
            t("autostart_hint"),
        )
        c.addSubview_(hint)

        c.addSubview_(
            _label(AppKit.NSMakeRect(20, SETTINGS_H - 126, 140, 22), t("ui_language"))
        )
        self.ui_lang_codes = [
            c for c in UI_LANG_CODES if c == "system" or c in UI_LANG_NATIVE
        ]
        self.ui_lang_popup = _popup(
            AppKit.NSMakeRect(168, SETTINGS_H - 130, 132, 26),
            [
                t("ui_lang_system") if c == "system" else UI_LANG_NATIVE[c]
                for c in self.ui_lang_codes
            ],
            "uiLangChanged:",
            self,
        )
        c.addSubview_(self.ui_lang_popup)
        _pointer_cursor(self.ui_lang_popup, self)

        c.addSubview_(
            _secondary_label(
                AppKit.NSMakeRect(20, SETTINGS_H - 152, 280, 18),
                t("ui_lang_note"),
            )
        )

        c.addSubview_(
            _label(AppKit.NSMakeRect(20, SETTINGS_H - 184, 140, 22), t("history_mode"))
        )
        self.history_mode_popup = _popup(
            AppKit.NSMakeRect(168, SETTINGS_H - 188, 132, 26),
            [t("history_mode_inline"), t("history_mode_screen")],
            "historyModeChanged:",
            self,
        )
        c.addSubview_(self.history_mode_popup)
        _pointer_cursor(self.history_mode_popup, self)

        divider = AppKit.NSBox.alloc().initWithFrame_(
            AppKit.NSMakeRect(20, 44, SETTINGS_W - 40, 1)
        )
        divider.setBoxType_(AppKit.NSBoxSeparator)
        c.addSubview_(divider)

        c.addSubview_(
            _secondary_label(
                AppKit.NSMakeRect(20, 16, SETTINGS_W - 40, 18),
                t("version_line", v=APP_VERSION),
            )
        )

    @staticmethod
    def _is_secondary_click(event) -> bool:
        if event.type() in (
            AppKit.NSEventTypeRightMouseDown,
            AppKit.NSEventTypeRightMouseUp,
        ):
            return True
        return bool(event.modifierFlags() & AppKit.NSControlKeyMask)

    def toggle_(self, sender):
        now = time.time()
        if now - self._last_click < CLICK_DEBOUNCE:
            return
        self._last_click = now
        event = AppKit.NSApplication.sharedApplication().currentEvent()
        if event is not None and self._is_secondary_click(event):
            AppKit.NSMenu.popUpContextMenu_withEvent_forView_(
                self.context_menu, event, self.status.button()
            )
            return
        if self.popover.isShown():
            self.popover.close()
        else:
            self.showPopover_(sender)

    def showPopover_(self, sender):
        self._stop_fade()
        if self.history_mode == "screen" and self.history_expanded:
            self.history_expanded = False
            self._apply_history_state()
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        button = self.status.button()
        self.popover.showRelativeToRect_ofView_preferredEdge_(
            button.bounds(), button, AppKit.NSMinYEdge
        )

    def application_openURLs_(self, app, urls):
        for url in urls:
            self._open_translate_url(str(url))

    def _open_translate_url(self, url):
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return
        if parsed.scheme.lower() != "translatebar":
            return
        query = urllib.parse.parse_qs(parsed.query)
        text = (query.get("text", [""])[0] or "").strip()
        self.showPopover_(None)
        if not text:
            return
        self.input_view.setString_(text)
        self.placeholder.setHidden_(True)
        self._update_clear_button()
        self._update_input_divider(animate=True)
        self.requestTranslation()

    def popoverDidShow_(self, notification):
        window = self.vc.view().window()
        if window is not None:
            window.makeFirstResponder_(self.input_view)

    def popoverDidClose_(self, notification):
        if self._debounce_timer is not None:
            self._debounce_timer.invalidate()
            self._debounce_timer = None
        if self.history_mode == "screen" and self.history_expanded:
            self.history_expanded = False
            self._apply_history_state()

    def mouseEntered_(self, event):
        AppKit.NSCursor.pointingHandCursor().set()

    def mouseExited_(self, event):
        AppKit.NSCursor.arrowCursor().set()

    def uiLangChanged_(self, sender):
        idx = self.ui_lang_popup.indexOfSelectedItem()
        codes = self.ui_lang_codes
        code = codes[idx] if 0 <= idx < len(codes) else "system"
        _write_settings({"ui_lang": code})

    def _restore_ui_lang(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            saved = str(data.get("ui_lang", "system")) if isinstance(data, dict) else "system"
        except (OSError, ValueError, AttributeError):
            saved = "system"
        codes = self.ui_lang_codes
        if saved not in codes:
            saved = "system"
        self.ui_lang_popup.selectItemAtIndex_(codes.index(saved))

    def historyModeChanged_(self, sender):
        idx = self.history_mode_popup.indexOfSelectedItem()
        mode = HISTORY_MODES[idx] if 0 <= idx < len(HISTORY_MODES) else HISTORY_MODE_DEFAULT
        self.history_mode = mode
        save_history_mode(mode)
        if mode == "screen":
            # Вариант А: отдельный экран всегда начинается с перевода.
            self.history_expanded = False
        else:
            self.history_expanded = load_history_expanded()
        self._apply_history_state()

    def _restore_history_mode(self):
        mode = load_history_mode()
        if mode not in HISTORY_MODES:
            mode = HISTORY_MODE_DEFAULT
        self.history_mode_popup.selectItemAtIndex_(HISTORY_MODES.index(mode))

    def openSettings_(self, sender):
        self.autostart_box.setState_(
            AppKit.NSOnState if is_autostart_enabled() else AppKit.NSOffState
        )
        self._restore_ui_lang()
        self._restore_history_mode()
        # Popover lives at NSStatusWindowLevel (25); plain floating (3) would open behind it.
        level = AppKit.NSFloatingWindowLevel
        try:
            popover_window = self.vc.view().window()
            if popover_window is not None and self.popover.isShown():
                level = popover_window.level() + 1
        except (AttributeError, objc.error):
            pass
        self.settings.setLevel_(level)
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.settings.center()
        self.settings.orderFrontRegardless()
        self.settings.makeKeyAndOrderFront_(None)

    def autostartToggled_(self, sender):
        want = sender.state() == AppKit.NSOnState
        ok, msg = set_autostart(want)
        sender.setState_(
            AppKit.NSOnState if is_autostart_enabled() else AppKit.NSOffState
        )
        if not ok:
            _show_alert(t("autostart_error_title"), msg)

    def quitApp_(self, sender):
        AppKit.NSApplication.sharedApplication().terminate_(None)

    def _set_caption(self, text):
        self._last_caption = text
        self.caption.setStringValue_(text)

    def _target_code(self):
        # +1: item 0 в pullsDown — заголовок кнопки, языки начинаются с индекса 1.
        idx = self.target_popup.indexOfSelectedItem() - 1
        if 0 <= idx < len(TARGET_LANGUAGES):
            return TARGET_LANGUAGES[idx][1]
        return DEFAULT_TARGET

    def _source_code(self):
        idx = self.source_popup.indexOfSelectedItem() - 1
        if 0 <= idx < len(SOURCE_LANGUAGES):
            return SOURCE_LANGUAGES[idx][1]
        return SOURCE_AUTO

    def _select_target(self, code):
        for i, (_, google, _) in enumerate(TARGET_LANGUAGES):
            if google.lower() == code.lower():
                self.target_popup.selectItemAtIndex_(i + 1)
                return

    def _select_source(self, code):
        for i, (_, google, _) in enumerate(SOURCE_LANGUAGES):
            if google.lower() == code.lower():
                self.source_popup.selectItemAtIndex_(i + 1)
                return

    def _restore_languages(self):
        self._select_source(load_source_lang())
        self._select_target(load_target_lang())
        self._sync_language_titles()

    def _sync_language_titles(self):
        # pullsDown-кнопки не обновляют заголовок сами — выставляем вручную.
        self.source_popup.setTitle_(lang_name(self._source_code()))
        self.target_popup.setTitle_(lang_name(self._target_code()))

    def _save_languages(self):
        save_source_lang(self._source_code())
        save_target_lang(self._target_code())
        self._sync_language_titles()

    def languageChanged_(self, sender):
        self._save_languages()
        self._retranslate_if_needed()

    def sourceChanged_(self, sender):
        self._save_languages()
        self._retranslate_if_needed()

    def _retranslate_if_needed(self):
        if self.input_view.string().strip():
            self.requestTranslation()
        else:
            self._set_caption(self._direction_caption())

    def swapLanguages_(self, sender):
        src = self._source_code()
        tgt = self._target_code()
        if src == SOURCE_AUTO:
            self._select_source(tgt)
            self._select_target(DEFAULT_TARGET)
        else:
            self._select_source(tgt)
            self._select_target(src)
        self._save_languages()

    @staticmethod
    def _is_pure_deletion(old: str, new: str) -> bool:
        if new == old:
            return True
        it = iter(old)
        return all(ch in it for ch in new)

    def textDidChange_(self, notification):
        new = str(self.input_view.string())
        self.placeholder.setHidden_(bool(new))
        self._update_clear_button()
        # Синхронный пересчёт: _line_count берёт максимум из layout и оценки
        # по ширине, поэтому устаревший layout не может занизить число строк.
        self._update_input_divider(animate=True)
        if self._debounce_timer is not None:
            self._debounce_timer.invalidate()
            self._debounce_timer = None
        if self._is_pure_deletion(self._prev_input, new):
            # Удаление не пересчитывает перевод: вывод замирает
            # на последнем результате, пока не начнут набирать заново.
            self._prev_input = new
            return
        self._prev_input = new
        self._debounce_timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            DEBOUNCE_INTERVAL, self, "debounceFired:", None, False
        )

    def _fade_in_output(self):
        try:
            reduce = AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()
        except (AttributeError, objc.error):
            reduce = False
        if self._fade_timer is not None:
            self._fade_timer.invalidate()
            self._fade_timer = None
        if reduce:
            self.output_scroll.setAlphaValue_(1.0)
            return
        # Ручной фейд: animator()/CoreAnimation в этой иерархии не анимирует alpha.
        self._fade_step = 0
        self.output_scroll.setAlphaValue_(0.0)
        self._fade_timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            FADE_STEP, self, "fadeTick:", None, True
        )

    def fadeTick_(self, timer):
        self._fade_step += 1
        alpha = min(1.0, self._fade_step * FADE_STEP / FADE_DURATION)
        self.output_scroll.setAlphaValue_(alpha)
        if alpha >= 1.0:
            timer.invalidate()
            self._fade_timer = None

    def _line_count(self, view) -> int:
        """Число отображаемых строк: максимум из layout-оценки и оценки по ширине."""
        text = str(view.string())
        if not text:
            return 0
        layout_count = 0
        try:
            container = view.textContainer()
            layout = view.layoutManager()
            if layout is not None and container is not None:
                layout.ensureLayoutForTextContainer_(container)
                try:
                    layout.ensureLayoutForCharacterRange_(
                        AppKit.NSMakeRange(0, layout.numberOfCharacters())
                    )
                except (AttributeError, objc.error):
                    pass
                total = layout.numberOfGlyphs()
                index = 0
                while index < total:
                    try:
                        _rect, rng = layout.lineFragmentRectForGlyphAtIndex_effectiveRange_(
                            index, None
                        )
                    except (AttributeError, objc.error):
                        break
                    layout_count += 1
                    index = rng.location + (rng.length or 1)
        except (AttributeError, objc.error):
            layout_count = 0
        # Оценка по ширине: не зависит от актуальности layout.
        width = 0.0
        try:
            width = float(view.textContainer().containerSize().width)
        except (AttributeError, objc.error):
            width = float(view.bounds().size.width)
        if width <= 1.0:
            width = float(view.bounds().size.width) or 300.0
        font = view.font()
        char_w = 0.0
        try:
            char_w = float(font.maximumAdvancementForGlyph_(font.glyphWithName_("M")).width)
        except (AttributeError, objc.error):
            char_w = 0.0
        if char_w <= 1.0:
            char_w = float(font.pointSize()) * 0.6 or 8.0
        per_line = max(1, int(width // char_w))
        est = 0
        paragraphs = text.split("\n")
        # Завершающий перенос не создаёт новую отображаемую строку.
        if len(paragraphs) > 1 and paragraphs[-1] == "":
            paragraphs = paragraphs[:-1]
        for paragraph in paragraphs:
            est += max(1, -(-len(paragraph) // per_line))
        # Приоритет layout: он точен. Оценка — только если layout недоступен.
        return layout_count if layout_count > 0 else est

    def _set_divider_alpha(self, alpha: float) -> None:
        self._divider_alpha = alpha
        self.input_divider.setAlphaValue_(alpha)
        self.input_divider.setHidden_(alpha <= 0.0)

    def _divider_should_show(self) -> bool:
        return self._line_count(self.input_view) >= DIVIDER_LINE_THRESHOLD

    def _update_input_divider(self, animate: bool = True) -> None:
        if not hasattr(self, "input_divider"):
            return
        wanted = 1.0 if self._divider_should_show() else 0.0
        if abs(self._divider_alpha - wanted) < 0.01 and not self.input_divider.isHidden():
            return
        previous = self._divider_alpha
        self._divider_wanted = wanted
        self._divider_alpha = wanted
        if wanted > 0.0:
            self.input_divider.setHidden_(False)
        # Состояние применяется сразу, плавность — только визуальный эффект
        # Core Animation (таймеры и animator() здесь ненадёжны).
        if animate and not self._reduce_motion() and previous != wanted:
            self._animate_divider_opacity(previous, wanted)
        else:
            if self._divider_timer is not None:
                self._divider_timer.invalidate()
                self._divider_timer = None
            self.input_divider.setAlphaValue_(wanted)
            self.input_divider.setHidden_(wanted <= 0.0)

    def _animate_divider_opacity(self, from_alpha: float, to_alpha: float) -> None:
        layer = self.input_divider.layer()
        if layer is None:
            self.input_divider.setAlphaValue_(to_alpha)
            self.input_divider.setHidden_(to_alpha <= 0.0)
            return
        anim = AppKit.CABasicAnimation.animationWithKeyPath_("opacity")
        anim.setFromValue_(from_alpha)
        anim.setToValue_(to_alpha)
        anim.setDuration_(FADE_DURATION)
        anim.setRemovedOnCompletion_(True)
        layer.addAnimation_forKey_(anim, "dividerFade")
        self.input_divider.setAlphaValue_(to_alpha)
        if to_alpha <= 0.0:
            # Скрываем после завершения анимации, не блокируя финальное состояние.
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                FADE_DURATION + 0.02, self, "hideDividerAfterFade:", None, False
            )
        else:
            self.input_divider.setHidden_(False)

    def hideDividerAfterFade_(self, timer):
        if self._divider_wanted <= 0.0:
            self.input_divider.setHidden_(True)

    @staticmethod
    def _reduce_motion() -> bool:
        try:
            return bool(
                AppKit.NSWorkspace.sharedWorkspace()
                .accessibilityDisplayShouldReduceMotion()
            )
        except (AttributeError, objc.error):
            return False

    def _update_clear_button(self):
        target = 1.0 if self.input_view.string().strip() else 0.0
        if abs(self.clear_text_btn.alphaValue() - target) < 0.01:
            return
        AppKit.NSAnimationContext.beginGrouping()
        AppKit.NSAnimationContext.currentContext().setDuration_(0.2)
        self.clear_text_btn.animator().setAlphaValue_(target)
        AppKit.NSAnimationContext.endGrouping()

    def clearText_(self, sender):
        if self._debounce_timer is not None:
            self._debounce_timer.invalidate()
            self._debounce_timer = None
        self._prev_input = ""
        self.input_view.setString_("")
        self.output_view.setString_("")
        self._update_input_divider(animate=True)
        self.placeholder.setHidden_(False)
        self._update_clear_button()
        self._set_caption(self._direction_caption())
        window = self.vc.view().window()
        if window is not None:
            window.makeFirstResponder_(self.input_view)

    def debounceFired_(self, timer):
        self._debounce_timer = None
        self.requestTranslation()

    def _cmd_enter_filter(self, event):
        try:
            if event.keyCode() == 53:
                if self.popover.isShown():
                    self.popover.close()
                return None
            if event.keyCode() == 36 and (event.modifierFlags() & AppKit.NSCommandKeyMask):
                self.requestTranslation()
                return None
        except (AttributeError, objc.error):
            pass
        return event

    def copyResult_(self, sender):
        text = self.output_view.string().strip()
        if not text:
            return
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
        self._set_caption(t("copied"))
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.2, self, "restoreCaption:", None, False
        )

    def restoreCaption_(self, timer):
        self.caption.setStringValue_(self._last_caption)

    def _direction_caption(self):
        return f"{lang_name(self._source_code())} → {lang_name(self._target_code())}"

    def requestTranslation(self):
        text = self.input_view.string().strip()
        self._prev_input = str(self.input_view.string())
        if not text:
            self.output_view.setString_("")
            self._set_caption(self._direction_caption())
            return
        target = self._target_code()
        source = self._source_code()
        self._save_languages()
        self._req_id += 1
        req = self._req_id
        self._set_caption(t("translating"))
        threading.Thread(
            target=self._translate_worker, args=(text, target, source, req), daemon=True
        ).start()

    def _translate_worker(self, text, target, source, req):
        cached = lookup_history(self.history, text, target, source)
        if cached is not None:
            cached_result, cached_src = cached
            payload = {
                "ok": True,
                "req": req,
                "text": text,
                "result": cached_result,
                "src": cached_src or "auto",
                "target": target,
                "via": "cache",
            }
        else:
            try:
                result, src, via = translate_with_meta(text, target, source)
                payload = {
                    "ok": True,
                    "req": req,
                    "text": text,
                    "result": result,
                    "src": src,
                    "target": target,
                    "via": via,
                }
            except Exception as exc:
                payload = {"ok": False, "req": req, "error": str(exc)}
        # dict(): payload crosses the ObjC bridge as NSDictionary.
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyTranslation:", payload, False
        )

    def applyTranslation_(self, payload):
        payload = dict(payload)
        if payload.get("req") != self._req_id:
            return
        if not payload.get("ok"):
            err = str(payload.get("error"))
            if err == "NO_CONNECTION":
                err = t("no_connection")
            self.output_view.setString_("")
            self._set_caption(f"{t('error_prefix')}: {err}")
            return
        result = payload["result"]
        self.output_view.setString_(result)
        self._fade_in_output()
        src = str(payload.get("src", "auto"))
        target = str(payload.get("target", ""))
        self._set_caption(f"{lang_name(src)} → {lang_name(target)}")
        if payload.get("via") not in ("cache", "same"):
            self.history = add_to_history(
                self.history,
                payload["text"],
                result,
                src_lang=src,
                dst_lang=target,
                provider=str(payload.get("via", "")),
            )
            save_history(self.history)
            self._refresh_history()

    def numberOfRowsInTableView_(self, table):
        return len(self.history)

    def tableView_objectValueForTableColumn_row_(self, table, column, row):
        if 0 <= row < len(self.history):
            item = self.history[row]
            when = relative_time(item.get("ts", 0)) if item.get("ts") else t("earlier")
            return f"{format_history_item(item)}  ·  {when}"
        return ""

    def tableViewSelectionDidChange_(self, notification):
        row = self.hist_table.selectedRow()
        if 0 <= row < len(self.history):
            item = self.history[row]
            if self.history_mode == "screen" and self.history_expanded:
                self.history_expanded = False
                self._apply_history_state()
            self.input_view.setString_(item["src"])
            self._prev_input = item["src"]
            self.output_view.setString_(item["dst"])
            self._update_input_divider(animate=True)
            self.placeholder.setHidden_(True)
            self._update_clear_button()
            self._set_caption(
                f"{lang_name(item.get('src_lang', 'auto'))} → "
                f"{lang_name(item.get('dst_lang', ''))}"
            )
            self.hist_table.deselectAll_(None)
            window = self.vc.view().window()
            if window is not None:
                window.makeFirstResponder_(self.input_view)

    def clearHistory_(self, sender):
        self.history = []
        save_history(self.history)
        self._refresh_history()

    def _refresh_history(self):
        self.hist_table.reloadData()
        self.hist_empty.setHidden_(
            not self.history_expanded or bool(self.history)
        )


if __name__ == "__main__":
    if "--toggle-autostart" in sys.argv:
        ok, msg = set_autostart(not is_autostart_enabled())
        print(("OK " if ok else "FAIL ") + msg)
        raise SystemExit(0 if ok else 1)
    _lock = ensure_single_instance()
    if _lock is None:
        raise SystemExit(t("already_running"))
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    _install_main_menu()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()
