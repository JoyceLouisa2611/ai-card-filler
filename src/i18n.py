# -*- coding: utf-8 -*-
"""Ngôn ngữ giao diện/prompt: theo ngôn ngữ đang chọn trong Anki (Vietnamese hoặc English)."""
import os


def lang():
    forced = os.environ.get("ACF_LANG")
    if forced:
        return forced
    try:
        import anki.lang
        cur = (anki.lang.current_lang or "en").lower()
    except Exception:  # noqa: BLE001
        cur = "en"
    return "vi" if cur.startswith("vi") else "en"


def tr(s):
    if lang() == "vi":
        return s
    from .en import EN
    return EN.get(s, s)
