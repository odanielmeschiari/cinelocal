"""Dark gray and white theme (palette + QSS)."""
from __future__ import annotations

from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from ..config import CACHE_DIR

COLORS = {
    "bg": "#141414",
    "surface": "#1a1a1a",
    "surface2": "#232323",
    "surface3": "#2d2d2d",
    "border": "#333333",
    "accent": "#ffffff",
    "accent_hover": "#e5e5e5",
    "accent_dark": "#3a3a3a",
    "text": "#e5e5e5",
    "muted": "#8c8c8c",
    "warn": "#ffb454",
}

_QSS = Template("""
QWidget { color: $text; }
QMainWindow, QDialog, QStackedWidget { background: $bg; }
QWidget#page, QWidget#content { background: $bg; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 4px 8px; }

QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox {
    background: $surface; border: 1px solid $border;
    padding: 8px 12px; selection-background-color: $accent;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: $accent; }
QComboBox { combobox-popup: 0; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: $surface2; border: 1px solid $border; outline: 0;
    selection-background-color: $accent_dark; selection-color: $text; padding: 4px;
}

QPushButton, QToolButton {
    background: $surface2; border: 1px solid $border; padding: 8px 16px;
}
QPushButton:hover, QToolButton:hover { background: $surface3; border-color: $accent; }
QPushButton:pressed, QToolButton:pressed { background: $accent_dark; }
QPushButton:checked { background: $accent_dark; border-color: $accent; }
QPushButton:disabled { color: $muted; background: $surface; border-color: $surface2; }
QPushButton[primary="true"] { background: $accent; border-color: $accent; color: $bg; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#iconBtn { background: transparent; border: none; padding: 0; font-size: 26pt; }
QPushButton#iconBtn:hover { background: $surface2; border: none; }
QPushButton#iconBtn:pressed { background: $surface3; }
QPushButton#plainIcon { background: transparent; border: none; padding: 0 6px; font-size: 26pt; }
QPushButton#plainIcon:hover { background: transparent; color: $accent_hover; }
QPushButton#plainIcon:pressed { background: transparent; color: $accent; }
QPushButton#bigIcon { background: transparent; border: none; padding: 0; font-size: 22pt; }
QPushButton#bigIcon:hover { background: transparent; color: $accent_hover; }
QPushButton#bigIcon:checked { background: transparent; color: $accent_hover; }
QPushButton::menu-indicator, QToolButton::menu-indicator { image: none; width: 0; }

QTreeWidget#sidebar { background: $surface; border: none; outline: 0; padding: 10px 6px; }
QTreeWidget#sidebar::item { padding: 7px 10px; margin: 1px 4px; }
QTreeWidget#sidebar::item:hover { background: $surface2; }
QTreeWidget#sidebar::item:selected { background: $accent_dark; color: white; }

QListView#grid { background: transparent; border: none; outline: 0; }

QListWidget { background: $surface; border: 1px solid $border; outline: 0; padding: 4px; }
QListWidget::item { padding: 8px; }
QListWidget::item:hover { background: $surface2; }
QListWidget::item:selected { background: $accent_dark; color: white; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 40px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMenu { background: $surface2; border: 1px solid $border; padding: 6px; }
QMenu::item { padding: 8px 24px; }
QMenu::item:selected { background: $accent_dark; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }

QProgressBar { background: $surface2; border: none; border-radius: 4px; max-height: 8px; text-align: center; }
QProgressBar::chunk { background: $accent; border-radius: 4px; }
QStatusBar { background: $surface; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QCheckBox::indicator, QListWidget::indicator { width: 16px; height: 16px; border: 1px solid $muted; background: $surface; }
QCheckBox::indicator:checked, QListWidget::indicator:checked { image: url($check); border-color: $accent; }
QRadioButton::indicator { width: 16px; height: 16px; border: 1px solid $muted; border-radius: 9px; background: $surface; }
QRadioButton::indicator:checked { border-color: $accent; background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5,
    fx: 0.5, fy: 0.5, stop: 0 $accent, stop: 0.5 $accent, stop: 0.6 $surface, stop: 1 $surface); }

QWidget#scrim { background: rgba(0, 0, 0, 170); }
QFrame#overlayPanel { background: $surface; border: 1px solid $border; }
QFrame#overlayPanel QLabel { background: transparent; }

QFrame#infobar { background: $accent_dark; }
QLabel#muted { color: $muted; }
QLabel#heading { font-size: 20pt; font-weight: 700; }
QLabel#movieTitle { font-size: 24pt; font-weight: 800; }
QLabel#welcomeTitle { font-size: 34pt; font-weight: 800; }
QLabel#section { color: $muted; font-weight: 700; font-size: 9pt; }
QLabel#rating { color: #ffd25e; font-weight: 700; font-size: 12pt; }
QLabel#warn { color: $warn; }
a { color: $accent_hover; }
""")


def _check_mark() -> str:
    """Path of the check mark drawn inside the checked boxes (QSS only takes images from files)."""
    path = CACHE_DIR / "check.png"
    pixmap = QPixmap(32, 32)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(COLORS["accent"]), 2, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
    painter.drawPolyline([QPointF(3.5, 8.2), QPointF(6.6, 11.3), QPointF(12.2, 4.4)])
    painter.end()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(path), "PNG")
    return path.as_posix()


def stylesheet() -> str:
    return _QSS.safe_substitute(COLORS, check=_check_mark())


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    c = {k: QColor(v) for k, v in COLORS.items()}
    palette = QPalette()
    palette.setColor(QPalette.Window, c["bg"])
    palette.setColor(QPalette.WindowText, c["text"])
    palette.setColor(QPalette.Base, c["surface"])
    palette.setColor(QPalette.AlternateBase, c["surface2"])
    palette.setColor(QPalette.Text, c["text"])
    palette.setColor(QPalette.Button, c["surface2"])
    palette.setColor(QPalette.ButtonText, c["text"])
    palette.setColor(QPalette.ToolTipBase, c["surface2"])
    palette.setColor(QPalette.ToolTipText, c["text"])
    palette.setColor(QPalette.Highlight, c["accent"])
    palette.setColor(QPalette.HighlightedText, c["bg"])
    palette.setColor(QPalette.PlaceholderText, c["muted"])
    palette.setColor(QPalette.Link, c["accent_hover"])
    app.setPalette(palette)
    font = QFont(app.font())
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
