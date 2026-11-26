"""Harmonized palettes: host theme colors or a local, user-selected palette."""
from pathlib import Path
import sys
from aqt.qt import QColor, QPalette

PRESETS = {
    'peach': ('Quýt cam', '#ecad78', '#fff7ee', '#29221e'),
    'sunshine': ('Nắng vàng', '#e5c255', '#fffbeb', '#28251b'),
    'strawberry': ('Dâu hồng', '#dca1b1', '#fff4f6', '#2b2228'),
    'lavender': ('Oải hương', '#b6a3da', '#f8f5ff', '#252230'),
    'matcha': ('Matcha', '#a6bd8c', '#f6f9f0', '#22271f'),
    'ocean': ('Biển xanh', '#92bad2', '#f2f8fc', '#202730'),
}
DEFAULT_APPEARANCE = dict(mode='anki', source='auto', preset='peach', accent='#ecad78',
                          light_bg='#fff7ee', dark_bg='#29221e', decorations=True)


def appearance():
    import aqt
    result = dict(DEFAULT_APPEARANCE)
    mw = aqt.mw
    try:
        config = mw.addonManager.getConfig(__name__.split('.')[0]) or {}
        saved = getattr(mw, '_acf_appearance_preview', None)
        if saved is None:
            saved = config.get('appearance', {})
        if isinstance(saved, dict):
            result.update(saved)
    except Exception:
        pass
    return result


def mix(a, b, amount):
    a, b = QColor(a), QColor(b)
    return QColor(*[round(x * (1 - amount) + y * amount) for x, y in
                    zip((a.red(), a.green(), a.blue()), (b.red(), b.green(), b.blue()))]).name()


def luminance(value):
    c = QColor(value)
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                for v in (c.redF(), c.greenF(), c.blueF())]
    return sum(v * w for v, w in zip(channels, (.2126, .7152, .0722)))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


def readable(foreground, background, ratio=4.5):
    """Retain the desired tone, moving toward neutral black/white when needed."""
    if contrast(foreground, background) >= ratio:
        return QColor(foreground).name()
    target = '#171717' if luminance(background) > .3 else '#fafafa'
    for i in range(1, 21):
        candidate = mix(foreground, target, i / 20)
        if contrast(candidate, background) >= ratio:
            return candidate
    return target


def valid(value, fallback):
    if isinstance(value, str) and QColor(value).isValid() and QColor(value).alpha() == 255:
        return QColor(value).name()
    return fallback


def host_colors(night):
    import aqt
    from aqt import colors as native
    mode = 'dark' if night else 'light'
    result = dict(bg=valid(native.CANVAS[mode], '#292929' if night else '#f5f5f5'),
                  panel=valid(native.CANVAS_ELEVATED[mode], '#363636' if night else '#ffffff'),
                  accent=None)
    mw = aqt.mw
    app = getattr(mw, 'app', None)
    if app:
        palette = app.palette()
        window = palette.color(QPalette.ColorRole.Window)
        if (luminance(window) < .25) == bool(night):
            result['bg'] = window.name()
        accent = palette.color(QPalette.ColorRole.Highlight)
        if accent.hsvSaturationF() > .15:
            result['accent'] = accent.name()
    snapshot = getattr(mw, '_acf_theme_snapshot', None)
    if snapshot and snapshot.get('night') == bool(night):
        for key in ('bg', 'panel', 'accent'):
            if snapshot.get(key):
                result[key] = valid(snapshot[key], result.get(key))
    # The already-loaded Onigiri module exposes a read-only theme configuration.
    # Read its actual accent and surface tokens, never its foreground text color.
    bridge = sys.modules.get('1011095603.core.config')
    if bridge and callable(getattr(bridge, 'get_config_readonly', None)):
        try:
            tokens = bridge.get_config_readonly().get('colors', {}).get(mode, {})
            for target, keys in {'bg': ('--bg',), 'panel': ('--canvas-inset',),
                                 'accent': ('--accent-color', '--button-primary-bg')}.items():
                for key in keys:
                    if isinstance(tokens.get(key), str) and QColor(tokens[key]).isValid():
                        result[target] = valid(tokens[key], result.get(target))
                        break
        except Exception:
            pass
    return result


def colors(night):
    settings = appearance()
    host = host_colors(night)
    if settings.get('mode') == 'custom':
        bg = valid(settings.get('dark_bg' if night else 'light_bg'), '#25252b' if night else '#fff7ee')
        seed = valid(settings.get('accent'), '#ecad78')
        panel = mix(bg, '#ffffff', .035 if luminance(bg) < .25 else .65)
    else:
        bg, panel = host['bg'], host['panel']
        canvas = max((QColor(bg), QColor(panel)), key=lambda c: c.hsvSaturationF())
        source = settings.get('source', 'auto')
        if source == 'auto':
            # Follow whichever part of Anki the user just changed. This handles
            # a pale yellow canvas as well as a bright orange accent.
            import aqt
            history = getattr(aqt.mw, '_acf_color_history', {})
            previous, detected = history.get(bool(night), (None, 'auto'))
            if previous:
                if any(host[k] != previous[k] for k in ('bg', 'panel')):
                    detected = 'background'
                elif host['accent'] != previous['accent']:
                    detected = 'accent'
            history[bool(night)] = (dict(host), detected)
            aqt.mw._acf_color_history = history
            source = detected
        if source == 'background' or (source == 'auto' and canvas.hsvSaturationF() >= .20):
            seed = canvas.name() if canvas.hsvSaturationF() > .06 else host['accent']
        else:
            seed = host['accent'] or (canvas.name() if canvas.hsvSaturationF() > .06 else None)
        seed = valid(seed, '#c8aa8c')
    dark = luminance(bg) < .25
    if contrast(panel, '#fafafa' if dark else '#252525') < 4.5:
        panel = mix(bg, '#ffffff', .045 if dark else .65)
    text = readable('#eeeae5' if dark else '#322d29', panel)
    muted = readable(mix(text, panel, .28), panel)
    primary = valid(seed, '#c8aa8c')
    if dark:
        primary = mix(primary, '#19191c', .08)
    primary_text = '#171717' if contrast(primary, '#171717') >= contrast(primary, '#ffffff') else '#ffffff'
    accent = readable(seed, panel)
    selection = mix(panel, seed, .20 if dark else .24)
    return dict(bg=bg, panel=panel, text=text, muted=muted,
                soft=mix(panel, seed, .06 if dark else .08), edge=mix(panel, seed, .30),
                accent=accent, accent_hover=readable(mix(seed, text, .15), panel),
                primary=primary, primary_text=primary_text,
                primary_hover=mix(primary, '#ffffff' if dark else '#000000', .08),
                selection=selection, disabled=mix(panel, seed, .24),
                danger=readable('#cb7a8c', panel), warning=readable('#b38a30', panel), seed=seed)


def make_style(night):
    c = colors(night)
    assets = Path(__file__).resolve().parent / 'assets'
    c.update(chevron=(assets / ('chevron-light.svg' if luminance(c['bg']) < .25 else 'chevron.svg')).as_posix(),
             check=(assets / ('check-dark.svg' if c['primary_text'] == '#171717' else 'check.svg')).as_posix())
    return """
QDialog, QDialog QWidget { color: %(text)s; }
QDialog { background: %(bg)s; color: %(text)s; font-size: 10pt; }
QWidget { color: %(text)s; }
QLabel { background: transparent; }
QLabel#title { font-size: 21px; font-weight: 700; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; }
QLabel#muted, QLabel#caption { color: %(muted)s; }
QLabel#caption { font-size: 9pt; }
QLabel#badge { background: %(selection)s; color: %(accent)s; border-radius: 10px; padding: 5px 10px; font-weight: 600; }
QLabel#emptyMark { background: %(selection)s; color: %(accent)s; border-radius: 18px; font-size: 26px; font-weight: 600; }
QLabel#imageThumb { background: %(soft)s; color: %(muted)s; border: 1px dashed %(edge)s; border-radius: 9px; }
QFrame#card { background: %(panel)s; border: 1px solid %(edge)s; border-radius: 12px; }
QFrame#inset { background: %(soft)s; border: 1px solid %(edge)s; border-radius: 8px; }
QGroupBox { background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; border-radius: 10px; margin-top: 12px; padding: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton, QToolButton { background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; border-radius: 7px; padding: 7px 11px; font-weight: 600; }
QPushButton:hover, QToolButton:hover { border-color: %(accent)s; background: %(soft)s; }
QPushButton:pressed, QToolButton:checked { background: %(selection)s; border-color: %(accent)s; }
QPushButton:focus, QToolButton:focus { border: 2px solid %(accent)s; padding: 6px 10px; }
QPushButton#primary { background: %(primary)s; color: %(primary_text)s; border-color: %(primary)s; padding: 9px 14px; }
QPushButton#primary:hover { background: %(primary_hover)s; border-color: %(primary_hover)s; }
QPushButton#primary:focus { border: 2px solid %(accent_hover)s; padding: 8px 13px; }
QPushButton:disabled, QToolButton:disabled { color: %(muted)s; background: %(soft)s; }
QPushButton#primary:disabled { background: %(disabled)s; border-color: %(disabled)s; color: %(muted)s; }
QPushButton#quiet { background: transparent; color: %(muted)s; padding: 5px 8px; }
QPushButton#danger { color: %(danger)s; }
QLineEdit, QPlainTextEdit, QComboBox, QTableWidget, QListWidget { background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; border-radius: 7px; selection-background-color: %(selection)s; selection-color: %(text)s; }
QLineEdit, QComboBox { padding: 7px 9px; min-height: 18px; }
QPlainTextEdit { padding: 7px; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QListWidget:focus { border-color: %(accent)s; }
QLineEdit:disabled, QComboBox:disabled { background: %(soft)s; color: %(muted)s; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url("%(chevron)s"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; selection-background-color: %(selection)s; selection-color: %(text)s; }
QCheckBox { color: %(text)s; spacing: 7px; padding: 3px 0; }
QCheckBox:disabled { color: %(muted)s; }
QCheckBox::indicator { width: 15px; height: 15px; }
QCheckBox::indicator:unchecked, QTableWidget::indicator:unchecked { background: %(panel)s; border: 1px solid %(muted)s; border-radius: 3px; width: 14px; height: 14px; }
QCheckBox::indicator:checked, QTableWidget::indicator:checked { background: %(primary)s; border: 1px solid %(primary)s; border-radius: 3px; image: url("%(check)s"); width: 14px; height: 14px; }
QTableWidget { alternate-background-color: %(soft)s; gridline-color: %(edge)s; }
QTableWidget::item { padding: 5px; border-bottom: 1px solid %(edge)s; }
QTableWidget::item:selected, QListWidget::item:selected { background: %(selection)s; color: %(text)s; }
QHeaderView { background: %(panel)s; }
QHeaderView::section { background: %(soft)s; color: %(muted)s; padding: 9px 6px; border: 0; border-bottom: 1px solid %(edge)s; font-weight: 600; }
QTableCornerButton::section { background: %(soft)s; border: none; }
QTabWidget::pane { background: transparent; border: none; padding-top: 8px; }
QTabBar::tab { background: transparent; color: %(muted)s; padding: 9px 12px; margin-right: 3px; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: %(accent)s; border-bottom: 2px solid %(accent)s; background: %(selection)s; }
QTabBar::tab:hover { color: %(accent)s; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: %(edge)s; border-radius: 3px; }
QSplitter::handle:vertical { background: %(edge)s; border-top: 5px solid %(panel)s; border-bottom: 5px solid %(panel)s; border-radius: 0; }
QSplitter::handle:vertical:hover { background: %(accent)s; }
QTabWidget::tab-bar { alignment: left; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: %(edge)s; border-radius: 5px; min-height: 28px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: %(edge)s; border-radius: 5px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QProgressBar { background: %(soft)s; border: none; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: %(accent)s; border-radius: 2px; }
QMenu { background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; padding: 5px; }
QMenu::item { color: %(text)s; background: transparent; padding: 9px 18px; border-radius: 5px; }
QMenu::item:disabled { color: %(muted)s; }
QMenu::separator { height: 1px; background: %(edge)s; margin: 5px 8px; }
QMenu::item:selected { background: %(selection)s; }
QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; padding: 5px; }
""" % c


def apply_theme(widget, night):
    from aqt.qt import QWidget
    c = colors(night)
    widget._acf_colors = c
    palette = QPalette(widget.palette())
    for role, value in {
        QPalette.ColorRole.Window: c['bg'], QPalette.ColorRole.Base: c['panel'],
        QPalette.ColorRole.AlternateBase: c['soft'], QPalette.ColorRole.Text: c['text'],
        QPalette.ColorRole.WindowText: c['text'], QPalette.ColorRole.Button: c['panel'],
        QPalette.ColorRole.ButtonText: c['text'], QPalette.ColorRole.Highlight: c['selection'],
        QPalette.ColorRole.HighlightedText: c['text'], QPalette.ColorRole.PlaceholderText: c['muted'],
        QPalette.ColorRole.Link: c['accent'], QPalette.ColorRole.ToolTipText: c['text'],
        QPalette.ColorRole.ToolTipBase: c['panel'],
    }.items():
        palette.setColor(role, QColor(value))
    widget.setPalette(palette)
    widget.setStyleSheet(make_style(night))
    for child in widget.findChildren(QWidget):
        if child.property('acfDecoration'):
            child.setVisible(bool(appearance().get('decorations', True)))
            child.update()


def capture_web_canvas(night, done):
    """Read only the dashboard's computed theme colors, never card content."""
    import aqt
    from aqt.qt import QColor
    mw = aqt.mw
    if getattr(mw, 'state', None) not in ('deckBrowser', 'overview') or not hasattr(mw, 'web'):
        return False
    script = r"""(() => {
        const hex = value => {
            value = value.trim();
            if (/^#[0-9a-f]{3,6}$/i.test(value)) return value;
            const m = value.match(/^rgba?\(([^)]+)\)/);
            if (!m) return null;
            const n = m[1].split(',').map(Number);
            if (n.length > 3 && n[3] < 0.95) return null;
            return '#' + n.slice(0,3).map(x => Math.round(x).toString(16).padStart(2,'0')).join('');
        };
        const body = getComputedStyle(document.body);
        const root = getComputedStyle(document.documentElement);
        return {bg: hex(body.backgroundColor) || hex(root.backgroundColor) || hex(root.getPropertyValue('--bg')),
                panel: hex(root.getPropertyValue('--canvas-inset')) || hex(body.getPropertyValue('--canvas-inset')),
                accent: ['--accent-color', '--primary', '--bs-primary', '--link', '--button-primary-bg'].map(key => hex(root.getPropertyValue(key)) || hex(body.getPropertyValue(key))).find(Boolean) || null};
    })()"""
    def received(result):
        if isinstance(result, dict) and QColor(result.get('bg') or '').isValid():
            bg = QColor(result['bg'])
            if (bg.lightnessF() < .5) == bool(night):
                previous = getattr(mw, '_acf_theme_snapshot', None)
                mw._acf_theme_snapshot = dict(bg=bg.name(), night=bool(night))
                accent = QColor(result.get('accent') or '')
                if accent.isValid():
                    mw._acf_theme_snapshot['accent'] = accent.name()
                panel = QColor(result.get('panel') or '')
                if panel.isValid():
                    mw._acf_theme_snapshot['panel'] = panel.name()
                if mw._acf_theme_snapshot != previous:
                    done()
    try:
        mw.web.evalWithCallback(script, received)
        return True
    except Exception:
        return False
