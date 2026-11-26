"""Appearance editor with live preview and reversible changes."""
from copy import deepcopy
import aqt
from aqt.qt import *
from .i18n import tr
from .theme import appearance, colors, apply_theme, PRESETS, valid
from .decorations import StudyGarden


class AppearanceDialog(QDialog):
    def __init__(self, parent, night):
        super().__init__(parent)
        self.night = night
        self.settings = deepcopy(appearance())
        self.previous = getattr(aqt.mw, '_acf_appearance_preview', None)
        self.setWindowTitle(tr('Màu sắc và trang trí'))
        self.resize(640, min(720, int(QApplication.primaryScreen().availableGeometry().height() * .9)))
        self.setMinimumSize(510, 500)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        heading = QLabel(tr('Một góc học tập mang màu của bạn'))
        heading.setObjectName('sectionTitle')
        root.addWidget(heading)
        hint = QLabel(tr('Xem thay đổi ngay trên add-on. Bấm Lưu để giữ, Hủy để trở về.'))
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        root.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 6, 6, 8)
        body.setSpacing(10)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem(tr('Theo theme Anki'), 'anki')
        self.mode.addItem(tr('Palette riêng'), 'custom')
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.settings['mode'])))
        self.source = QComboBox()
        for text, value in [(tr('Tự nhận diện màu Anki'), 'auto'), (tr('Ưu tiên màu nền Anki'), 'background'),
                            (tr('Ưu tiên màu nhấn Anki'), 'accent')]:
            self.source.addItem(text, value)
        self.source.setCurrentIndex(max(0, self.source.findData(self.settings.get('source'))))
        form.addRow(tr('Chế độ'), self.mode)
        form.addRow(tr('Lấy màu từ'), self.source)
        body.addLayout(form)
        note = QLabel(tr('Nền, nút, tab và họa tiết cùng một tông; chữ luôn giữ độ tương phản dễ đọc.'))
        note.setWordWrap(True)
        note.setObjectName('caption')
        body.addWidget(note)
        body.addWidget(QLabel(tr('Palette có sẵn — bấm để thử')))
        grid = QGridLayout()
        self.preset_buttons = {}
        for i, (key, (name, accent, light_bg, dark_bg)) in enumerate(PRESETS.items()):
            button = QPushButton(tr(name))
            button.setCheckable(True)
            button.setMinimumHeight(33)
            swatch = QPixmap(52, 20)
            swatch.fill(Qt.GlobalColor.transparent)
            painter = QPainter(swatch)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            for x, fill in [(10, accent), (25, light_bg), (40, dark_bg)]:
                painter.setBrush(QColor(fill))
                painter.drawEllipse(QRectF(x - 7, 3, 14, 14))
            painter.end()
            button.setIcon(QIcon(swatch))
            button.setIconSize(QSize(52, 20))
            qconnect(button.clicked, lambda checked=False, k=key: self.choose_preset(k))
            self.preset_buttons[key] = button
            grid.addWidget(button, i // 3, i % 3)
        body.addLayout(grid)
        self.custom_frame = QFrame()
        self.custom_frame.setObjectName('inset')
        cf = QFormLayout(self.custom_frame)
        self.edits, self.color_buttons = {}, {}
        for key, label in [('accent', tr('Màu nhấn')), ('light_bg', tr('Nền sáng')), ('dark_bg', tr('Nền tối'))]:
            row = QHBoxLayout()
            edit = QLineEdit(self.settings[key])
            edit.setMaxLength(7)
            edit.setAccessibleName(label)
            button = QPushButton(tr('Chọn màu'))
            button.setMinimumWidth(90)
            qconnect(button.clicked, lambda checked=False, k=key: self.pick_color(k))
            qconnect(edit.editingFinished, lambda k=key: self.edit_color(k))
            row.addWidget(edit, 1)
            row.addWidget(button)
            cf.addRow(label, row)
            self.edits[key], self.color_buttons[key] = edit, button
        body.addWidget(self.custom_frame)
        self.error = QLabel('')
        self.error.setWordWrap(True)
        body.addWidget(self.error)
        self.decor = QCheckBox(tr('Hoa nhỏ, dấu chân mèo và thẻ minh họa'))
        self.decor.setChecked(bool(self.settings.get('decorations', True)))
        body.addWidget(self.decor)
        self.preview = QFrame()
        self.preview.setObjectName('card')
        preview_layout = QHBoxLayout(self.preview)
        garden = StudyGarden(self.preview)
        garden.setFixedSize(156, 110)
        preview_layout.addWidget(garden)
        detail = QVBoxLayout()
        preview_title = QLabel(tr('Xem trước trực tiếp'))
        preview_title.setObjectName('sectionTitle')
        detail.addWidget(preview_title)
        caption = QLabel(tr('Màu dễ thương, chữ dễ đọc.'))
        caption.setObjectName('muted')
        detail.addWidget(caption)
        sample = QPushButton(tr('Thêm vào Anki'))
        sample.setObjectName('primary')
        sample.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        detail.addWidget(sample)
        preview_layout.addLayout(detail, 1)
        body.addWidget(self.preview)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName('primary')
        qconnect(self.buttons.accepted, self.accept)
        qconnect(self.buttons.rejected, self.reject)
        root.addWidget(self.buttons)
        qconnect(self.mode.currentIndexChanged, self._mode_changed)
        qconnect(self.source.currentIndexChanged, self._source_changed)
        qconnect(self.decor.toggled, self._decor_changed)
        self._update_preview()
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)

    def _mode_changed(self):
        self.settings['mode'] = self.mode.currentData()
        self._update_preview()

    def _source_changed(self):
        self.settings['source'] = self.source.currentData()
        self._update_preview()

    def _decor_changed(self, enabled):
        self.settings['decorations'] = bool(enabled)
        self._update_preview()

    def choose_preset(self, key):
        name, accent, light_bg, dark_bg = PRESETS[key]
        self.settings.update(mode='custom', preset=key, accent=accent, light_bg=light_bg, dark_bg=dark_bg)
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(self.mode.findData('custom'))
        self.mode.blockSignals(False)
        for field, edit in self.edits.items():
            edit.setText(self.settings[field])
        self.error.clear()
        self._update_preview()

    def pick_color(self, key):
        color = QColorDialog.getColor(QColor(self.settings[key]), self, tr('Chọn màu'))
        if color.isValid():
            self.edits[key].setText(color.name())
            self.edit_color(key)

    def edit_color(self, key):
        value = self.edits[key].text().strip()
        if len(value) != 7 or not value.startswith('#') or not QColor(value).isValid():
            self.error.setText(tr('Nhập mã màu dạng #RRGGBB.'))
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
            return
        self.settings[key] = QColor(value).name()
        self.settings['preset'] = 'custom'
        self.settings['mode'] = 'custom'
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(self.mode.findData('custom'))
        self.mode.blockSignals(False)
        self.error.clear()
        self._update_preview()

    def _update_preview(self):
        aqt.mw._acf_appearance_preview = dict(self.settings)
        custom = self.settings['mode'] == 'custom'
        self.source.setEnabled(not custom)
        self.custom_frame.setEnabled(custom)
        for key, button in self.preset_buttons.items():
            button.setChecked(custom and self.settings.get('preset') == key)
        self.parent()._apply_current_theme()
        apply_theme(self, self.night())
        from .theme import contrast
        for key, button in self.color_buttons.items():
            fill = valid(self.settings.get(key), '#cccccc')
            text = '#171717' if contrast(fill, '#171717') > contrast(fill, '#ffffff') else '#ffffff'
            button.setStyleSheet('QPushButton { background: %s; color: %s; border: 1px solid %s; }' % (fill, text, fill))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not bool(self.error.text()))

    def done(self, result):
        aqt.mw._acf_appearance_preview = self.previous
        self.parent()._apply_current_theme()
        super().done(result)

    def accept(self):
        if self.settings.get('mode') == 'custom':
            for key, edit in self.edits.items():
                value = edit.text().strip()
                if len(value) != 7 or not value.startswith('#') or not QColor(value).isValid():
                    self.error.setText(tr('Nhập mã màu dạng #RRGGBB.'))
                    edit.setFocus()
                    return
        super().accept()
