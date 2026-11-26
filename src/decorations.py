"""Tiny theme-aware UI doodles, painted natively at any display scale."""
from pathlib import Path
from aqt.qt import QWidget, QPainter, QPainterPath, QPen, QColor, QRectF, QPixmap, Qt
from .theme import colors


class StudyGarden(QWidget):
    def __init__(self, parent=None, small=False):
        super().__init__(parent)
        self.small = small
        self.setProperty('acfDecoration', True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(72, 22) if small else self.setFixedSize(224, 154)
        self.cat = QPixmap(str(Path(__file__).parent / 'assets' / 'study-cat.png'))

    def paintEvent(self, event):
        c = getattr(self.window(), '_acf_colors', None) or colors(False)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if self.small:
            self._paw(p, 14, 13, c)
            self._flower(p, 39, 11, 4, c)
            self._sparkle(p, 62, 11, 5, c)
            return
        p.scale(self.width() / 224, self.height() / 154)
        # A little stack of flashcards, a familiar cat, and two quiet flowers.
        p.setPen(QPen(QColor(c['edge']), 1.5))
        p.setBrush(QColor(c['soft']))
        p.drawRoundedRect(QRectF(39, 27, 142, 105), 18, 18)
        p.save()
        p.translate(112, 78)
        p.rotate(-7)
        p.setBrush(QColor(c['panel']))
        p.drawRoundedRect(QRectF(-74, -50, 148, 103), 16, 16)
        p.restore()
        p.setPen(QPen(QColor(c['primary']), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(56, 47, 80, 44)
        p.setPen(QPen(QColor(c['edge']), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(55, 59, 78, 56)
        p.drawPixmap(76, 40, 97, 97, self.cat)
        self._flower(p, 24, 94, 7, c)
        self._flower(p, 201, 53, 6, c)
        self._sparkle(p, 192, 116, 8, c)
        self._sparkle(p, 35, 30, 6, c)
        self._paw(p, 59, 137, c)

    @staticmethod
    def _flower(p, x, y, size, c):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['selection']))
        for dx, dy in ((0, -size), (size, 0), (0, size), (-size, 0)):
            p.drawEllipse(QRectF(x + dx - size * .65, y + dy - size * .65, size * 1.3, size * 1.3))
        p.setBrush(QColor(c['primary']))
        p.drawEllipse(QRectF(x - size * .45, y - size * .45, size * .9, size * .9))

    @staticmethod
    def _sparkle(p, x, y, size, c):
        path = QPainterPath()
        path.moveTo(x, y - size)
        path.quadTo(x + 1, y - 1, x + size, y)
        path.quadTo(x + 1, y + 1, x, y + size)
        path.quadTo(x - 1, y + 1, x - size, y)
        path.quadTo(x - 1, y - 1, x, y - size)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['primary']))
        p.drawPath(path)

    @staticmethod
    def _paw(p, x, y, c):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['primary']))
        p.drawEllipse(QRectF(x - 4, y - 1, 8, 6))
        for dx, dy in ((-6, -5), (-2, -8), (3, -8), (7, -4)):
            p.drawEllipse(QRectF(x + dx - 1.8, y + dy, 3.6, 4.4))
