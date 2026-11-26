"""Small local GIF players. Respect Anki's Reduce Motion preference."""
from pathlib import Path
from aqt.qt import QLabel, QMovie, QSize, QByteArray, QBuffer, QIODevice, QImage, Qt


class AnimatedLabel(QLabel):
    def __init__(self, parent=None, size=64):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._movie = None
        self._buffer = None
        self._animation_enabled = True

    def clear_animation(self):
        self.setMovie(None)
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if self._buffer:
            self._buffer.close()
            self._buffer.deleteLater()
            self._buffer = None

    def play_data(self, data):
        self.clear_animation()
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(data))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._movie = QMovie(self._buffer, QByteArray(b'gif'), self)
        first = QImage()
        if not first.loadFromData(data):
            self.clear_animation()
            return False
        self._movie.setScaledSize(first.size().scaled(QSize(self.width() - 4, self.height() - 4), Qt.AspectRatioMode.KeepAspectRatio))
        if not self._movie.isValid():
            self.clear_animation()
            return False
        self.setMovie(self._movie)
        self._movie.jumpToFrame(0)
        self._update_playback()
        return True

    def set_animation_enabled(self, enabled):
        self._animation_enabled = bool(enabled)
        self._update_playback()

    def _update_playback(self):
        if not self._movie:
            return
        if self._animation_enabled and self.isVisible():
            self._movie.start()
        else:
            self._movie.stop()
            self._movie.jumpToFrame(0)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_playback()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._movie:
            self._movie.stop()


class StudyCat(AnimatedLabel):
    def __init__(self, parent=None):
        super().__init__(parent, 62)
        self.play_data((Path(__file__).parent / 'assets' / 'study-cat.gif').read_bytes())
