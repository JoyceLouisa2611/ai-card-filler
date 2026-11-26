# -*- coding: utf-8 -*-
"""AI Card Filler: fill Anki cards with AI. Menu: Tools -> AI Card Filler."""
from aqt import mw, gui_hooks
from aqt.qt import QAction, QDialogButtonBox, QTimer, qconnect

from .i18n import tr

PKG = __name__.split(".")[0]


def _open_hub():
    from .ui import HubDialog
    dlg = getattr(mw, "_ai_card_filler_dialog", None)
    if dlg is not None and dlg.isVisible():
        dlg.showNormal()
        dlg.raise_()
        dlg.activateWindow()
        return
    dlg = HubDialog(mw)
    mw._ai_card_filler_dialog = dlg  # giữ tham chiếu
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def _on_add_init(addcards):
    # nút phụ trong cửa sổ Add gốc
    try:
        btn = addcards.form.buttonBox.addButton("AI Card Filler", QDialogButtonBox.ButtonRole.ActionRole)
        qconnect(btn.clicked, lambda *_: (addcards.close(), _open_hub()))
    except Exception:
        pass
    # chế độ "bấm Add là mở Hub"
    if getattr(mw, "_acf_bypass", False):
        mw._acf_bypass = False
        return
    cfg = mw.addonManager.getConfig(PKG) or {}
    if cfg.get("open_on_add"):
        QTimer.singleShot(0, lambda: (addcards.close(), _open_hub()))


def _fill_from_browser(browser):
    """Điền ô trống cho các ghi chú đang chọn trong Browser."""
    from aqt.utils import tooltip
    try:
        ids = list(browser.selected_notes())
    except Exception:  # noqa: BLE001
        ids = []
    if not ids:
        tooltip(tr('Hãy chọn ít nhất một thẻ trong Browser.'), parent=browser)
        return
    from .fill_existing import FillExistingDialog
    dlg = FillExistingDialog(browser, ids)
    browser._acf_fill_dialog = dlg  # giữ tham chiếu
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def _browser_context_menu(browser, menu):
    menu.addSeparator()
    act = menu.addAction(tr('AI Card Filler: điền ô trống…'))
    qconnect(act.triggered, lambda *_: _fill_from_browser(browser))


def _browser_menus(browser):
    try:
        notes_menu = browser.form.menu_Notes
        notes_menu.addSeparator()
        act = notes_menu.addAction(tr('AI Card Filler: điền ô trống…'))
        qconnect(act.triggered, lambda *_: _fill_from_browser(browser))
    except Exception:  # noqa: BLE001
        pass


if mw is not None:
    _action = QAction("AI Card Filler…", mw)
    qconnect(_action.triggered, _open_hub)
    mw.form.menuTools.addAction(_action)
    gui_hooks.add_cards_did_init.append(_on_add_init)
    gui_hooks.browser_will_show_context_menu.append(_browser_context_menu)
    gui_hooks.browser_menus_did_init.append(_browser_menus)
