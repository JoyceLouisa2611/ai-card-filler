# -*- coding: utf-8 -*-
from __future__ import annotations

import webbrowser
import urllib.parse
import json

import aqt
from aqt.qt import *
from aqt.utils import showInfo, showWarning, tooltip

from . import core
from .i18n import tr
from .theme import apply_theme, capture_web_canvas, appearance, colors
from .drafts import DraftStore
from .animation import StudyCat, AnimatedLabel
from .decorations import StudyGarden

PKG = __name__.split(".")[0]
def _night():
    try:
        from aqt.theme import theme_manager
        return bool(theme_manager.night_mode)
    except Exception:  # noqa: BLE001
        return False


def _mw():
    return aqt.mw


def get_cfg():
    c = _mw().addonManager.getConfig(PKG) or {}
    for k, v in {"gemini_key": "", "gemini_model": "gemini-2.5-flash-lite", "image_max_side": 512, "tag": "ai-card-filler", "open_on_add": False, "extra": "", "types": {},
                 "provider": "gemini", "openai": {"base_url": "https://api.openai.com/v1", "key": "", "model": "gpt-4o-mini"},
                 "anthropic": {"key": "", "model": "claude-haiku-5-5"}, "auto_fallback": True, "chunk_size": 20,
                 "tts_model": "gemini-2.5-flash-preview-tts", "tts_voice": "Kore"}.items():
        c.setdefault(k, v)
    return c


def save_cfg(c):
    _mw().addonManager.writeConfig(PKG, c)


def shrink_jpeg(data, max_side=512):
    img = QImage()
    if not img.loadFromData(data):
        raise ValueError(tr('Không đọc được ảnh này.'))
    if max(img.width(), img.height()) > max_side:
        img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QImage(img.width(), img.height(), QImage.Format.Format_RGB32)
    out.fill(QColor("white"))
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    out.save(buf, "JPEG", 82)
    return bytes(ba)


def prepare_image(data, max_side=512):
    if data.startswith((b'GIF87a', b'GIF89a')):
        if len(data) > 16 * 1024 * 1024:
            raise ValueError(tr('GIF quá lớn (tối đa 16 MB).'))
        image = QImage()
        if not image.loadFromData(data):
            raise ValueError(tr('Không đọc được ảnh này.'))
        # Keep the original bytes, frames, timing and transparency.
        return bytes(data)
    return shrink_jpeg(data, max_side)


def _motion_allowed():
    try:
        reduced = _mw().pm.reduce_motion()
    except Exception:
        reduced = False
    return bool(get_cfg().get('animations', True) and not reduced)


def pixmap_of(data, w, h):
    pm = QPixmap()
    if data and pm.loadFromData(data):
        return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return None


def bg(fn, done):
    """Chạy fn ở luồng nền; done(kết_quả, lỗi) chạy ở luồng giao diện."""
    def cb(fut):
        try:
            res = fut.result()
        except Exception as e:  # noqa: BLE001
            done(None, e)
        else:
            done(res, None)
    _mw().taskman.run_in_background(fn, cb)


# ============================================================ cấu hình ô + prompt
class TypeConfigDialog(QDialog):
    def __init__(self, parent, model_name, field_names, tcfg):
        super().__init__(parent)
        self.setWindowTitle(tr('Cấu hình ô và prompt: %s') % model_name)
        self.resize(900, 620)
        apply_theme(self, _night())
        self.field_names = field_names
        self.model_name = model_name
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr('Lời mở đầu prompt (vai trò của AI, cách xưng hô, độ khó…):')))
        self.intro = QPlainTextEdit(tcfg["intro"])
        self.intro.setFixedHeight(80)
        lay.addWidget(self.intro)
        lay.addWidget(QLabel(tr('Mỗi ô: chọn ai điền (chữ, ảnh, âm thanh hay bỏ qua) và viết mô tả để AI hiểu ô đó cần gì. Với ô âm thanh, mô tả là TÊN Ô cần đọc (để trống thì đọc ô đầu tiên). Ô đầu tiên là từ bạn nhập nên luôn do bạn quyết định.')))
        self.tbl = QTableWidget(len(field_names), 3)
        self.tbl.setHorizontalHeaderLabels([tr('Ô'), tr('Vai trò'), tr('Mô tả cho AI (càng cụ thể càng tốt)')])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setColumnWidth(0, 160)
        self.tbl.setColumnWidth(1, 155)
        self.tbl.verticalHeader().setDefaultSectionSize(54)
        self.tbl.setAlternatingRowColors(True)
        self.combos = {}
        for i, n in enumerate(field_names):
            it = QTableWidgetItem(n)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(i, 0, it)
            cb = QComboBox()
            for k, label in core.ROLE_NAMES.items():
                cb.addItem(label, k)
            cb.setCurrentIndex(list(core.ROLE_NAMES).index(tcfg["roles"].get(n, core.ROLE_AI)))
            if i == 0:
                cb.setEnabled(False)
            self.tbl.setCellWidget(i, 1, cb)
            self.combos[n] = cb
            self.tbl.setItem(i, 2, QTableWidgetItem(tcfg["hints"].get(n, "")))
        lay.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        reset = QPushButton(tr('Khôi phục mặc định'))
        qconnect(reset.clicked, self._reset)
        row.addWidget(reset)
        self.preset_cb = QComboBox()
        self.preset_cb.addItem(tr('Áp dụng mẫu có sẵn…'), None)
        for k, v in core.CFG_PRESETS.items():
            self.preset_cb.addItem(tr(v["label"]), k)
        qconnect(self.preset_cb.activated, self._preset_picked)
        row.addWidget(self.preset_cb)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        qconnect(bb.accepted, self.accept)
        qconnect(bb.rejected, self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def _reset(self):
        d = core.default_type_config(self.field_names)
        self.intro.setPlainText(d["intro"])
        for i, n in enumerate(self.field_names):
            self.combos[n].setCurrentIndex(list(core.ROLE_NAMES).index(d["roles"][n]))
            self.tbl.item(i, 2).setText(d["hints"].get(n, ""))

    def _preset_picked(self, i):
        key = self.preset_cb.itemData(i)
        res = core.apply_preset(self.field_names, key) if key else None
        if not res:
            return
        intro, hints = res
        self.intro.setPlainText(intro)
        for r, n in enumerate(self.field_names):
            if n in hints:
                self.tbl.item(r, 2).setText(hints[n])
        self.preset_cb.setCurrentIndex(0)

    def result_config(self):
        roles, hints = {}, {}
        for i, n in enumerate(self.field_names):
            roles[n] = self.combos[n].currentData()
            hints[n] = self.tbl.item(i, 2).text().strip()
        roles[self.field_names[0]] = core.ROLE_AI
        return {"intro": self.intro.toPlainText().strip() or core.DEFAULT_INTRO, "roles": roles, "hints": hints}


# ============================================================ ô ảnh
class ImageSlot(QFrame):
    def __init__(self, dlg, field):
        super().__init__()
        self.dlg, self.field = dlg, field
        self.row = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)
        left = QVBoxLayout()
        self.thumb = AnimatedLabel(size=128)
        self.thumb.setText(tr('chưa có ảnh'))
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedSize(128, 94)
        self.thumb.setObjectName("imageThumb")
        left.addWidget(self.thumb)
        btns = QGridLayout()
        for i, (label, fn) in enumerate([(tr('Chọn ảnh'), self.pick_file), (tr('Dán ảnh'), self.paste), (tr('Xóa ảnh'), self.clear)]):
            b = QPushButton(label)
            b.setAutoDefault(False)
            b.setObjectName("quiet")
            qconnect(b.clicked, fn)
            btns.addWidget(b, i // 2, i % 2)
        left.addLayout(btns)
        lay.addLayout(left)
        right = QVBoxLayout()
        self.q = QLineEdit()
        self.q.setAccessibleName(tr("Từ khóa tìm ảnh (tiếng Anh)"))
        self.q.setPlaceholderText(tr('Từ khóa tìm ảnh (tiếng Anh)'))
        qconnect(self.q.editingFinished, self._q_edited)
        right.addWidget(self.q)
        r1 = QHBoxLayout()
        self.find_btn = QPushButton(tr('Tìm ảnh'))
        qconnect(self.find_btn.clicked, lambda: self.search())
        self.google_btn = QPushButton(tr('Google Ảnh'))
        qconnect(self.google_btn.clicked, self.google)
        r1.addWidget(self.find_btn)
        r1.addWidget(self.google_btn)
        r1.addStretch(1)
        right.addLayout(r1)
        self.cands = QListWidget()
        self.cands.setViewMode(QListWidget.ViewMode.IconMode)
        self.cands.setFlow(QListWidget.Flow.LeftToRight)
        self.cands.setWrapping(True)
        self.cands.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.cands.setMovement(QListWidget.Movement.Static)
        self.cands.setIconSize(QSize(72, 72))
        self.cands.setGridSize(QSize(80, 80))
        self.cands.setMinimumHeight(84)
        qconnect(self.cands.itemClicked, self._pick_cand)
        right.addWidget(self.cands)
        lay.addLayout(right, 1)
        self.setEnabled(False)
        self.setMinimumWidth(270)
        self.setMinimumHeight(200)
        self.find_btn.setAutoDefault(False)
        self.google_btn.setAutoDefault(False)
        self._loading = False

    # ---- hiển thị
    def show_row(self, row):
        self.row = row
        self.setEnabled(row is not None)
        if row is None:
            self.thumb.clear_animation()
            self.thumb.setText(tr('chưa có ảnh'))
            self.thumb.setPixmap(QPixmap())
            self.q.setText("")
            self.cands.clear()
            return
        self.q.setText(self._query(row))
        self._refresh_thumb()
        self._refresh_cands()

    def _query(self, row):
        qs = row["q"].get(self.field, ["", ""])
        if qs[0]:
            return qs[0]
        first = self.dlg.field_names[0]
        return row["f"].get(first, "")

    def _refresh_thumb(self):
        data = self.row["img"].get(self.field) if self.row else None
        self.thumb.clear_animation()
        if data and data.startswith((b'GIF87a', b'GIF89a')):
            self.thumb.set_animation_enabled(_motion_allowed())
            if self.thumb.play_data(data):
                self.dlg.update_img_cell(self.row, self.field)
                return
        pm = pixmap_of(data, 124, 90)
        if pm:
            self.thumb.setPixmap(pm)
        else:
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText(tr('chưa có ảnh'))
        self.dlg.update_img_cell(self.row, self.field)

    def _refresh_cands(self):
        self.cands.clear()
        if not self.row:
            return
        thumbs = self.row["thumbs"].get(self.field, [])
        for i, c in enumerate(self.row["cands"].get(self.field, [])):
            data = thumbs[i] if i < len(thumbs) else None
            it = QListWidgetItem()
            pm = pixmap_of(data, 72, 72)
            if pm:
                it.setIcon(QIcon(pm))
            else:
                it.setText("…")
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setToolTip(c.get("src", ""))
            self.cands.addItem(it)
        self._load_missing_thumbs()

    def _load_missing_thumbs(self):
        if self._loading or not self.row:
            return
        row, field = self.row, self.field
        cands = row["cands"].get(field, [])
        thumbs = row["thumbs"].setdefault(field, [])
        while len(thumbs) < len(cands):
            thumbs.append(None)
        todo = [(i, cands[i]["thumb"]) for i, t in enumerate(thumbs) if t is None and not (cands[i].get("failed"))]
        if not todo:
            return
        self._loading = True

        def task():
            out = []
            for i, u in todo:
                try:
                    out.append((i, core.http_get(u, timeout=15)))
                except Exception:  # noqa: BLE001
                    out.append((i, b""))
            return out

        def done(res, err):
            self._loading = False
            for i, d in (res or []):
                if d:
                    thumbs[i] = d
                else:
                    cands[i]["failed"] = True
            if self.row is row:
                self._refresh_cands_icons()
        bg(task, done)

    def _refresh_cands_icons(self):
        thumbs = self.row["thumbs"].get(self.field, [])
        for k in range(self.cands.count()):
            it = self.cands.item(k)
            i = it.data(Qt.ItemDataRole.UserRole)
            pm = pixmap_of(thumbs[i], 72, 72) if i < len(thumbs) else None
            if pm:
                it.setIcon(QIcon(pm))
                it.setText("")

    # ---- hành động
    def _q_edited(self):
        if self.row is not None:
            qs = self.row["q"].setdefault(self.field, ["", ""])
            qs[0] = self.q.text().strip()

    def set_image(self, data):
        if self.row is None:
            return
        try:
            self.row["img"][self.field] = prepare_image(data, int(get_cfg().get("image_max_side", 512)))
        except Exception as e:  # noqa: BLE001
            showWarning(str(e))
            return
        self._refresh_thumb()

    def clear(self):
        if self.row is not None:
            self.row["img"].pop(self.field, None)
            self._refresh_thumb()

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Chọn ảnh'), "", tr('Ảnh (*.png *.jpg *.jpeg *.webp *.gif *.bmp)'))
        if path:
            try:
                with open(path, "rb") as f:
                    self.set_image(f.read())
            except OSError as error:
                showWarning(str(error))

    def paste(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            tooltip(tr('Clipboard chưa có ảnh. Hãy copy ảnh trước (chuột phải ảnh → Sao chép hình ảnh).'), parent=self.dlg)
            return
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        self.set_image(bytes(ba))

    def google(self):
        q = self.q.text().strip() or self._query(self.row)
        webbrowser.open("https://www.google.com/search?tbm=isch&q=" + urllib.parse.quote(q))
        tooltip(tr('Ở tab Google: chuột phải ảnh → Sao chép hình ảnh, rồi quay lại bấm “Dán ảnh”.'), period=6000, parent=self.dlg)

    def search(self, then=None):
        if self.row is None:
            return
        row, field = self.row, self.field
        q = self.q.text().strip()
        if not q:
            return
        self._q_edited()
        self.find_btn.setEnabled(False)

        def task():
            cands = core.search_images(q)

            def get(c):
                try:
                    return core.http_get(c["thumb"], timeout=10)
                except Exception:  # noqa: BLE001
                    return None
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=6) as ex:
                thumbs = list(ex.map(get, cands))
            return cands, thumbs

        def done(res, err):
            self.find_btn.setEnabled(True)
            if err or not res:
                tooltip(tr('Không tìm được ảnh: %s') % (err or tr('không có kết quả')), parent=self.dlg)
                return
            row["cands"][field], row["thumbs"][field] = res
            if not res[0]:
                tooltip(tr('Không thấy ảnh cho “%s”. Thử từ khóa tiếng Anh khác.') % q, parent=self.dlg)
            if self.row is row:
                self._refresh_cands()
        bg(task, done)

    def _pick_cand(self, item):
        i = item.data(Qt.ItemDataRole.UserRole)
        thumbs = self.row["thumbs"].get(self.field, []) if self.row else []
        if i is not None and i < len(thumbs) and thumbs[i]:
            self.set_image(thumbs[i])


class RowEditDialog(QDialog):
    """Sửa tất cả các ô chữ của một dòng trong một biểu mẫu (tiện khi ô dài)."""
    def __init__(self, parent, fields, values, warnings):
        super().__init__(parent)
        self.setWindowTitle(tr('Sửa dòng'))
        apply_theme(self, _night())
        self.resize(640, min(620, 120 + 62 * len(fields)))
        lay = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        self.eds = {}
        for n in fields:
            v = values.get(n, "")
            if len(v) > 60 or "\n" in v:
                ed = QPlainTextEdit(v)
                ed.setFixedHeight(66)
            else:
                ed = QLineEdit(v)
            warn = warnings.get(n)
            label = QLabel(("⚠ " if warn else "") + n)
            if warn:
                label.setToolTip(warn)
                ed.setToolTip(warn)
            self.eds[n] = ed
            form.addRow(label, ed)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        qconnect(bb.accepted, self.accept)
        qconnect(bb.rejected, self.reject)
        lay.addWidget(bb)

    def values(self):
        return {n: (e.text() if isinstance(e, QLineEdit) else e.toPlainText()).strip() for n, e in self.eds.items()}


class RegenDialog(QDialog):
    """Nhờ AI viết lại một số ô của một dòng theo yêu cầu ngắn (gọi trực tiếp hoặc sao chép/dán)."""
    def __init__(self, parent, row, text_fields, img_fields, warnings, can_call):
        super().__init__(parent)
        self.hub = parent
        self.row = row
        self.item = None
        self.setWindowTitle(tr('Tạo lại một dòng bằng AI'))
        apply_theme(self, _night())
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        first = parent.field_names[0]
        head = QLabel(tr('Dòng: %s') % row["f"].get(first, ""))
        head.setObjectName("sectionTitle")
        lay.addWidget(head)
        lay.addWidget(QLabel(tr('Yêu cầu ngắn cho lần viết lại này (không bắt buộc):')))
        self.instr = QLineEdit()
        self.instr.setPlaceholderText(tr('VD: câu ví dụ đơn giản hơn, dùng từ HSK 2'))
        lay.addWidget(self.instr)
        lay.addWidget(QLabel(tr('Viết lại các ô:')))
        self.checks = {}
        box = QFrame()
        box.setObjectName("inset")
        bl = QVBoxLayout(box)
        flagged = [n for n in text_fields if n in warnings and n != first]
        for n in [x for x in text_fields if x != first] + list(img_fields):
            cb = QCheckBox(n + ((" ⚠ " + warnings[n]) if n in warnings else "") + (tr(' (đổi từ khóa và tìm lại ảnh)') if n in img_fields else ""))
            cb.setChecked(n in flagged if flagged else n in text_fields)
            self.checks[n] = cb
            bl.addWidget(cb)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(box)
        sc.setMinimumHeight(120)
        lay.addWidget(sc, 1)
        self.status = QLabel("")
        self.status.setObjectName("caption")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.go_btn = QPushButton(tr('Tạo lại bằng AI'))
        self.go_btn.setObjectName("primary")
        self.go_btn.setEnabled(can_call)
        if not can_call:
            self.go_btn.setToolTip(tr('Chưa cấu hình dịch vụ AI ở tab “Tự động (API)”. Bạn vẫn có thể sao chép prompt rồi dán kết quả.'))
        qconnect(self.go_btn.clicked, self._call)
        lay.addWidget(self.go_btn)
        row2 = QHBoxLayout()
        self.copy_btn = QPushButton(tr('Sao chép prompt'))
        qconnect(self.copy_btn.clicked, self._copy)
        row2.addWidget(self.copy_btn)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText(tr('Hoặc dán kết quả JSON từ AI vào đây rồi bấm “Áp dụng kết quả đã dán”…'))
        self.paste.setFixedHeight(70)
        lay.addWidget(self.paste)
        self.apply_btn = QPushButton(tr('Áp dụng kết quả đã dán'))
        qconnect(self.apply_btn.clicked, self._apply_paste)
        lay.addWidget(self.apply_btn)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        qconnect(close.rejected, self.reject)
        lay.addWidget(close)
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)

    def redo(self):
        return [n for n, c in self.checks.items() if c.isChecked()]

    def _prompt(self):
        return self.hub._regen_prompt(self.row, self.redo(), self.instr.text())

    def _need(self):
        if not self.redo():
            self.status.setText(tr('Hãy tick ít nhất một ô cần viết lại.'))
            return False
        return True

    def _copy(self):
        if self._need():
            QApplication.clipboard().setText(self._prompt())
            self.status.setText(tr('Đã sao chép prompt. Gửi cho AI rồi dán kết quả vào ô bên dưới.'))

    def _finish(self, raw):
        try:
            items = core.parse_ai_json(raw)
        except Exception as e:  # noqa: BLE001
            self.status.setText(tr('Không đọc được kết quả: %s') % e)
            return
        if not items:
            self.status.setText(tr('Kết quả rỗng.'))
            return
        self.item = items[0]
        self.accept()

    def _apply_paste(self):
        if self._need():
            self._finish(self.paste.toPlainText())

    def _call(self):
        if not self._need():
            return
        cfg = self.hub._ui_cfg()
        prompt = self._prompt()
        self.go_btn.setEnabled(False)
        self.status.setText(tr('AI đang viết lại…'))

        def done(res, err):
            self.go_btn.setEnabled(True)
            if err:
                self.status.setText(tr('AI báo lỗi: %s') % err)
                return
            self._finish(res)
        bg(lambda: core.ai_text(cfg, prompt), done)


class NewTypeDialog(QDialog):
    """Tạo loại ghi chú mới (kiểu Basic của Anki) ngay trong add-on."""
    PRESETS = [
        ("Basic (Mặt trước / Mặt sau)", "Front, Back", False),
        ("Basic + ảnh", "Front, Back, Image", False),
        ("Basic có thẻ đảo (hai chiều)", "Front, Back", True),
        ("Từ vựng tiếng Trung (Hán)", "Hanzi, Pinyin, Meaning, Example, Example_Pinyin, Example_Meaning, Pic", False),
        ("Từ vựng tiếng Hàn", "Word, Romanization, Meaning, Example, Example_Meaning, Pic", False),
        ("Từ vựng tiếng Anh", "Word, IPA, Meaning, Example, Pic", False),
        ("Tự đặt các ô", "", False),
        ("Sao chép từ loại có sẵn", "", False),
    ]
    PRESET_KEYS = {3: "zh", 4: "ko", 5: "en"}

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Tạo loại ghi chú mới'))
        apply_theme(self, _night())
        self.resize(540, 420)
        lay = QVBoxLayout(self)
        self.name_ed = QLineEdit()
        self.name_ed.setPlaceholderText("My cards")
        self.preset = QComboBox()
        for label, _f, _r in self.PRESETS:
            self.preset.addItem(tr(label))
        self.fields_ed = QLineEdit("Front, Back")
        self.rev = QCheckBox(tr('Tạo thêm thẻ đảo (mặt sau → mặt trước)'))
        self.src_lbl = QLabel(tr('Sao chép từ:'))
        self.src_cb = QComboBox()
        try:
            for nt in sorted(aqt.mw.col.models.all_names_and_ids(), key=lambda x: x.name.lower()):
                self.src_cb.addItem(nt.name, nt.id)
        except Exception:  # noqa: BLE001
            pass
        for lbl, w in ((tr('Tên loại ghi chú:'), self.name_ed), (tr('Mẫu có sẵn:'), self.preset), (tr('Các ô (cách nhau bằng dấu phẩy):'), self.fields_ed)):
            lay.addWidget(QLabel(lbl))
            lay.addWidget(w)
        lay.addWidget(self.rev)
        lay.addWidget(self.src_lbl)
        lay.addWidget(self.src_cb)
        self._preset_changed(0)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        qconnect(bb.accepted, self.accept)
        qconnect(bb.rejected, self.reject)
        lay.addWidget(bb)
        qconnect(self.preset.currentIndexChanged, self._preset_changed)

    def _preset_changed(self, i):
        _l, f, r = self.PRESETS[i]
        clone = i == len(self.PRESETS) - 1
        if f:
            self.fields_ed.setText(f)
        self.rev.setChecked(r)
        for w in (self.fields_ed, self.rev):
            w.setEnabled(not clone)
        self.src_lbl.setVisible(clone)
        self.src_cb.setVisible(clone)

    def preset_key(self):
        return self.PRESET_KEYS.get(self.preset.currentIndex())

    def src_id(self):
        return self.src_cb.currentData() if self.preset.currentIndex() == len(self.PRESETS) - 1 else None

    def values(self):
        return self.name_ed.text().strip(), [x.strip() for x in self.fields_ed.text().split(",") if x.strip()], self.rev.isChecked()


# ============================================================ cửa sổ chính
class HubDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Card Filler · " + core.VERSION)
        ui = get_cfg().get("ui", {})
        if not isinstance(ui, dict):
            ui = {}
        try:
            g = QApplication.primaryScreen().availableGeometry()
            self.resize(min(int(ui.get("width", 1320)), int(g.width() * 0.94)),
                        min(int(ui.get("height", 900)), int(g.height() * 0.94)))
        except Exception:  # noqa: BLE001
            self.resize(1240, 800)
        apply_theme(self, _night())
        self.rows = []
        self.field_names = []
        self.text_fields, self.img_fields, self.audio_fields = [], [], []
        self._warn_rows = 0
        self._job_total = self._job_done = 0
        self._chunk_total = self._chunk_done_n = 0
        self._api_cancel = False
        self._audio_jobs = []
        self._last_add = None
        self.tcfg = None
        self._busy = 0
        self._generating = False
        self._adding = False
        self._loading_models = False
        self._undo_stack = []
        self._ready = False
        self._restoring = False
        try:
            profile_key = _mw().pm.profileFolder()
        except Exception:
            profile_key = 'test-profile'
        self.draft_store = DraftStore(str(profile_key))
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(1200)
        qconnect(self.draft_timer.timeout, self._save_draft)
        self._wide_sizes = [430, 750]
        self.setMinimumSize(720, 540)
        self._build()
        self.tabs.setCurrentIndex(1 if ui.get("mode") == 1 else 0)
        self._load_models()
        self._restore_draft()
        self._ready = True
        aqt.gui_hooks.theme_did_change.append(self._refresh_theme)
        aqt.gui_hooks.state_did_change.append(self._host_state_changed)
        self._refresh_theme()
        self.theme_timer = QTimer(self)
        self.theme_timer.setInterval(2000)
        qconnect(self.theme_timer.timeout, self._poll_theme)
        self.theme_timer.start()
        self._adapt_layout()
        self.words.setFocus()

    # ---------------------------------------------------------- dựng giao diện
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(14)

        header = QHBoxLayout()
        self.cat = StudyCat(self)
        self.cat.setToolTip(tr('Bạn đồng hành học bài · có thể tắt chuyển động trong Tùy chọn'))
        header.addWidget(self.cat)
        brand = QVBoxLayout()
        brand.setSpacing(3)
        title = QLabel("AI Card Filler")
        title.setObjectName("title")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addWidget(StudyGarden(self, small=True))
        title_row.addStretch(1)
        brand.addLayout(title_row)
        sub = QLabel(tr('Chuẩn bị nội dung. Tạo bằng AI. Kiểm tra trước khi thêm.'))
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        brand.addWidget(sub)
        header.addLayout(brand, 1)
        self.draft_info = QLabel('')
        self.draft_info.setObjectName('caption')
        header.addWidget(self.draft_info)
        self.appearance_btn = QPushButton(tr('Màu sắc'))
        self.appearance_btn.setToolTip(tr('Theo màu Anki hoặc tự chọn palette'))
        qconnect(self.appearance_btn.clicked, self._open_appearance)
        header.addWidget(self.appearance_btn)
        self.more_btn = QPushButton(tr('Tùy chọn'))
        menu = QMenu(self.more_btn)
        appearance_action = menu.addAction(tr('Màu sắc và trang trí…'))
        qconnect(appearance_action.triggered, self._open_appearance)
        menu.addSeparator()
        self.animation_act = menu.addAction(tr('Mascot và ảnh xem trước chuyển động'))
        self.animation_act.setCheckable(True)
        self.animation_act.setChecked(bool(get_cfg().get('animations', True)))
        qconnect(self.animation_act.toggled, self._save_animation)
        self.draft_act = menu.addAction(tr('Tự lưu và khôi phục bản nháp'))
        self.draft_act.setCheckable(True)
        self.draft_act.setChecked(bool(get_cfg().get('auto_save_draft', True)))
        qconnect(self.draft_act.toggled, self._toggle_drafts)
        menu.addSeparator()
        self.on_add = menu.addAction(tr('bấm Add của Anki sẽ mở cửa sổ này'))
        self.on_add.setCheckable(True)
        self.on_add.setChecked(bool(get_cfg().get("open_on_add", False)))
        qconnect(self.on_add.toggled, self._save_on_add)
        self.plain_add_act = menu.addAction(tr('Add thường'))
        qconnect(self.plain_add_act.triggered, lambda *_: self._open_plain_add())
        menu.addSeparator()
        exp_act = menu.addAction(tr('Xuất cấu hình loại thẻ này…'))
        qconnect(exp_act.triggered, lambda *_: self._export_cfg())
        imp_act = menu.addAction(tr('Nhập cấu hình từ file…'))
        qconnect(imp_act.triggered, lambda *_: self._import_cfg())
        menu.addSeparator()
        self.upd_act = menu.addAction(tr('🔄 Kiểm tra cập nhật'))
        qconnect(self.upd_act.triggered, lambda *_: self._check_updates())
        self.more_btn.setMenu(menu)
        header.addWidget(self.more_btn)
        outer.addLayout(header)

        destination = QFrame()
        destination.setObjectName("card")
        dest = QGridLayout(destination)
        dest.setContentsMargins(14, 10, 14, 12)
        dest.setHorizontalSpacing(12)
        dest.setVerticalSpacing(5)
        model_label = QLabel(tr('Loại ghi chú'))
        model_label.setObjectName("caption")
        deck_label = QLabel(tr('Bộ thẻ đích'))
        deck_label.setObjectName("caption")
        self.model_cb = QComboBox()
        self.model_cb.setMinimumWidth(100)
        self.model_cb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.model_cb.setAccessibleName(tr('Loại ghi chú'))
        model_label.setBuddy(self.model_cb)
        self.mgr_btn = QPushButton(tr('Quản lý'))
        self.mgr_btn.setToolTip(tr('Tạo loại ghi chú mới hoặc mở trình quản lý loại ghi chú của Anki'))
        tm = QMenu(self.mgr_btn)
        act_new = tm.addAction(tr('Tạo loại ghi chú mới…'))
        qconnect(act_new.triggered, lambda *_: self._new_type())
        act_mgr = tm.addAction(tr('Quản lý loại trong Anki…'))
        qconnect(act_mgr.triggered, lambda *_: self._manage_types())
        self.mgr_btn.setMenu(tm)
        self.deck_cb = QComboBox()
        self.deck_cb.setMinimumWidth(100)
        self.deck_cb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.deck_cb.setAccessibleName(tr('Bộ thẻ đích'))
        deck_label.setBuddy(self.deck_cb)
        self.newdeck_btn = QPushButton(tr('Tạo mới'))
        qconnect(self.newdeck_btn.clicked, self._new_deck)
        dest.addWidget(model_label, 0, 0, 1, 2)
        dest.addWidget(deck_label, 0, 2, 1, 2)
        dest.addWidget(self.model_cb, 1, 0)
        dest.addWidget(self.mgr_btn, 1, 1)
        dest.addWidget(self.deck_cb, 1, 2)
        dest.addWidget(self.newdeck_btn, 1, 3)
        dest.setColumnStretch(0, 1)
        dest.setColumnStretch(2, 1)
        outer.addWidget(destination)

        self.workspace = QStackedWidget()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(12)
        self.compact_tabs = QTabWidget()
        self.workspace.addWidget(self.splitter)
        self.workspace.addWidget(self.compact_tabs)
        outer.addWidget(self.workspace, 1)

        self.compose_page = QFrame()
        self.compose_page.setObjectName("card")
        compose_layout = QVBoxLayout(self.compose_page)
        compose_layout.setContentsMargins(0, 0, 0, 0)
        compose_layout.setSpacing(0)
        self.compose_scroll = QScrollArea()
        self.compose_scroll.setWidgetResizable(True)
        self.compose_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.compose_scroll.setMinimumWidth(310)
        self.compose_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        compose_layout.addWidget(self.compose_scroll, 1)
        compose = QFrame()
        root = QVBoxLayout(compose)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)
        self.compose_scroll.setWidget(compose)
        heading = QLabel(tr('1. Soạn nội dung'))
        heading.setObjectName("sectionTitle")
        compose_head = QHBoxLayout()
        compose_head.addWidget(heading, 1)
        self.input_info = QLabel(tr('Chưa có nội dung'))
        self.input_info.setObjectName("caption")
        compose_head.addWidget(self.input_info)
        root.addLayout(compose_head)
        helper = QLabel(tr('Mỗi dòng một mục, hoặc dán một đoạn văn.'))
        helper.setObjectName("muted")
        helper.setWordWrap(True)
        root.addWidget(helper)
        self.words = QPlainTextEdit()
        self.words.setAccessibleName(tr('Nội dung cần học'))
        self.words.setPlaceholderText(tr('Ví dụ:\n银行 | ngân hàng\n库存 | hàng tồn kho'))
        self.words.setMinimumHeight(96)
        self.words.setMaximumHeight(104)
        root.addWidget(self.words)
        photo_row = QHBoxLayout()
        self.photo_btn = QPushButton(tr('Lấy từ ảnh…'))
        self.photo_btn.setObjectName("quiet")
        self.photo_btn.setToolTip(tr('Chụp hoặc chọn ảnh một trang sách: AI đọc ảnh và điền danh sách từ vào ô này (cần cấu hình AI, nên kiểm tra lại kết quả).'))
        pmenu = QMenu(self.photo_btn)
        a_file = pmenu.addAction(tr('Chọn ảnh từ máy…'))
        qconnect(a_file.triggered, lambda *_: self._photo_file())
        a_clip = pmenu.addAction(tr('Dán ảnh từ clipboard'))
        qconnect(a_clip.triggered, lambda *_: self._photo_clip())
        self.photo_btn.setMenu(pmenu)
        photo_row.addWidget(self.photo_btn)
        photo_row.addStretch(1)
        root.addLayout(photo_row)
        extra_label = QLabel(tr('Yêu cầu thêm (không bắt buộc)'))
        extra_label.setObjectName("caption")
        root.addWidget(extra_label)
        self.extra = QLineEdit(get_cfg().get("extra", ""))
        self.extra.setPlaceholderText(tr('VD: HSK 2, giải thích bằng tiếng Việt'))
        self.extra.setAccessibleName(tr('Yêu cầu thêm (không bắt buộc)'))
        root.addWidget(self.extra)

        self.advanced_btn = QPushButton(tr('Tùy chỉnh prompt và nhãn'))
        self.advanced_btn.setObjectName("quiet")
        self.advanced_btn.setCheckable(True)
        root.addWidget(self.advanced_btn)
        self.advanced = QFrame()
        self.advanced.setObjectName("inset")
        adv = QVBoxLayout(self.advanced)
        adv.setContentsMargins(10, 10, 10, 10)
        adv.addWidget(QLabel(tr('Thẻ mẫu cho AI bắt chước:')))
        self.sample_cb = QComboBox()
        self.sample_cb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.sample_cb.setAccessibleName(tr('Thẻ mẫu cho AI bắt chước:'))
        self.sample_cb.setToolTip(tr('Lấy một thẻ có sẵn của loại này làm ví dụ trong prompt (ô âm thanh/SVG tự bị bỏ qua).'))
        adv.addWidget(self.sample_cb)
        adv.addWidget(QLabel(tr('Nhãn:')))
        self.tag_ed = QLineEdit(get_cfg().get("tag", "ai-card-filler"))
        self.tag_ed.setPlaceholderText(tr('Cách nhau bằng dấu cách'))
        self.tag_ed.setAccessibleName(tr('Nhãn:'))
        adv.addWidget(self.tag_ed)
        self.cfg_btn = QPushButton(tr('Cấu hình ô và prompt'))
        qconnect(self.cfg_btn.clicked, self._edit_type_cfg)
        adv.addWidget(self.cfg_btn)
        self.advanced.hide()
        qconnect(self.advanced_btn.toggled, self.advanced.setVisible)
        root.addWidget(self.advanced)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        man = QWidget()
        ml = QVBoxLayout(man)
        ml.setContentsMargins(0, 6, 0, 0)
        ml.setSpacing(9)
        info = QLabel(tr('Sao chép prompt sang ChatGPT / Gemini, rồi dán câu trả lời về đây.'))
        info.setWordWrap(True)
        info.setObjectName("muted")
        ml.addWidget(info)
        self.copy_btn = QPushButton(tr('Sao chép prompt'))
        self.copy_btn.setToolTip(tr('Sao chép prompt (Ctrl+Shift+C)'))
        qconnect(self.copy_btn.clicked, self._copy_prompt)
        pr = QHBoxLayout()
        self.prompt_info = QLabel("")
        self.prompt_info.setObjectName("caption")
        self.prompt_info.setWordWrap(True)
        self.prompt_toggle = QPushButton(tr('Xem prompt'))
        self.prompt_toggle.setObjectName("quiet")
        self.prompt_toggle.setCheckable(True)
        pr.addWidget(self.copy_btn, 1)
        pr.addWidget(self.prompt_toggle)
        ml.addLayout(pr)
        ml.addWidget(self.prompt_info)
        self.prompt = QPlainTextEdit()
        self.prompt.setReadOnly(True)
        self.prompt.setAccessibleName(tr('Prompt gửi cho AI'))
        self.prompt.setFixedHeight(116)
        self.prompt.hide()
        qconnect(self.prompt_toggle.toggled, self.prompt.setVisible)
        ml.addWidget(self.prompt)
        ml.addWidget(QLabel(tr('Câu trả lời của AI')))
        self.result = QPlainTextEdit()
        self.result.setAccessibleName(tr('Câu trả lời của AI'))
        self.result.setPlaceholderText(tr('Dán toàn bộ khối JSON từ AI vào đây…'))
        self.result.setMinimumHeight(80)
        self.result.setMaximumHeight(100)
        ml.addWidget(self.result)
        self.auto_img_m = QCheckBox(tr('Tự tìm ảnh minh họa'))
        self.auto_img_m.setChecked(True)
        ml.addWidget(self.auto_img_m)
        self.make_btn = QPushButton(tr('Tạo bản xem trước'))
        self.make_btn.setObjectName("primary")
        qconnect(self.make_btn.clicked, self._from_paste)
        ml.addWidget(self.make_btn)
        self.tabs.addTab(man, tr('Sao chép & dán'))

        auto = QWidget()
        al = QVBoxLayout(auto)
        al.setContentsMargins(0, 6, 0, 0)
        al.setSpacing(10)
        api_info = QLabel(tr('Chọn dịch vụ AI và dán khóa để tạo nội dung ngay trong Anki.'))
        api_info.setWordWrap(True)
        api_info.setObjectName("muted")
        al.addWidget(api_info)
        self.provider_cb = QComboBox()
        self.provider_cb.setAccessibleName(tr('Dịch vụ AI'))
        for k, label in core.PROVIDER_LABELS.items():
            self.provider_cb.addItem(label, k)
        self.provider_cb.setCurrentIndex(max(0, self.provider_cb.findData(get_cfg().get('provider', 'gemini'))))
        al.addWidget(self.provider_cb)
        self.provider_stack = QStackedWidget()
        # ---- Gemini
        gem = QWidget()
        gl = QVBoxLayout(gem)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(10)
        api_link = QLabel('<a href="https://aistudio.google.com/apikey">%s</a>' % tr('Lấy khóa tại Google AI Studio'))
        api_link.setOpenExternalLinks(True)
        gl.addWidget(api_link)
        model_row = QHBoxLayout()
        self.api_model = QComboBox()
        self.api_model.setEditable(True)
        self.api_model.addItem(get_cfg().get('gemini_model', 'gemini-2.5-flash-lite'))
        self.api_model.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.api_model.setAccessibleName(tr('Model Gemini'))
        self.api_model.setToolTip(tr('Nhập tên model hoặc tải danh sách từ Google.'))
        self.models_btn = QPushButton(tr('Tải model'))
        qconnect(self.models_btn.clicked, self._fetch_models)
        model_row.addWidget(self.api_model, 1)
        model_row.addWidget(self.models_btn)
        gl.addWidget(QLabel(tr('Model Gemini')))
        gl.addLayout(model_row)
        self.key_ed = QLineEdit(get_cfg().get("gemini_key", ""))
        self.key_ed.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_ed.setPlaceholderText(tr('Dán khóa Gemini API'))
        self.key_ed.setAccessibleName(tr('Khóa Gemini API'))
        gl.addWidget(self.key_ed)
        kr = QHBoxLayout()
        self.key_toggle = QPushButton(tr('Hiện khóa'))
        self.key_toggle.setCheckable(True)
        qconnect(self.key_toggle.toggled, self._toggle_key)
        self.key_save = QPushButton(tr('Lưu khóa'))
        qconnect(self.key_save.clicked, self._save_key)
        kr.addWidget(self.key_toggle)
        kr.addWidget(self.key_save)
        gl.addLayout(kr)
        self.provider_stack.addWidget(gem)
        # ---- OpenAI-compatible
        oai = QWidget()
        ol = QVBoxLayout(oai)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(8)
        oc = get_cfg().get('openai') or {}
        self.oai_preset = QComboBox()
        self.oai_preset.addItem(tr('Chọn nhanh…'), None)
        for label, url, model in core.OPENAI_PRESETS:
            self.oai_preset.addItem(label, (url, model))
        qconnect(self.oai_preset.activated, self._oai_preset_picked)
        ol.addWidget(self.oai_preset)
        self.oai_url = QLineEdit(oc.get('base_url', ''))
        self.oai_url.setPlaceholderText(tr('Địa chỉ API (ví dụ https://api.openai.com/v1)'))
        self.oai_url.setAccessibleName(tr('Địa chỉ API'))
        self.oai_model = QLineEdit(oc.get('model', ''))
        self.oai_model.setPlaceholderText(tr('Tên model'))
        self.oai_model.setAccessibleName(tr('Tên model'))
        self.oai_key = QLineEdit(oc.get('key', ''))
        self.oai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.oai_key.setPlaceholderText(tr('Khóa API (bỏ trống nếu chạy trên máy bạn như Ollama)'))
        self.oai_key.setAccessibleName(tr('Khóa API'))
        for w in (self.oai_url, self.oai_model, self.oai_key):
            ol.addWidget(w)
        orow = QHBoxLayout()
        self.oai_save = QPushButton(tr('Lưu khóa'))
        qconnect(self.oai_save.clicked, self._save_key)
        orow.addWidget(self.oai_save)
        orow.addStretch(1)
        ol.addLayout(orow)
        self.provider_stack.addWidget(oai)
        # ---- Claude
        cla = QWidget()
        cl = QVBoxLayout(cla)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        ac = get_cfg().get('anthropic') or {}
        self.cla_model = QLineEdit(ac.get('model', ''))
        self.cla_model.setPlaceholderText(tr('Tên model'))
        self.cla_model.setAccessibleName(tr('Tên model'))
        self.cla_key = QLineEdit(ac.get('key', ''))
        self.cla_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.cla_key.setPlaceholderText(tr('Khóa API của Anthropic'))
        self.cla_key.setAccessibleName(tr('Khóa API'))
        cl.addWidget(self.cla_model)
        cl.addWidget(self.cla_key)
        crow = QHBoxLayout()
        self.cla_save = QPushButton(tr('Lưu khóa'))
        qconnect(self.cla_save.clicked, self._save_key)
        crow.addWidget(self.cla_save)
        crow.addStretch(1)
        cl.addLayout(crow)
        self.provider_stack.addWidget(cla)
        al.addWidget(self.provider_stack)
        self.provider_stack.setCurrentIndex(max(0, self.provider_cb.currentIndex()))
        qconnect(self.provider_cb.currentIndexChanged, self._provider_changed)
        self.fallback_cb = QCheckBox(tr('Hết hạn mức (429) thì tự đổi dịch vụ'))
        self.fallback_cb.setToolTip(tr('Khi dịch vụ đang chọn hết hạn mức (429), tự đổi sang dịch vụ khác đã cấu hình'))
        self.fallback_cb.setChecked(bool(get_cfg().get('auto_fallback', True)))
        al.addWidget(self.fallback_cb)
        privacy = QLabel(tr('Khóa lưu trong cấu hình add-on trên máy và chỉ dùng để gọi đúng dịch vụ bạn chọn.'))
        privacy.setWordWrap(True)
        privacy.setObjectName("caption")
        al.addWidget(privacy)
        self.auto_img_a = QCheckBox(tr('Tự tìm ảnh minh họa'))
        self.auto_img_a.setChecked(True)
        al.addWidget(self.auto_img_a)
        self.auto_btn = QPushButton(tr('Tạo bản xem trước bằng AI'))
        self.auto_btn.setObjectName("primary")
        qconnect(self.auto_btn.clicked, self._from_api)
        al.addWidget(self.auto_btn)
        al.addStretch(1)
        self.tabs.addTab(auto, tr('Tự động (API)'))
        root.addWidget(self.tabs)
        root.addStretch(1)
        actions = QWidget()
        action_layout = QVBoxLayout(actions)
        action_layout.setContentsMargins(16, 8, 16, 14)
        action_layout.addWidget(self.make_btn)
        action_layout.addWidget(self.auto_btn)
        compose_layout.addWidget(actions)
        qconnect(self.tabs.currentChanged, self._generation_mode_changed)
        self._generation_mode_changed(self.tabs.currentIndex())

        self.preview = QFrame()
        self.preview.setObjectName("card")
        self.preview.setMinimumWidth(300)
        pl = QVBoxLayout(self.preview)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(9)
        preview_head = QHBoxLayout()
        preview_title = QLabel(tr('2. Xem trước'))
        preview_title.setObjectName("sectionTitle")
        self.count_badge = QLabel(tr('0 thẻ'))
        self.count_badge.setObjectName("badge")
        preview_head.addWidget(preview_title, 1)
        preview_head.addWidget(self.count_badge)
        pl.addLayout(preview_head)
        preview_hint = QLabel(tr('Nhấp đúp để sửa chữ. Chọn một dòng để xem ảnh.'))
        preview_hint.setWordWrap(True)
        preview_hint.setObjectName("muted")
        pl.addWidget(preview_hint)
        tools = QHBoxLayout()
        self.select_btn = QPushButton(tr('Chọn tất cả'))
        self.select_btn.setObjectName("quiet")
        qconnect(self.select_btn.clicked, self._toggle_selection)
        self.remove_btn = QPushButton(tr('Bỏ dòng'))
        self.remove_btn.setObjectName("danger")
        self.remove_btn.setToolTip(tr('Bỏ các dòng đang chọn khỏi bản xem trước (phím Delete). Giữ Ctrl hoặc Shift để chọn nhiều dòng.'))
        qconnect(self.remove_btn.clicked, self._remove_current)
        self.undo_btn = QPushButton(tr('Hoàn tác'))
        self.undo_btn.setObjectName('quiet')
        self.undo_btn.setToolTip(tr('Khôi phục dòng vừa bỏ (Ctrl+Z khi không sửa văn bản)'))
        qconnect(self.undo_btn.clicked, self._undo_remove)
        self.edit_btn = QPushButton(tr('Sửa dòng'))
        self.edit_btn.setObjectName('quiet')
        self.edit_btn.setToolTip(tr('Mở biểu mẫu để sửa tất cả các ô của dòng đang chọn'))
        qconnect(self.edit_btn.clicked, self._edit_row)
        self.regen_btn = QPushButton(tr('Tạo lại'))
        self.regen_btn.setObjectName('quiet')
        self.regen_btn.setToolTip(tr('Nhờ AI viết lại một số ô của dòng đang chọn theo yêu cầu ngắn của bạn'))
        qconnect(self.regen_btn.clicked, self._regen_row)
        self.audio_btn = QPushButton(tr('Tạo âm thanh'))
        self.audio_btn.setObjectName('quiet')
        self.audio_btn.setToolTip(tr('Tạo âm thanh cho các dòng đã chọn bằng giọng đọc của Gemini (thử nghiệm, cần khóa Gemini)'))
        qconnect(self.audio_btn.clicked, self._make_audio)
        self.audio_btn.hide()
        self.image_toggle = QPushButton(tr('Ảnh minh họa'))
        self.image_toggle.setObjectName("quiet")
        self.image_toggle.setCheckable(True)
        self.image_toggle.setChecked(True)
        tools.addWidget(self.select_btn)
        tools.addWidget(self.remove_btn)
        tools.addWidget(self.undo_btn)
        tools.addWidget(self.edit_btn)
        tools.addWidget(self.regen_btn)
        tools.addWidget(self.audio_btn)
        tools.addStretch(1)
        tools.addWidget(self.image_toggle)
        pl.addLayout(tools)
        self.review_split = QSplitter(Qt.Orientation.Vertical)
        self.review_split.setChildrenCollapsible(False)
        self.review_split.setHandleWidth(14)
        self.review_split.setToolTip(tr('Kéo thanh này lên/xuống để đổi chiều cao khung ảnh. Nhấp đúp để về mặc định.'))
        self.preview_stack = QStackedWidget()
        self.preview_stack.setMinimumHeight(120)
        self.preview_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)   # trang trống không được ép chiều cao tối thiểu
        self.table = QTableWidget(0, 0)
        self.table.setAccessibleName(tr('Bản xem trước thẻ'))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        qconnect(self.table.customContextMenuRequested, self._table_menu)
        qconnect(self.table.cellDoubleClicked, self._cell_double_clicked)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(120)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(38)
        qconnect(self.table.itemChanged, self._cell_changed)
        qconnect(self.table.itemSelectionChanged, self._row_selected)
        self.preview_stack.addWidget(self.table)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark = StudyGarden(empty)
        el.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        el.addSpacing(10)
        empty_title = QLabel(tr('Thẻ sẽ xuất hiện ở đây'))
        empty_title.setObjectName("sectionTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setWordWrap(True)
        el.addWidget(empty_title)
        empty_hint = QLabel(tr('Nhập nội dung và tạo bản xem trước.\nBạn có thể sửa chữ và chọn ảnh trước khi thêm.'))
        empty_hint.setObjectName("muted")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setWordWrap(True)
        el.addWidget(empty_hint)
        self.preview_stack.addWidget(empty)
        self.review_split.addWidget(self.preview_stack)
        self.image_tabs = QTabWidget()
        self.image_tabs.setMinimumHeight(268)
        self.image_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        self.image_tabs.tabBar().setExpanding(False)
        self.review_split.addWidget(self.image_tabs)
        self.review_split.setStretchFactor(0, 1)
        self.review_split.setStretchFactor(1, 1)
        self.review_split.setCollapsible(0, False)
        self.review_split.setCollapsible(1, False)
        self.review_split.handle(1).installEventFilter(self)
        self.del_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self.table)
        self.del_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        qconnect(self.del_shortcut.activated, self._remove_current)
        qconnect(self.image_toggle.toggled, self._show_images)
        pl.addWidget(self.review_split, 1)
        self.slots = {}
        self.splitter.addWidget(self.compose_page)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes(self._wide_sizes)

        footer = QFrame()
        footer.setObjectName("card")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(6)
        foot = QHBoxLayout()
        summary = QVBoxLayout()
        summary.setSpacing(2)
        self.skip_dup = QCheckBox(tr('Bỏ qua từ đã có trong Anki'))
        self.skip_dup.setChecked(True)
        qconnect(self.skip_dup.toggled, self._update_footer)
        self.status = QLabel(tr('Sẵn sàng. Bắt đầu bằng nội dung bạn muốn học.'))
        self.status.setObjectName("caption")
        self.status.setWordWrap(True)
        summary.addWidget(self.skip_dup)
        summary.addWidget(self.status)
        foot.addLayout(summary, 1)
        self.stop_btn = QPushButton(tr('Dừng'))
        qconnect(self.stop_btn.clicked, self._stop_images)
        self.stop_btn.hide()
        foot.addWidget(self.stop_btn)
        self.undo_add_btn = QPushButton(tr('Hoàn tác lần thêm vừa rồi'))
        self.undo_add_btn.setObjectName("quiet")
        self.undo_add_btn.setToolTip(tr('Xóa các thẻ vừa thêm (dùng chức năng hoàn tác của Anki) và đưa các dòng về lại bản xem trước'))
        qconnect(self.undo_add_btn.clicked, self._undo_last_add)
        self.undo_add_btn.hide()
        foot.addWidget(self.undo_add_btn)
        self.add_btn = QPushButton(tr('Thêm vào Anki'))
        self.add_btn.setObjectName("primary")
        self.add_btn.setToolTip(tr('Thêm các thẻ đã chọn (Ctrl+Shift+Enter)'))
        self.add_btn.setEnabled(False)
        qconnect(self.add_btn.clicked, self._add_to_anki)
        foot.addWidget(self.add_btn)
        fl.addLayout(foot)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        fl.addWidget(self.progress)
        outer.addWidget(footer)

        qconnect(self.words.textChanged, self._refresh_prompt)
        qconnect(self.extra.textChanged, self._refresh_prompt)
        qconnect(self.model_cb.currentIndexChanged, self._model_changed)
        qconnect(self.sample_cb.currentIndexChanged, self._refresh_prompt)
        qconnect(self.result.textChanged, self._sync_controls)
        qconnect(self.key_ed.textChanged, self._sync_controls)
        for w in (self.oai_url, self.oai_model, self.oai_key, self.cla_model, self.cla_key):
            qconnect(w.textChanged, self._sync_controls)
        qconnect(self.api_model.currentTextChanged, self._sync_controls)
        qconnect(self.deck_cb.currentIndexChanged, self._schedule_draft)
        qconnect(self.tag_ed.textChanged, self._schedule_draft)
        qconnect(self.result.textChanged, self._schedule_draft)
        self.undo_shortcut = QShortcut(QKeySequence('Ctrl+Z'), self)
        qconnect(self.undo_shortcut.activated, self._undo_if_not_editing)
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        qconnect(self.copy_shortcut.activated, lambda: self._copy_prompt() if self.copy_btn.isEnabled() else None)
        self.add_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Return"), self)
        qconnect(self.add_shortcut.activated, lambda: self._add_to_anki() if self.add_btn.isEnabled() else None)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        for tabs in self.findChildren(QTabWidget):
            tabs.tabBar().setDrawBase(False)

    def _apply_current_theme(self):
        if getattr(self, '_theme_updating', False):
            return
        self._theme_updating = True
        try:
            apply_theme(self, _night())
            for dialog in self.findChildren(QDialog):
                apply_theme(dialog, _night())
            for label in self.findChildren(AnimatedLabel):
                label.set_animation_enabled(_motion_allowed())
            self._theme_signature = tuple(sorted(colors(_night()).items()))
        finally:
            self._theme_updating = False

    def _refresh_theme(self):
        self._apply_current_theme()
        capture_web_canvas(_night(), self._apply_current_theme)

    def _poll_theme(self):
        if not self.isVisible() or appearance().get('mode') != 'anki':
            return
        if tuple(sorted(colors(_night()).items())) != getattr(self, '_theme_signature', None):
            self._apply_current_theme()
        capture_web_canvas(_night(), self._apply_current_theme)

    def _open_appearance(self):
        from .appearance_ui import AppearanceDialog
        dialog = AppearanceDialog(self, _night)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = get_cfg()
            config['appearance'] = dict(dialog.settings)
            save_cfg(config)
        self._refresh_theme()

    def _host_state_changed(self, *_):
        if self.isVisible():
            self._refresh_theme()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ApplicationPaletteChange and hasattr(self, 'cat'):
            self._refresh_theme()

    def _save_animation(self, enabled):
        config = get_cfg()
        config['animations'] = bool(enabled)
        save_cfg(config)
        self._refresh_theme()

    def _toggle_drafts(self, enabled):
        config = get_cfg()
        config['auto_save_draft'] = bool(enabled)
        save_cfg(config)
        if enabled:
            self._schedule_draft()
        else:
            self.draft_timer.stop()
            self.draft_info.setText(tr('Tự lưu nháp đã tắt'))

    def _schedule_draft(self, *_):
        if self._ready and not self._restoring and get_cfg().get('auto_save_draft', True):
            self.draft_info.setText(tr('Đang chỉnh sửa…'))
            self.draft_timer.start()

    def _save_draft(self):
        self.draft_timer.stop()
        if not self._ready or self._restoring or not get_cfg().get('auto_save_draft', True):
            return
        payload = dict(model_id=self.model_cb.currentData(), fields=self.field_names,
                       deck_id=self.deck_cb.currentData(), words=self.words.toPlainText(),
                       result=self.result.toPlainText(), extra=self.extra.text(), tags=self.tag_ed.text(),
                       sample_id=self.sample_cb.currentData(), mode=self.tabs.currentIndex(),
                       skip_dup=self.skip_dup.isChecked(), rows=self.rows)
        try:
            if self.rows or payload['words'].strip() or payload['result'].strip():
                self.draft_store.save(payload)
                self.draft_info.setText(tr('Nháp đã lưu'))
            else:
                self.draft_store.clear()
                self.draft_info.clear()
        except (OSError, ValueError, TypeError) as error:
            self.draft_info.setText(tr('Chưa lưu được nháp'))
            self.draft_info.setToolTip(str(error))

    def _restore_draft(self):
        if not get_cfg().get('auto_save_draft', True):
            return
        self._restoring = True
        try:
            saved = self.draft_store.load()
            if not saved:
                return
            index = self.model_cb.findData(saved.get('model_id'))
            if index >= 0:
                self.model_cb.setCurrentIndex(index)
            self.words.setPlainText(saved.get('words', ''))
            self.result.setPlainText(saved.get('result', ''))
            self.extra.setText(saved.get('extra', ''))
            self.tag_ed.setText(saved.get('tags', ''))
            self._select_deck(saved.get('deck_id'))
            self.tabs.setCurrentIndex(1 if saved.get('mode') == 1 else 0)
            self.skip_dup.setChecked(bool(saved.get('skip_dup', True)))
            sample = self.sample_cb.findData(saved.get('sample_id'))
            if sample >= 0:
                self.sample_cb.setCurrentIndex(sample)
            if index >= 0 and saved.get('fields') == self.field_names:
                existing = core.existing_firsts(_mw().col, self.model['id'])
                self.rows = saved['rows']
                for row in self.rows:
                    row['dup'] = row['f'].get(self.field_names[0], '') in existing
                    row.setdefault('audio', {})
                self._rebuild_table()
                if self.rows:
                    self.table.selectRow(0)
            elif saved.get('rows'):
                self.result.setPlainText(json.dumps([r['f'] for r in saved['rows']], ensure_ascii=False))
            self.draft_info.setText(tr('Đã khôi phục nháp'))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.draft_info.setText(tr('Không đọc được nháp cũ'))
        finally:
            self._restoring = False

    def _undo_if_not_editing(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)):
            focus.undo()
        else:
            self._undo_remove()

    def _undo_remove(self):
        if self._generating or self._adding or self._loading_models or not self._undo_stack:
            return
        group = self._undo_stack.pop()
        for index, row in sorted(group, key=lambda x: x[0]):
            self.rows.insert(min(index, len(self.rows)), row)
        self._rebuild_table()
        self.table.selectRow(min(min(i for i, _ in group), len(self.rows) - 1))

    def _fetch_models(self):
        key = self.key_ed.text().strip()
        if not key or self._busy or self._generating or self._adding or self._loading_models:
            return
        current = self.api_model.currentText().strip()
        self._loading_models = True
        self.status.setText(tr('Đang tải danh sách model từ Google…'))
        self._sync_controls()
        def done(models, error):
            self._loading_models = False
            if not error and models:
                self.api_model.blockSignals(True)
                self.api_model.clear()
                self.api_model.addItems(models)
                self.api_model.setCurrentText(current)
                self.api_model.blockSignals(False)
                tooltip(tr('Đã tải %d model. Bạn có thể chọn hoặc nhập tên model.') % len(models), parent=self)
            elif error:
                showWarning(tr('Không tải được model: %s') % error)
            self._update_footer()
        bg(lambda: core.gemini_models(key), done)

    def _toggle_key(self, show):
        self.key_ed.setEchoMode(QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password)
        self.key_toggle.setText(tr('Ẩn khóa') if show else tr('Hiện khóa'))

    def _generation_mode_changed(self, index):
        self.make_btn.setVisible(index == 0)
        self.auto_btn.setVisible(index == 1)

    def _show_images(self, on):
        want = bool(on and self.img_fields and self.rows)
        was = self.image_tabs.isVisible() or getattr(self, "_img_shown", False)
        self.image_tabs.setVisible(want)
        self._img_shown = want
        if want and not was:
            QTimer.singleShot(0, self._reset_review_split)

    def _adapt_layout(self):
        compact = self.width() < 1040
        if compact and self.workspace.currentWidget() is not self.compact_tabs:
            sizes = self.splitter.sizes()
            if len(sizes) == 2 and min(sizes) >= 310:
                self._wide_sizes = sizes
            self.compact_tabs.addTab(self.compose_page, tr('Soạn nội dung'))
            self.compact_tabs.addTab(self.preview, tr('Xem trước'))
            self.workspace.setCurrentWidget(self.compact_tabs)
        elif not compact and self.workspace.currentWidget() is not self.splitter:
            while self.compact_tabs.count():
                self.compact_tabs.removeTab(0)
            self.splitter.addWidget(self.compose_page)
            self.splitter.addWidget(self.preview)
            self.workspace.setCurrentWidget(self.splitter)
            self.compose_page.show()
            self.preview.show()
            self.splitter.setSizes(getattr(self, "_wide_sizes", [410, 750]))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "workspace"):
            self._adapt_layout()

    def closeEvent(self, event):
        self._save_draft()
        self.draft_timer.stop()
        self.theme_timer.stop()
        try:
            aqt.gui_hooks.theme_did_change.remove(self._refresh_theme)
            aqt.gui_hooks.state_did_change.remove(self._host_state_changed)
        except ValueError:
            pass
        c = get_cfg()
        c["ui"] = {"width": self.width(), "height": self.height(),
                   "mode": self.tabs.currentIndex(), "model_id": self.model_cb.currentData()}
        c["extra"] = self.extra.text()
        c["tag"] = self.tag_ed.text()
        c['gemini_model'] = self.api_model.currentText().strip().removeprefix('models/')
        save_cfg(c)
        super().closeEvent(event)

    def _sync_controls(self):
        locked = bool(self._busy or self._generating or self._adding or self._loading_models)
        has_model = bool(self.field_names)
        has_prompt = has_model and bool(self.prompt.toPlainText().strip())
        self.copy_btn.setEnabled(has_prompt)
        self.make_btn.setEnabled(has_model and bool(self.result.toPlainText().strip()) and not locked)
        has_key = bool(self.key_ed.text().strip())
        ucfg = self._ui_cfg()
        self.auto_btn.setEnabled(has_prompt and core.provider_ready(ucfg, ucfg["provider"]) and not locked)
        self.photo_btn.setEnabled(not locked)
        self.audio_btn.setEnabled(bool(self.audio_fields) and bool(self.rows) and not locked and not self._generating)
        self.api_model.setEnabled(not locked)
        self.models_btn.setEnabled(has_key and not locked)
        edit_locked = bool(self._generating or self._adding or self._loading_models)
        sel_rows = self._selected_rows()
        self.undo_btn.setEnabled(bool(self._undo_stack) and not edit_locked)
        self.edit_btn.setEnabled(len(sel_rows) == 1 and not edit_locked)
        self.regen_btn.setEnabled(len(sel_rows) == 1 and not edit_locked)
        for widget in (self.model_cb, self.mgr_btn, self.cfg_btn, self.deck_cb, self.newdeck_btn):
            widget.setEnabled(not locked)
        self.cfg_btn.setEnabled(has_model and not locked)
        for cb in (self.auto_img_m, self.auto_img_a):
            cb.setEnabled(bool(self.img_fields) and not locked)
            cb.setToolTip('' if self.img_fields else tr('Loại ghi chú này không có ô ảnh.'))
        self.remove_btn.setEnabled(bool(sel_rows) and not edit_locked)
        self.select_btn.setEnabled(bool(self.rows) and not self._adding)
        self.table.setEnabled(not self._adding)
        self.add_btn.setEnabled(bool(self._picks()) and not locked)
        self.stop_btn.setVisible(bool(self._busy or self._generating))
        self.stop_btn.setEnabled(bool(getattr(self, "_jobs", []) or getattr(self, "_audio_jobs", []) or self._generating))
        self.progress.setVisible(locked)
        if self._generating and getattr(self, "_chunk_total", 0) > 1:
            self.progress.setRange(0, self._chunk_total)
            self.progress.setValue(self._chunk_done_n)
        elif self._generating or self._adding or self._loading_models:
            self.progress.setRange(0, 0)
        elif self._busy:
            self.progress.setRange(0, max(1, self._job_total))
            self.progress.setValue(self._job_done)

    def _picks(self):
        if not self.field_names:
            return []
        first = self.field_names[0]
        return [r for r in self.rows if r.get("sel") and r["f"].get(first, '').strip()
                and not (self.skip_dup.isChecked() and r.get("dup"))]

    def _toggle_selection(self):
        eligible = [r for r in self.rows if not (self.skip_dup.isChecked() and r.get("dup"))]
        select = not (eligible and all(r.get("sel") for r in eligible))
        for r in self.rows:
            r["sel"] = select and r in eligible
        keep = self.table.currentRow()
        self._rebuild_table()
        if keep >= 0:
            self.table.selectRow(keep)

    def _selected_rows(self):
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _remove_current(self):
        """Bỏ tất cả các dòng đang chọn (dùng được cả khi đang tìm ảnh)."""
        if self._generating or self._adding:
            return
        idx = [i for i in self._selected_rows() if i < len(self.rows)]
        if not idx:
            return
        group = [(i, self.rows[i]) for i in idx]
        gone = {id(r) for _, r in group}
        self.rows = [r for r in self.rows if id(r) not in gone]
        self._undo_stack.append(group)
        self._undo_stack = self._undo_stack[-50:]
        self._rebuild_table()
        if self.rows:
            self.table.selectRow(min(idx[0], len(self.rows) - 1))
        self._row_selected()
        self.status.setText(tr('Đã bỏ %d dòng. Bấm Hoàn tác nếu bỏ nhầm.') % len(idx))

    def _table_menu(self, pos):
        ix = self.table.indexAt(pos)
        if ix.isValid() and not self.table.selectionModel().isRowSelected(ix.row()):
            self.table.selectRow(ix.row())
        sel = self._selected_rows()
        menu = QMenu(self)
        a_rm = menu.addAction(tr('Bỏ dòng') + (" (%d)" % len(sel) if len(sel) > 1 else ""))
        a_rm.setEnabled(bool(sel) and not (self._generating or self._adding))
        qconnect(a_rm.triggered, lambda *_: self._remove_current())
        a_edit = menu.addAction(tr('Sửa dòng…'))
        a_edit.setEnabled(len(sel) == 1)
        qconnect(a_edit.triggered, lambda *_: self._edit_row())
        a_re = menu.addAction(tr('Tạo lại bằng AI…'))
        a_re.setEnabled(len(sel) == 1)
        qconnect(a_re.triggered, lambda *_: self._regen_row())
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _cell_double_clicked(self, row, col):
        k = col - 2 - len(self.text_fields)
        if 0 <= k < len(self.img_fields):
            self.image_tabs.setCurrentIndex(k)

    def _edit_row(self):
        sel = self._selected_rows()
        if len(sel) != 1 or sel[0] >= len(self.rows) or self._generating or self._adding:
            return
        row = self.rows[sel[0]]
        warn = core.validate_row(row, self.field_names, self.tcfg, self.rows)
        dlg = RowEditDialog(self, self.text_fields, row["f"], warn)
        if dlg.exec():
            for n, v in dlg.values().items():
                row["f"][n] = v
            row["dup"] = row["f"].get(self.field_names[0], "") in core.existing_firsts(_mw().col, self.model["id"])
            self._rebuild_table()
            self.table.selectRow(sel[0])

    def _regen_prompt(self, row, redo, instruction):
        return core.build_regen_prompt(self.field_names, self.tcfg, row["f"], redo, instruction, extra=self.extra.text(), example=self._example())

    def _regen_row(self):
        sel = self._selected_rows()
        if len(sel) != 1 or sel[0] >= len(self.rows) or self._generating or self._adding:
            return
        row = self.rows[sel[0]]
        warn = core.validate_row(row, self.field_names, self.tcfg, self.rows)
        cfg = self._ui_cfg()
        dlg = RegenDialog(self, row, self.text_fields, self.img_fields, warn, core.provider_ready(cfg, cfg["provider"]))
        if not dlg.exec() or not dlg.item:
            return
        changed = core.apply_regen(row, dlg.item, dlg.redo(), self.field_names, self.tcfg)
        self._rebuild_table()
        self.table.selectRow(sel[0])
        if changed:
            self._auto_images([row])
        self.status.setText(tr('Đã viết lại dòng “%s”.') % row["f"].get(self.field_names[0], ""))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonDblClick and hasattr(self, "review_split") and obj is self.review_split.handle(1):
            self._reset_review_split()
            return True
        return super().eventFilter(obj, event)

    def _reset_review_split(self):
        if not hasattr(self, "review_split") or not self.image_tabs.isVisible():
            return
        total = self.review_split.height()
        if total <= 0:
            return
        img = min(max(self.image_tabs.minimumHeight(), int(total * 0.42)), max(self.image_tabs.minimumHeight(), total - 150))
        self.review_split.setSizes([max(120, total - img - 14), img])

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reset_review_split)

    def _stop_images(self):
        self._jobs = []
        self._audio_jobs = []
        self._api_cancel = True
        self._retried = True
        self.status.setText(tr('Đang dừng, chờ lượt đang chạy xong…'))
        self._sync_controls()


    # ---------------------------------------------------------- loại ghi chú
    def _load_models(self):
        col = _mw().col
        self.model_cb.blockSignals(True)
        self.model_cb.clear()
        for nid in sorted(col.models.all_names_and_ids(), key=lambda x: x.name.lower()):
            self.model_cb.addItem(nid.name, nid.id)
        # Keep the user's last type, with the original Hub preference as a fallback.
        ui = get_cfg().get("ui", {})
        remembered = ui.get("model_id") if isinstance(ui, dict) else None
        last = self.model_cb.findData(remembered)
        if last >= 0:
            self.model_cb.setCurrentIndex(last)
        else:
            for i in range(self.model_cb.count()):
                if "hub v5" in self.model_cb.itemText(i).lower():
                    self.model_cb.setCurrentIndex(i)
                    break
        self.model_cb.blockSignals(False)
        self.deck_cb.clear()
        for d in sorted(col.decks.all_names_and_ids(include_filtered=False), key=lambda x: x.name.lower()):
            self.deck_cb.addItem(d.name, d.id)
        self._select_deck(get_cfg().get("last_deck") or col.decks.get_current_id())
        self._model_changed()

    def _select_deck(self, did):
        i = self.deck_cb.findData(did)
        if i >= 0:
            self.deck_cb.setCurrentIndex(i)

    def _manage_types(self):
        try:
            from aqt.models import Models
            mid = self.model_cb.currentData()
            dlg = Models(_mw(), self, selected_notetype_id=mid)
            self._models_dlg = dlg
            qconnect(dlg.finished, lambda *_: self._reload_models_keep(mid))
        except Exception as e:  # noqa: BLE001
            showWarning(str(e))

    def _reload_models_keep(self, mid):
        self._load_models()
        i = self.model_cb.findData(mid)
        if i >= 0:
            self.model_cb.setCurrentIndex(i)

    def _new_type(self):
        dlg = NewTypeDialog(self)
        if not dlg.exec():
            return
        name, fields, rev = dlg.values()
        src = dlg.src_id()
        if not name or (not fields and not src):
            showWarning(tr('Tên và các ô không được để trống.'))
            return
        try:
            if src:
                mid = core.clone_note_type(_mw().col, src, name)
            else:
                mid = core.create_note_type(_mw().col, name, fields, rev)
        except KeyError:
            showWarning(tr('Đã có loại ghi chú tên “%s”.') % name)
            return
        except Exception as e:  # noqa: BLE001
            showWarning(str(e))
            return
        key = None if src else dlg.preset_key()
        if key:
            res = core.apply_preset(fields, key)
            if res:
                c = get_cfg()
                c["types"][name] = {"intro": res[0], "roles": {}, "hints": res[1]}
                save_cfg(c)
        self._load_models()
        i = self.model_cb.findData(mid)
        if i >= 0:
            self.model_cb.setCurrentIndex(i)
        tooltip(tr('Đã tạo loại ghi chú “%s”.') % name, parent=self)

    def _new_deck(self):
        name, ok = QInputDialog.getText(self, tr('Bộ thẻ mới'), tr('Tên bộ thẻ (dùng :: để tạo bộ con):'))
        name = (name or "").strip()
        if not ok or not name:
            return
        col = _mw().col
        did = col.decks.id(name)
        self.deck_cb.addItem(name, did)
        self._select_deck(did)
        tooltip(tr('Đã tạo bộ thẻ “%s”.') % name, parent=self)

    def _export_cfg(self):
        if not self.field_names:
            return
        default = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in self.model["name"]) + ".acf.json"
        path, _ = QFileDialog.getSaveFileName(self, tr('Xuất cấu hình loại thẻ này'), default, "JSON (*.json)")
        if not path:
            return
        data = {"acf_type_config": 1, "name": self.model["name"], "fields": self.field_names,
                "intro": self.tcfg["intro"], "roles": self.tcfg["roles"], "hints": self.tcfg["hints"]}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            showWarning(str(e))
            return
        tooltip(tr('Đã xuất cấu hình (không kèm khóa API).'), parent=self)

    def _import_cfg(self):
        if not self.field_names:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Nhập cấu hình từ file'), "", "JSON (*.json)")
        if not path:
            return
        try:
            import os
            if os.path.getsize(path) > 1024 * 1024:
                raise ValueError(tr('File quá lớn.'))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            new = core.sanitize_type_config(data, self.field_names)
        except (OSError, ValueError) as e:
            showWarning(tr('Không nhập được cấu hình: %s') % e)
            return
        if self.rows:
            ans = QMessageBox.question(self, tr('Chỉnh cấu hình?'), tr('Lưu cấu hình mới sẽ xóa bản xem trước hiện tại. Tiếp tục?'),
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if ans != QMessageBox.StandardButton.Yes:
                return
        cur = self.tcfg
        c = get_cfg()
        c["types"][self.model["name"]] = {"intro": new["intro"] or cur["intro"],
                                          "roles": {**cur["roles"], **new["roles"]},
                                          "hints": {**cur["hints"], **new["hints"]}}
        save_cfg(c)
        self._model_changed()
        tooltip(tr('Đã nhập cấu hình cho loại “%s”.') % self.model["name"], parent=self)

    def _save_on_add(self, on):
        c = get_cfg()
        c["open_on_add"] = bool(on)
        save_cfg(c)

    def _check_updates(self):
        try:
            from aqt.addons import check_and_prompt_for_updates
            m = _mw()
            check_and_prompt_for_updates(self, m.addonManager, m.on_updates_installed, requested_by_user=True)
        except Exception as e:  # noqa: BLE001
            showWarning(tr('Không kiểm tra được cập nhật: %s') % e)

    def _open_plain_add(self):
        _mw()._acf_bypass = True
        aqt.dialogs.open("AddCards", _mw())

    def _load_samples(self):
        """Điền danh sách thẻ mẫu: các ghi chú mới nhất cùng loại."""
        col = _mw().col
        self.sample_cb.blockSignals(True)
        self.sample_cb.clear()
        self.sample_cb.addItem(tr('(không dùng thẻ mẫu)'), None)
        try:
            nids = list(col.find_notes('mid:%d' % self.model["id"]))
        except Exception:
            nids = []
        for nid in reversed(nids[-15:]):
            try:
                note = col.get_note(nid)
                label = core.strip_html(note.fields[0])[:40] or str(nid)
            except Exception:
                continue
            self.sample_cb.addItem(tr('Thẻ: ') + label, nid)
        if self.sample_cb.count() > 1:
            self.sample_cb.setCurrentIndex(1)
        self.sample_cb.blockSignals(False)

    def _model_changed(self):
        col = _mw().col
        mid = self.model_cb.currentData()
        if mid is None:
            self._rebuild_table()
            self._sync_controls()
            return
        old_model = getattr(self, "model", None)
        if self.rows and old_model and old_model["id"] != mid:
            answer = QMessageBox.question(
                self, tr('Đổi loại ghi chú?'),
                tr('Bản xem trước hiện tại sẽ bị xóa khi đổi loại ghi chú. Tiếp tục?'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                self.model_cb.blockSignals(True)
                self.model_cb.setCurrentIndex(self.model_cb.findData(old_model["id"]))
                self.model_cb.blockSignals(False)
                return
        model = col.models.get(mid)
        self.model = model
        self.field_names = [f["name"] for f in model["flds"]]
        self.tcfg = core.type_config(get_cfg(), model["name"], self.field_names)
        self.text_fields = [n for n in self.field_names if self.tcfg["roles"].get(n) == core.ROLE_AI]
        self.img_fields = [n for n in self.field_names if self.tcfg["roles"].get(n) == core.ROLE_IMG]
        self.img_fields.sort(key=lambda n: 0 if n.lower() in ("pic", "image", "img") else 1)
        self.audio_fields = [n for n in self.field_names if self.tcfg["roles"].get(n) == core.ROLE_AUDIO]
        self.audio_btn.setVisible(bool(self.audio_fields))
        self.rows = []
        self._undo_stack = []
        self._load_samples()
        self._rebuild_slots()
        self._rebuild_table()
        self._refresh_prompt()

    def _edit_type_cfg(self):
        if self.rows:
            answer = QMessageBox.question(
                self, tr('Chỉnh cấu hình?'),
                tr('Lưu cấu hình mới sẽ xóa bản xem trước hiện tại. Tiếp tục?'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return
        dlg = TypeConfigDialog(self, self.model["name"], self.field_names, self.tcfg)
        if dlg.exec():
            c = get_cfg()
            c["types"][self.model["name"]] = dlg.result_config()
            save_cfg(c)
            self._model_changed()

    def _rebuild_slots(self):
        while self.image_tabs.count():
            widget = self.image_tabs.widget(0)
            self.image_tabs.removeTab(0)
            widget.deleteLater()
        self.slots = {}
        for f in self.img_fields:
            slot = ImageSlot(self, f)
            self.slots[f] = slot
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(slot)
            self.image_tabs.addTab(scroll, f)
        self.image_toggle.setVisible(bool(self.img_fields))
        self._show_images(self.image_toggle.isChecked())

    # ---------------------------------------------------------- prompt
    def _example(self):
        nid = self.sample_cb.currentData() if hasattr(self, "sample_cb") else None
        if nid:
            try:
                note = _mw().col.get_note(nid)
                ex = core.build_example(self.field_names, self.tcfg, dict(note.items()))
                if ex:
                    return ex
            except Exception:
                pass
        return core.HUB_EXAMPLE if core.is_hub_type(self.field_names) else None

    def _refresh_prompt(self):
        if not self.field_names:
            self._sync_controls()
            return
        text = self.words.toPlainText()
        p = core.build_prompt(self.field_names, self.tcfg, text, extra=self.extra.text(), example=self._example())
        self.prompt.setPlainText(p)
        if not text.strip():
            self.input_info.setText(tr('Chưa có nội dung'))
        elif core.looks_like_list(text):
            self.input_info.setText(tr('%d mục đầu vào') % len(core.parse_lines(text)))
        else:
            self.input_info.setText(tr('Đoạn văn · AI sẽ chọn mục đáng học'))
        self._sync_controls()
        self._schedule_draft()
        if not p:
            self.prompt_info.setText(tr('Nhập nội dung để tạo prompt.'))
        elif core.looks_like_list(text):
            self.prompt_info.setText(tr('%d mục · sẵn sàng sao chép') % len(core.parse_lines(text)))
        else:
            self.prompt_info.setText(tr('Prompt từ đoạn văn (AI tự chọn mục đáng học).'))

    def _copy_prompt(self):
        QApplication.clipboard().setText(self.prompt.toPlainText())
        self.tabs.setCurrentIndex(0)
        self.compact_tabs.setCurrentWidget(self.compose_page)
        self.result.setFocus()
        self.compose_scroll.ensureWidgetVisible(self.result)
        tooltip(tr('Đã sao chép. Gửi prompt cho AI rồi dán câu trả lời vào đây.'), parent=self)

    # ---------------------------------------------------------- tạo thẻ
    def _ui_cfg(self):
        """Cấu hình đang hiển thị trên giao diện (chưa chắc đã lưu)."""
        c = dict(get_cfg())
        c["provider"] = self.provider_cb.currentData() or "gemini"
        c["gemini_key"] = self.key_ed.text().strip()
        c["gemini_model"] = self.api_model.currentText().strip().removeprefix("models/")
        c["openai"] = {"base_url": self.oai_url.text().strip(), "key": self.oai_key.text().strip(), "model": self.oai_model.text().strip()}
        c["anthropic"] = {"key": self.cla_key.text().strip(), "model": self.cla_model.text().strip()}
        c["auto_fallback"] = self.fallback_cb.isChecked()
        return c

    def _provider_changed(self, i):
        self.provider_stack.setCurrentIndex(max(0, i))
        self._sync_controls()

    def _oai_preset_picked(self, i):
        data = self.oai_preset.itemData(i)
        if data:
            self.oai_url.setText(data[0])
            self.oai_model.setText(data[1])

    def _save_key(self):
        u = self._ui_cfg()
        c = get_cfg()
        for k in ("provider", "gemini_key", "gemini_model", "openai", "anthropic", "auto_fallback"):
            c[k] = u[k]
        save_cfg(c)
        tooltip(tr('Đã lưu cấu hình dịch vụ AI.'), parent=self)

    def _from_paste(self):
        if self._busy or self._generating or self._adding:
            return
        raw = self.result.toPlainText().strip()
        if not raw:
            tooltip(tr('Hãy dán kết quả AI vào ô ③ trước.'), parent=self)
            return
        try:
            items = core.parse_ai_json(raw)
        except Exception as e:  # noqa: BLE001
            showWarning(tr('Không đọc được kết quả: %s\nHãy copy cả khối mã JSON mà AI trả về.') % e)
            return
        if self._load_items(items, self.auto_img_m.isChecked()):
            self.result.clear()

    def _chunk_msg(self):
        if getattr(self, "_chunk_total", 0) > 1:
            return tr('AI đang điền ô… lượt %d/%d') % (min(self._chunk_done_n + 1, self._chunk_total), self._chunk_total)
        return tr('AI đang điền ô…')

    def _chunk_progress(self, n):
        self._chunk_done_n = n
        if self._generating:
            self.status.setText(self._chunk_msg())
            self._sync_controls()

    def _from_api(self):
        if self._busy or self._generating or self._adding:
            return
        cfg = self._ui_cfg()
        name = cfg["provider"]
        if not core.provider_ready(cfg, name):
            showInfo(tr('Hãy điền đủ khóa và tên model của dịch vụ AI rồi bấm “Lưu khóa” trước.'))
            return
        text = self.words.toPlainText()
        if not text.strip():
            tooltip(tr('Hãy dán nội dung ở ô ① trước.'), parent=self)
            return
        import re
        if name == "gemini" and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', cfg["gemini_model"]):
            showWarning(tr('Tên model không hợp lệ. Hãy chọn từ danh sách hoặc nhập ID model.'))
            return
        first = self.field_names[0]
        todo = core.without_known(text, {r["f"].get(first, "") for r in self.rows})
        if not todo.strip():
            tooltip(tr('Tất cả các mục này đã có trong bản xem trước.'), parent=self)
            return
        chunks = core.chunk_items(todo, int(cfg.get("chunk_size", 20) or 20))
        example = self._example()
        prompts = [core.build_prompt(self.field_names, self.tcfg, c, extra=self.extra.text(), example=example) for c in chunks]
        self._api_cancel = False
        self._chunk_total, self._chunk_done_n = len(prompts), 0
        self._set_busy(True, self._chunk_msg())
        tm = _mw().taskman
        on_main = getattr(tm, "run_on_main", None) or (lambda f: f())

        def work():
            results = []
            for i, pr in enumerate(prompts):
                if self._api_cancel:
                    return results, None, i
                items, last = None, None
                for _attempt in range(2):
                    try:
                        items = core.parse_ai_json(core.ai_text(cfg, pr))
                        break
                    except (core.AIError, core.QuotaError) as e:
                        last = e
                        break
                    except Exception as e:  # noqa: BLE001  (JSON chưa đúng: thử lại một lần)
                        last = e
                if items is None:
                    return results, last, i
                results.extend(items)
                on_main(lambda n=i + 1: self._chunk_progress(n))
            return results, None, len(prompts)

        def done(res, err):
            self._set_busy(False)
            if err:
                showWarning(tr('AI báo lỗi: %s') % err)
                return
            results, last, finished = res
            if results:
                self._load_items(results, self.auto_img_a.isChecked())
            if last:
                tail = ""
                if results:
                    tail = tr('\n\nĐã tạo %d mục (%d/%d lượt). Bấm “Tạo bản xem trước bằng AI” lần nữa để chạy tiếp phần còn thiếu; các mục đã có sẽ được bỏ qua.') % (len(results), finished, len(prompts))
                showWarning(tr('AI báo lỗi: %s') % last + tail)
            elif self._api_cancel:
                self.status.setText(tr('Đã dừng sau %d/%d lượt.') % (finished, len(prompts)))
        bg(work, done)

    # ---------------------------------------------------------- lấy từ ảnh
    def _photo_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Chọn ảnh trang sách'), "", tr('Ảnh (*.png *.jpg *.jpeg *.webp *.bmp)'))
        if path:
            try:
                with open(path, "rb") as f:
                    self._photo_extract(f.read())
            except OSError as e:
                showWarning(str(e))

    def _photo_clip(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            tooltip(tr('Clipboard chưa có ảnh. Hãy copy ảnh trang sách trước.'), parent=self)
            return
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        self._photo_extract(bytes(ba))

    def _photo_extract(self, data):
        cfg = self._ui_cfg()
        if not core.provider_ready(cfg, cfg["provider"]):
            showInfo(tr('Cần cấu hình dịch vụ AI ở tab “Tự động (API)” để đọc ảnh.'))
            return
        try:
            jpg = shrink_jpeg(data, 1600)
        except Exception as e:  # noqa: BLE001
            showWarning(str(e))
            return
        self._chunk_total = 0
        self._set_busy(True, tr('AI đang đọc ảnh…'))

        def done(res, err):
            self._set_busy(False)
            if err:
                showWarning(tr('AI báo lỗi: %s') % err)
                return
            lines = core.clean_vocab_lines(res)
            if not lines:
                tooltip(tr('AI không đọc được từ nào trong ảnh. Thử ảnh rõ và thẳng hơn.'), parent=self)
                return
            cur = self.words.toPlainText().rstrip()
            self.words.setPlainText((cur + "\n" if cur else "") + lines)
            tooltip(tr('Đã điền %d mục từ ảnh. Hãy kiểm tra lại chữ trước khi tạo thẻ.') % len(lines.splitlines()), period=6000, parent=self)
        bg(lambda: core.ai_text(cfg, core.PHOTO_PROMPT, images=[("image/jpeg", jpg)], json_mode=False), done)

    def _set_busy(self, on, msg=""):
        self._generating = bool(on)
        if on:
            self.status.setText(msg)
        else:
            self._update_footer()
        self._sync_controls()


    def _load_items(self, items, auto_img):
        new = core.norm_rows(items, self.field_names, self.tcfg)
        if not new:
            showWarning(tr('Không có mục nào dùng được trong kết quả (thiếu ô “%s”).') % self.field_names[0])
            return False
        existing = core.existing_firsts(_mw().col, self.model["id"])
        have = {r["f"][self.field_names[0]] for r in self.rows}
        fresh = []
        for r in new:
            first = r["f"][self.field_names[0]]
            if first in have:
                continue
            have.add(first)
            r.update({"img": {}, "cands": {}, "thumbs": {}, "audio": {}, "sel": True, "dup": first in existing})
            if r["dup"] and self.skip_dup.isChecked():
                r["sel"] = False
            self.rows.append(r)
            fresh.append(r)
        if not fresh:
            tooltip(tr('Các mục này đã có trong bản xem trước.'), parent=self)
            return False
        self._rebuild_table()
        if self.rows:
            self.table.selectRow(len(self.rows) - len(fresh))
        if auto_img and self.img_fields:
            self._auto_images(fresh)
        self._update_footer()
        self.compact_tabs.setCurrentWidget(self.preview)
        return True

    # ---------------------------------------------------------- bảng
    def _rebuild_table(self):
        self.table.blockSignals(True)
        cols = [tr('Chọn'), tr('Trạng thái')] + self.text_fields + [tr('Ảnh: ') + f for f in self.img_fields] + [tr('Âm: ') + f for f in self.audio_fields]
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Checked if r.get("sel") else Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, chk)
            st = QTableWidgetItem(tr('Đã có trong Anki') if r.get("dup") else tr('Mới'))
            st.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 1, st)
            for j, n in enumerate(self.text_fields):
                self.table.setItem(i, 2 + j, QTableWidgetItem(r["f"].get(n, "")))
            for k, f in enumerate(self.img_fields):
                self._set_img_cell(i, 2 + len(self.text_fields) + k, r, f)
            for k, f in enumerate(self.audio_fields):
                self._set_audio_cell(i, 2 + len(self.text_fields) + len(self.img_fields) + k, r, f)
        self.table.resizeColumnsToContents()
        for j in range(2, 2 + len(self.text_fields)):
            self.table.setColumnWidth(j, min(max(self.table.columnWidth(j), 90), 260))
        self.table.setIconSize(QSize(40, 30))
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setColumnWidth(0, 54)
        self.table.setColumnWidth(1, 148)
        self.table.blockSignals(False)
        self._paint_warnings()
        self._update_footer()
        self._row_selected()

    def _paint_warnings(self):
        """Tô màu các ô nghi sai (trống, quá dài, trùng, câu ví dụ thiếu từ) và ghi lý do vào chú giải."""
        if not self.field_names or self.table.columnCount() < 2 + len(self.text_fields):
            return
        warn = QColor(colors(_night())["warning"])
        warn.setAlpha(85)
        self.table.blockSignals(True)
        count = 0
        for i, r in enumerate(self.rows):
            v = core.validate_row(r, self.field_names, self.tcfg, self.rows)
            count += 1 if v else 0
            st = self.table.item(i, 1)
            if st is not None:
                base = tr('Đã có trong Anki') if r.get("dup") else tr('Mới')
                st.setText(("⚠ %d · " % len(v) if v else "") + base)
                st.setToolTip("\n".join("%s: %s" % (n, why) for n, why in v.items()))
            for j, n in enumerate(self.text_fields):
                it = self.table.item(i, 2 + j)
                if it is None:
                    continue
                it.setBackground(QBrush(warn) if n in v else QBrush())
                it.setToolTip(v.get(n, ""))
        self._warn_rows = count
        self.table.blockSignals(False)

    def _set_audio_cell(self, i, c, r, f):
        it = QTableWidgetItem("♪" if r.get("audio", {}).get(f) else "—")
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it.setToolTip(tr('Âm thanh được đọc từ ô: %s') % self._audio_source(f))
        self.table.setItem(i, c, it)

    def update_audio_cell(self, row, field):
        if row not in self.rows or field not in self.audio_fields:
            return
        self.table.blockSignals(True)
        self._set_audio_cell(self.rows.index(row), 2 + len(self.text_fields) + len(self.img_fields) + self.audio_fields.index(field), row, field)
        self.table.blockSignals(False)

    def _audio_source(self, f):
        hint = (self.tcfg["hints"].get(f) or "").strip().lower()
        for n in self.field_names:
            if n.lower() == hint:
                return n
        return self.field_names[0]

    def _audio_text(self, r, f):
        return core.strip_html(r["f"].get(self._audio_source(f), ""))

    def _make_audio(self):
        if self._busy or self._generating or self._adding or not self.audio_fields:
            return
        cfg = self._ui_cfg()
        key = (cfg.get("gemini_key") or "").strip()
        if not key:
            showInfo(tr('Âm thanh dùng giọng đọc của Gemini: hãy dán khóa Gemini ở tab “Tự động (API)” rồi bấm “Lưu khóa”.'))
            return
        rows = [r for r in self.rows if r.get("sel")] or list(self.rows)
        jobs = [(r, f) for r in rows for f in self.audio_fields if not r["audio"].get(f) and self._audio_text(r, f)]
        if not jobs:
            tooltip(tr('Không có ô âm thanh nào cần tạo.'), parent=self)
            return
        self._busy += 1
        self._job_total, self._job_done = len(jobs), 0
        self._audio_jobs = jobs
        self._audio_err = None
        self.status.setText(tr('Đang tạo âm thanh… 0/%d') % len(jobs))
        self._sync_controls()
        self._next_audio(key, cfg)

    def _next_audio(self, key, cfg):
        if not self._audio_jobs:
            self._busy = max(0, self._busy - 1)
            self._refresh_after_jobs()
            if getattr(self, "_audio_err", None):
                showWarning(tr('Không tạo tiếp được âm thanh: %s\nCác dòng đã xong vẫn giữ nguyên; bấm “Tạo âm thanh” lần nữa để làm tiếp phần còn lại.') % self._audio_err)
            return
        r, f = self._audio_jobs.pop(0)
        text = self._audio_text(r, f)

        def done(res, err):
            self._job_done += 1
            if err:
                self._audio_jobs = []
                self._audio_err = err
            elif res and r in self.rows:
                r["audio"][f] = res
                self.update_audio_cell(r, f)
            self.status.setText(tr('Đang tạo âm thanh… %d/%d') % (self._job_done, self._job_total))
            self._sync_controls()
            self._next_audio(key, cfg)
        bg(lambda: core.gemini_tts(key, text, model=cfg.get("tts_model") or "gemini-2.5-flash-preview-tts", voice=cfg.get("tts_voice") or "Kore"), done)

    def _set_img_cell(self, i, c, r, f):
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        pm = pixmap_of(r["img"].get(f), 40, 30)
        if pm:
            it.setIcon(QIcon(pm))
            it.setText("")
        else:
            it.setText("—")
        self.table.setItem(i, c, it)

    def update_img_cell(self, row, field):
        if row is None or row not in self.rows or field not in self.img_fields:
            return
        i = self.rows.index(row)
        c = 2 + len(self.text_fields) + self.img_fields.index(field)
        self.table.blockSignals(True)
        self._set_img_cell(i, c, row, field)
        self.table.blockSignals(False)
        self._update_footer()

    def _cell_changed(self, item):
        i, c = item.row(), item.column()
        if i >= len(self.rows):
            return
        if c == 0:
            self.rows[i]["sel"] = item.checkState() == Qt.CheckState.Checked
        elif 2 <= c < 2 + len(self.text_fields):
            self.rows[i]["f"][self.text_fields[c - 2]] = item.text().strip()
        if c == 2 and self.text_fields:
            r = self.rows[i]
            first = r["f"].get(self.field_names[0], "")
            r["dup"] = first in core.existing_firsts(_mw().col, self.model["id"])
        if 2 <= c < 2 + len(self.text_fields) or c == 2:
            self._paint_warnings()
        self._update_footer()

    def _row_selected(self):
        sel = self._selected_rows()
        row = self.rows[sel[0]] if sel and sel[0] < len(self.rows) else None
        for s in self.slots.values():
            s.show_row(row)
        self._sync_controls()

    def _update_footer(self):
        picks = self._picks()
        n = len(picks)
        self.add_btn.setText(tr('Thêm %d thẻ vào Anki') % n if n else tr('Thêm vào Anki'))
        self.count_badge.setText(tr('%d thẻ') % len(self.rows))
        self.preview_stack.setCurrentIndex(0 if self.rows else 1)
        self._show_images(self.image_toggle.isChecked())
        eligible = [r for r in self.rows if not (self.skip_dup.isChecked() and r.get("dup"))]
        all_on = bool(eligible) and all(r.get("sel") for r in eligible)
        self.select_btn.setText(tr('Bỏ chọn tất cả') if all_on else tr('Chọn tất cả'))
        if not (self._busy or self._generating or self._adding or self._loading_models):
            if self.rows:
                msg = tr('%d / %d thẻ được chọn') % (n, len(self.rows))
                miss = sum(1 for r in picks if self.img_fields and not r["img"].get(self.img_fields[0]))
                if miss:
                    msg += tr(' · %d chưa có ảnh chính') % miss
                if getattr(self, "_warn_rows", 0):
                    msg += tr(' · ⚠ %d dòng nghi sai (rê chuột vào ô tô màu để xem lý do)') % self._warn_rows
                self.status.setText(msg)
            else:
                self.status.setText(tr('Sẵn sàng. Bắt đầu bằng nội dung bạn muốn học.'))
        self._sync_controls()

        self._schedule_draft()

    # ---------------------------------------------------------- ảnh tự động
    def _auto_images(self, rows):
        jobs = [(r, f) for r in rows for f in self.img_fields if not r["img"].get(f)]
        if not jobs:
            return
        self._busy += 1
        self._job_total, self._job_done = len(jobs), 0
        self._retried = False
        self._batch_open = True
        self._jobs = list(jobs)
        self.status.setText(tr('Đang tìm ảnh… 0/%d') % len(jobs))
        self._active = 0
        self._sync_controls()
        for _ in range(5):
            self._next_job()

    def _refresh_after_jobs(self):
        if self.table.state() == QAbstractItemView.State.EditingState:
            QTimer.singleShot(700, self._refresh_after_jobs)   # đang gõ trong ô: đợi xong rồi mới làm mới bảng
            return
        sel = self._selected_rows()
        self._rebuild_table()
        if sel and sel[0] < len(self.rows):
            self.table.selectRow(sel[0])
        self._update_footer()

    def _queries_for(self, r, f):
        q, alt = (r["q"].get(f) or ["", ""])[:2]
        first = r["f"].get(self.field_names[0], "")
        main = [q, alt, (r["q"].get(self.img_fields[0]) or [""])[0] if f != self.img_fields[0] else ""]
        out = []
        extra = []
        if getattr(self, "_retried", False):
            for n in self.field_names[1:]:
                v = (r["f"].get(n) or "").strip()
                if v and v.isascii() and len(v.split()) <= 4 and self.tcfg["roles"].get(n) == core.ROLE_AI:
                    extra.append(v.split(";")[0].split(",")[0].strip())
        for x in main + extra + ([first] if not any(main) else []):
            x = (x or "").strip()
            if x and x not in out:
                out.append(x)
        return out

    def _next_job(self):
        if not self._jobs:
            if self._active == 0 and not getattr(self, "_retried", False):
                # lượt thử lại: ô còn trống, dùng từ khóa tiếng Anh lấy từ các ô chữ của thẻ
                self._retried = True
                again = [(r, f) for r in self.rows for f in self.img_fields if not r["img"].get(f)]
                if again:
                    self._jobs = again
                    self._job_total += len(again)
                    for _ in range(min(5, len(again))):
                        self._next_job()
                    return
            if self._active == 0 and getattr(self, "_batch_open", False):
                self._batch_open = False
                self._busy = max(0, self._busy - 1)
                self._refresh_after_jobs()
                missing = sum(1 for r in self.rows for f in self.img_fields if not r["img"].get(f))
                if missing:
                    tooltip(tr('%d ô ảnh chưa có. Chọn hàng đó để tìm tay hoặc dán ảnh.') % missing, period=6000, parent=self)
            return
        r, f = self._jobs.pop(0)
        self._active += 1
        qs = self._queries_for(r, f)

        def done(res, err):
            self._active -= 1
            self._job_done += 1
            if res and res[0] and r in self.rows:
                data, used, cands = res
                try:
                    r["img"][f] = shrink_jpeg(data, int(get_cfg().get("image_max_side", 512)))
                except Exception:  # noqa: BLE001
                    pass
                r["cands"][f] = cands
                r["thumbs"][f] = [None] * len(cands)
                if r["q"].get(f) is None or not r["q"][f][0]:
                    r["q"][f] = [used, ""]
                self.update_img_cell(r, f)
                sel = self._selected_rows()
                if sel and sel[0] < len(self.rows) and self.rows[sel[0]] is r and f in self.slots:
                    self.slots[f].show_row(r)
            self.status.setText(tr('Đang tìm ảnh… %d/%d') % (self._job_done, self._job_total))
            self._sync_controls()
            self._next_job()
        bg(lambda: core.find_image_bytes(qs), done)

    # ---------------------------------------------------------- thêm vào Anki
    def _add_to_anki(self):
        if self._busy or self._generating or self._adding:
            return
        picks = self._picks()
        if not picks:
            return
        if self.skip_dup.isChecked():
            picks = [r for r in picks if not r.get("dup")]
        if not picks:
            tooltip(tr('Các mục đã chọn đều đã có trong Anki.'), parent=self)
            return
        # đang tìm ảnh: bỏ các việc chưa chạy, thẻ nào chưa có ảnh sẽ được thêm không ảnh
        self._jobs = []
        if core.is_hub_type(self.field_names):
            core.hub_helpers(picks)
        deck_id = self.deck_cb.currentData()
        tags = [t for t in self.tag_ed.text().replace(",", " ").split() if t]
        c = get_cfg()
        c["tag"] = " ".join(tags)
        c["last_deck"] = deck_id
        c["extra"] = self.extra.text()
        save_cfg(c)
        model = self.model
        names = self.field_names
        imgs = [dict(r["img"]) for r in picks]
        auds = [dict(r.get("audio", {})) for r in picks]
        added_rows = list(picks)

        def op(col):
            return core.add_rows(col, model, deck_id, tags, picks, names, imgs, auds)

        def ok(out):
            self._adding = False
            n = getattr(out, "count", len(added_rows))
            self.rows = [r for r in self.rows if r not in added_rows]
            self._rebuild_table()
            self._row_selected()
            self.status.setText(tr('Đã thêm %d thẻ vào Anki.') % n)
            tooltip(tr('Đã thêm %d thẻ vào “%s”.') % (n, self.deck_cb.currentText()), parent=self)
            try:
                step = _mw().col.undo_status().last_step
            except Exception:  # noqa: BLE001
                step = 0
            self._last_add = {"step": step, "rows": added_rows, "n": n} if step else None
            self.undo_add_btn.setVisible(bool(self._last_add))
        self._adding = True
        self.status.setText(tr('Đang thêm thẻ vào Anki…'))
        self._sync_controls()
        self._run_add(op, ok)

    def _undo_last_add(self):
        """Hoàn tác đúng lần thêm vừa rồi bằng chức năng hoàn tác của Anki (chỉ khi chưa có thao tác nào khác xen vào)."""
        info = self._last_add
        if not info or self._adding or self._generating:
            return
        try:
            st = _mw().col.undo_status()
            same = bool(st.undo) and st.last_step == info["step"]
        except Exception:  # noqa: BLE001
            same = False
        if not same:
            self._last_add = None
            self.undo_add_btn.hide()
            showInfo(tr('Không hoàn tác được vì sau lần thêm đó bạn đã làm thao tác khác trong Anki. Bạn có thể xóa thẻ trong Browser (tìm theo nhãn đã đặt).'))
            return
        ans = QMessageBox.question(self, tr('Hoàn tác lần thêm vừa rồi?'),
                                   tr('Xóa %d thẻ vừa thêm khỏi Anki và đưa các dòng về lại bản xem trước?') % info["n"],
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if ans != QMessageBox.StandardButton.Yes:
            return

        def op(col):
            return col.undo()

        def ok(_out):
            self._adding = False
            for r in info["rows"]:
                r["sel"] = True
                r["dup"] = False
            self.rows.extend(info["rows"])
            self._last_add = None
            self.undo_add_btn.hide()
            self._rebuild_table()
            self.status.setText(tr('Đã hoàn tác: %d thẻ đã xóa khỏi Anki, các dòng đã về lại bản xem trước.') % info["n"])
        self._adding = True
        self._sync_controls()
        self._run_add(op, ok, tr('Không hoàn tác được: %s'))

    def _run_add(self, op, ok, fail_msg=None):
        from aqt.operations import CollectionOp
        def failed(error):
            self._adding = False
            self._update_footer()
            showWarning((fail_msg or tr('Không thêm được thẻ: %s')) % error)
        try:
            CollectionOp(parent=self, op=op).success(ok).failure(failed).run_in_background()
        except Exception as error:  # noqa: BLE001
            failed(error)
