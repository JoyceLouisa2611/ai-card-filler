# -*- coding: utf-8 -*-
"""Điền ô còn trống cho các ghi chú ĐÃ CÓ (chọn trong Browser). Chỉ ghi vào ô trống, hoàn tác được bằng Ctrl+Z của Anki."""
from __future__ import annotations

import json
from collections import Counter

import aqt
from aqt.qt import *
from aqt.utils import showInfo, showWarning, tooltip

from . import core
from .i18n import tr
from .theme import apply_theme, colors
from .ui import _night, bg, get_cfg, pixmap_of, shrink_jpeg, save_cfg


class FillExistingDialog(QDialog):
    def __init__(self, parent, note_ids):
        super().__init__(parent)
        self.setWindowTitle(tr('AI Card Filler: điền ô trống cho thẻ có sẵn'))
        apply_theme(self, _night())
        self.resize(980, 700)
        col = aqt.mw.col
        mids = Counter(col.get_note(n).mid for n in note_ids)
        self.mid = mids.most_common(1)[0][0]
        self.note_ids = [n for n in note_ids if col.get_note(n).mid == self.mid]
        self.skipped_other = len(note_ids) - len(self.note_ids)
        self.model = col.models.get(self.mid)
        self.field_names = [f["name"] for f in self.model["flds"]]
        self.tcfg = core.type_config(get_cfg(), self.model["name"], self.field_names)
        self.fillable = [n for n in self.field_names[1:] if self.tcfg["roles"].get(n) in (core.ROLE_AI, core.ROLE_IMG)]
        self.rows = []
        self._busy = 0
        self._generating = False
        self._applying = False
        self._cancel = False
        self._jobs = []
        self._paste_targets = []
        self._build()
        self._refresh_targets()

    # ------------------------------------------------------------ giao diện
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        title = QLabel(tr('Điền ô trống cho %d ghi chú · loại “%s”') % (len(self.note_ids), self.model["name"]))
        title.setObjectName("sectionTitle")
        lay.addWidget(title)
        note = tr('Chỉ ô đang TRỐNG được điền; ô đã có nội dung không bao giờ bị ghi đè. Bạn xem và sửa kết quả trước khi áp dụng, và có thể hoàn tác bằng Ctrl+Z trong Browser.')
        if self.skipped_other:
            note += "\n" + tr('Đã bỏ qua %d ghi chú thuộc loại khác (chỉ xử lý loại có nhiều ghi chú nhất trong phần chọn).') % self.skipped_other
        lab = QLabel(note)
        lab.setWordWrap(True)
        lab.setObjectName("muted")
        lay.addWidget(lab)

        box = QFrame()
        box.setObjectName("card")
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel(tr('Các ô được phép điền:')))
        self.checks = {}
        grid = QGridLayout()
        for k, n in enumerate(self.fillable):
            cb = QCheckBox(n + (tr(' (ảnh)') if self.tcfg["roles"].get(n) == core.ROLE_IMG and not core.IMG_RE.search(n) else ""))
            cb.setChecked(True)
            qconnect(cb.toggled, lambda *_: self._refresh_targets())
            self.checks[n] = cb
            grid.addWidget(cb, k // 3, k % 3)
        bl.addLayout(grid)
        self.target_info = QLabel("")
        self.target_info.setObjectName("caption")
        bl.addWidget(self.target_info)
        lay.addWidget(box)

        row = QHBoxLayout()
        self.go_btn = QPushButton(tr('Tạo bằng AI'))
        self.go_btn.setObjectName("primary")
        qconnect(self.go_btn.clicked, self._generate)
        self.copy_btn = QPushButton(tr('Sao chép prompt'))
        qconnect(self.copy_btn.clicked, self._copy_prompt)
        self.auto_img = QCheckBox(tr('Tự tìm ảnh cho ô ảnh'))
        self.auto_img.setChecked(True)
        self.stop_btn = QPushButton(tr('Dừng'))
        qconnect(self.stop_btn.clicked, self._stop)
        self.stop_btn.hide()
        row.addWidget(self.go_btn)
        row.addWidget(self.copy_btn)
        row.addWidget(self.auto_img)
        row.addStretch(1)
        row.addWidget(self.stop_btn)
        lay.addLayout(row)
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText(tr('Hoặc dán kết quả JSON từ AI (cho lượt prompt đã sao chép) vào đây…'))
        self.paste.setFixedHeight(64)
        lay.addWidget(self.paste)
        self.paste_btn = QPushButton(tr('Áp dụng kết quả đã dán'))
        qconnect(self.paste_btn.clicked, self._from_paste)
        lay.addWidget(self.paste_btn)

        self.status = QLabel("")
        self.status.setObjectName("caption")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        lay.addWidget(self.progress)

        tools = QHBoxLayout()
        self.remove_btn = QPushButton(tr('Bỏ dòng'))
        self.remove_btn.setObjectName("danger")
        qconnect(self.remove_btn.clicked, self._remove_selected)
        tools.addWidget(self.remove_btn)
        tools.addStretch(1)
        lay.addLayout(tools)
        self.table = QTableWidget(0, 0)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        qconnect(self.table.itemChanged, self._cell_changed)
        qconnect(self.table.itemSelectionChanged, self._sync)
        lay.addWidget(self.table, 1)
        self.del_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self.table)
        self.del_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        qconnect(self.del_shortcut.activated, self._remove_selected)

        foot = QHBoxLayout()
        foot.addWidget(QLabel(tr('Nhãn gắn thêm:')))
        self.tag_ed = QLineEdit(get_cfg().get("fill_tag", "ai-filled"))
        self.tag_ed.setPlaceholderText(tr('Để trống nếu không muốn gắn nhãn'))
        self.tag_ed.setMaximumWidth(240)
        foot.addWidget(self.tag_ed)
        foot.addStretch(1)
        self.apply_btn = QPushButton(tr('Áp dụng vào ghi chú'))
        self.apply_btn.setObjectName("primary")
        qconnect(self.apply_btn.clicked, self._apply)
        foot.addWidget(self.apply_btn)
        lay.addLayout(foot)
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)
        self._rebuild_table()

    # ------------------------------------------------------------ mục tiêu
    def _want(self):
        return {n for n, cb in self.checks.items() if cb.isChecked()}

    def _targets(self):
        return core.fill_targets(aqt.mw.col, self.note_ids, self.field_names, self.tcfg, self._want())

    def _refresh_targets(self):
        t = self._targets()
        self.target_info.setText(tr('%d / %d ghi chú có ô trống cần điền.') % (len(t), len(self.note_ids)))
        self._sync()

    def _ready(self):
        cfg = self._cfg()
        return core.provider_ready(cfg, cfg["provider"])

    def _cfg(self):
        return get_cfg()

    def _sync(self):
        locked = bool(self._generating or self._applying)
        self.go_btn.setEnabled(self._ready() and not locked and not self._busy)
        self.copy_btn.setEnabled(not locked)
        self.paste_btn.setEnabled(not locked)
        self.go_btn.setToolTip("" if self._ready() else tr('Chưa cấu hình dịch vụ AI: mở AI Card Filler → tab “Tự động (API)”. Bạn vẫn dùng được cách sao chép/dán.'))
        self.remove_btn.setEnabled(bool(self.table.selectionModel().selectedRows()) and not locked)
        self.apply_btn.setEnabled(bool(self.rows) and not locked and not self._busy)
        self.stop_btn.setVisible(bool(self._generating or self._busy))
        self.progress.setVisible(bool(self._generating or self._busy or self._applying))

    # ------------------------------------------------------------ prompt
    def _example(self):
        return core.HUB_EXAMPLE if core.is_hub_type(self.field_names) else None

    def _chunks(self, targets):
        size = max(2, int(get_cfg().get("chunk_size", 20) or 20))
        chunks = [targets[i:i + size] for i in range(0, len(targets), size)]
        if len(chunks) > 1 and len(chunks[-1]) < 1:
            chunks.pop()
        return chunks

    def _prompt_for(self, targets):
        return core.build_fill_prompt(self.field_names, self.tcfg, targets, extra=get_cfg().get("extra", ""), example=self._example())

    def _copy_prompt(self):
        t = self._targets()
        if not t:
            tooltip(tr('Không có ô trống nào cần điền.'), parent=self)
            return
        self._paste_targets = t[:30]
        QApplication.clipboard().setText(self._prompt_for(self._paste_targets))
        extra = tr(' (chỉ %d ghi chú đầu; chọn ít ghi chú hơn hoặc dùng “Tạo bằng AI” để chạy hết)') % len(self._paste_targets) if len(t) > 30 else ""
        self.status.setText(tr('Đã sao chép prompt cho %d ghi chú%s. Gửi cho AI rồi dán kết quả vào ô bên dưới.') % (len(self._paste_targets), extra))

    # ------------------------------------------------------------ tạo bằng AI
    def _generate(self):
        if self._generating or self._busy or self._applying:
            return
        cfg = self._cfg()
        targets = self._targets()
        if not targets:
            tooltip(tr('Không có ô trống nào cần điền.'), parent=self)
            return
        done_keys = {r["t"]["nid"] for r in self.rows}
        targets = [t for t in targets if t["nid"] not in done_keys]
        if not targets:
            tooltip(tr('Tất cả đã có trong bảng bên dưới.'), parent=self)
            return
        chunks = self._chunks(targets)
        prompts = [self._prompt_for(c) for c in chunks]
        self._cancel = False
        self._generating = True
        self._total, self._done_n = len(chunks), 0
        self.status.setText(tr('AI đang điền… lượt %d/%d') % (1, self._total))
        self.progress.setRange(0, max(1, self._total))
        self.progress.setValue(0)
        self._sync()
        tm = aqt.mw.taskman
        on_main = getattr(tm, "run_on_main", None) or (lambda f: f())

        def work():
            out, last = [], None
            for i, (pr, chunk) in enumerate(zip(prompts, chunks)):
                if self._cancel:
                    return out, None, i
                matched = None
                for _try in range(2):
                    try:
                        matched = core.match_fill(core.parse_ai_json(core.ai_text(cfg, pr)), chunk, self.field_names[0])
                        break
                    except (core.AIError, core.QuotaError) as e:
                        last = e
                        break
                    except Exception as e:  # noqa: BLE001
                        last = e
                if matched is None:
                    return out, last, i
                out.extend(matched)
                on_main(lambda n=i + 1: self._progress(n))
            return out, None, len(chunks)

        def done(res, err):
            self._generating = False
            if err:
                showWarning(tr('AI báo lỗi: %s') % err)
                self._sync()
                return
            matched, last, finished = res
            self._take(matched)
            if last:
                showWarning(tr('AI báo lỗi: %s') % last + (tr('\n\nĐã xử lý %d/%d lượt. Bấm “Tạo bằng AI” lần nữa để làm tiếp phần còn thiếu.') % (finished, len(prompts)) if matched else ""))
            elif self._cancel:
                self.status.setText(tr('Đã dừng sau %d/%d lượt.') % (finished, len(prompts)))
            self._sync()
        bg(work, done)

    def _progress(self, n):
        self._done_n = n
        self.progress.setValue(n)
        if self._generating:
            self.status.setText(tr('AI đang điền… lượt %d/%d') % (min(n + 1, self._total), self._total))

    def _stop(self):
        self._cancel = True
        self._jobs = []
        self.status.setText(tr('Đang dừng, chờ lượt đang chạy xong…'))

    def _from_paste(self):
        if not self._paste_targets:
            self._paste_targets = self._targets()[:30]
        if not self._paste_targets:
            return
        try:
            items = core.parse_ai_json(self.paste.toPlainText())
        except Exception as e:  # noqa: BLE001
            showWarning(tr('Không đọc được kết quả: %s\nHãy copy cả khối mã JSON mà AI trả về.') % e)
            return
        self._take(core.match_fill(items, self._paste_targets, self.field_names[0]))
        self.paste.clear()
        self._sync()

    def _take(self, matched):
        """Biến kết quả AI thành các dòng xem trước."""
        miss = 0
        fresh = []
        have = {r["t"]["nid"] for r in self.rows}
        for t, item in matched:
            if item is None:
                miss += 1
                continue
            if t["nid"] in have:
                continue
            f, q = {}, {}
            for n in t["need"]:
                role = self.tcfg["roles"].get(n)
                if role == core.ROLE_AI:
                    v = item.get(n.lower())
                    f[n] = "" if v is None else str(v).strip()
                elif role == core.ROLE_IMG:
                    ka, kb = core.img_keys(n)
                    q[n] = [str(item.get(ka.lower(), "") or "").strip(), str(item.get(kb.lower(), "") or "").strip()]
            row = {"t": t, "f": f, "q": q, "img": {}, "thumbs": {}}
            self.rows.append(row)
            fresh.append(row)
        self._rebuild_table()
        msg = tr('Đã có kết quả cho %d ghi chú.') % len(fresh)
        if miss:
            msg += tr(' AI chưa trả về cho %d ghi chú (thử lại hoặc làm tiếp).') % miss
        self.status.setText(msg)
        if self.auto_img.isChecked():
            self._auto_images(fresh)

    # ------------------------------------------------------------ bảng
    def _text_cols(self):
        return sorted({n for r in self.rows for n in r["f"]}, key=self.field_names.index) if self.rows else [n for n in self.fillable if self.tcfg["roles"].get(n) == core.ROLE_AI and n in self._want()]

    def _img_cols(self):
        return [n for n in self.fillable if self.tcfg["roles"].get(n) == core.ROLE_IMG and n in self._want()]

    def _rebuild_table(self):
        self.table.blockSignals(True)
        self.tc, self.ic = self._text_cols(), self._img_cols()
        cols = [self.field_names[0]] + self.tc + [tr('Ảnh: ') + n for n in self.ic]
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            k = QTableWidgetItem(r["t"]["key"])
            k.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 0, k)
            for j, n in enumerate(self.tc):
                it = QTableWidgetItem(r["f"].get(n, "") if n in r["f"] else "")
                if n not in r["f"]:
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    it.setToolTip(tr('Ô này đã có nội dung, không bị thay đổi.'))
                self.table.setItem(i, 1 + j, it)
            for j, n in enumerate(self.ic):
                self._set_img_cell(i, 1 + len(self.tc) + j, r, n)
        self.table.resizeColumnsToContents()
        for j in range(1, 1 + len(self.tc)):
            self.table.setColumnWidth(j, min(max(self.table.columnWidth(j), 100), 280))
        self.table.setIconSize(QSize(40, 30))
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.blockSignals(False)
        self._sync()

    def _set_img_cell(self, i, c, r, n):
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if n not in r["t"]["need"]:
            it.setText(tr('đã có'))
        else:
            pm = pixmap_of(r["img"].get(n), 40, 30)
            if pm:
                it.setIcon(QIcon(pm))
            else:
                it.setText("—")
        self.table.setItem(i, c, it)

    def _cell_changed(self, item):
        i, c = item.row(), item.column()
        if i >= len(self.rows) or not (1 <= c < 1 + len(self.tc)):
            return
        n = self.tc[c - 1]
        if n in self.rows[i]["f"]:
            self.rows[i]["f"][n] = item.text().strip()

    def _remove_selected(self):
        if self._generating or self._applying:
            return
        idx = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not idx:
            return
        gone = {id(self.rows[i]) for i in idx if i < len(self.rows)}
        self.rows = [r for r in self.rows if id(r) not in gone]
        self._rebuild_table()
        self.status.setText(tr('Đã bỏ %d dòng khỏi danh sách (ghi chú gốc không bị đụng tới).') % len(gone))

    # ------------------------------------------------------------ ảnh
    def _auto_images(self, rows):
        jobs = [(r, n) for r in rows for n in self.ic if n in r["t"]["need"] and not r["img"].get(n)]
        if not jobs:
            return
        self._busy += 1
        self._jobs = list(jobs)
        self._active = 0
        self._job_total, self._job_done = len(jobs), 0
        self._open = True
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self._sync()
        for _ in range(4):
            self._next_job()

    def _queries(self, r, n):
        q, alt = (r["q"].get(n) or ["", ""])[:2]
        out = []
        for x in (q, alt, r["t"]["key"]):
            x = (x or "").strip()
            if x and x not in out:
                out.append(x)
        return out

    def _next_job(self):
        if not self._jobs:
            if self._active == 0 and getattr(self, "_open", False):
                self._open = False
                self._busy = max(0, self._busy - 1)
                self._rebuild_table()
                miss = sum(1 for r in self.rows for n in self.ic if n in r["t"]["need"] and not r["img"].get(n))
                self.status.setText(tr('Đã tìm ảnh xong.') + (tr(' %d ô ảnh chưa có (sẽ bị bỏ trống).') % miss if miss else ""))
            return
        r, n = self._jobs.pop(0)
        self._active += 1
        qs = self._queries(r, n)

        def done(res, err):
            self._active -= 1
            self._job_done += 1
            if res and res[0] and r in self.rows:
                try:
                    r["img"][n] = shrink_jpeg(res[0], int(get_cfg().get("image_max_side", 512)))
                except Exception:  # noqa: BLE001
                    pass
            self.progress.setValue(self._job_done)
            self.status.setText(tr('Đang tìm ảnh… %d/%d') % (self._job_done, self._job_total))
            self._next_job()
        bg(lambda: core.find_image_bytes(qs), done)

    # ------------------------------------------------------------ áp dụng
    def _apply(self):
        if self._generating or self._busy or self._applying or not self.rows:
            return
        updates = [{"nid": r["t"]["nid"], "f": dict(r["f"]), "img": dict(r["img"])} for r in self.rows]
        tags = [t for t in self.tag_ed.text().replace(",", " ").split() if t]
        c = get_cfg()
        c["fill_tag"] = " ".join(tags)
        save_cfg(c)
        n_rows = len(self.rows)

        def op(col):
            return core.update_notes_fill(col, updates, tags)[0]

        def ok(_out):
            self._applying = False
            self.rows = []
            self._rebuild_table()
            self._refresh_targets()
            self.status.setText(tr('Đã cập nhật %d ghi chú. Nếu cần hoàn tác: Ctrl+Z trong Browser (hoặc Edit → Undo).') % n_rows)
            tooltip(tr('Đã cập nhật %d ghi chú.') % n_rows, parent=self)

        def failed(err):
            self._applying = False
            self._sync()
            showWarning(tr('Không cập nhật được: %s') % err)
        self._applying = True
        self._sync()
        self._run_op(op, ok, failed)

    def _run_op(self, op, ok, failed):
        from aqt.operations import CollectionOp
        try:
            CollectionOp(parent=self, op=op).success(ok).failure(failed).run_in_background()
        except Exception as e:  # noqa: BLE001
            failed(e)
