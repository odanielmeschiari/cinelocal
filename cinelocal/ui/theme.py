"""Dark black-and-blue theme (palette + QSS)."""
from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#06080d",
    "surface": "#0c1119",
    "surface2": "#131a26",
    "surface3": "#1a2333",
    "border": "#1f2b40",
    "accent": "#2f80ff",
    "accent_hover": "#5a9bff",
    "accent_dark": "#17407f",
    "text": "#e9eef7",
    "muted": "#8693ab",
    "warn": "#ffb454",
}

_QSS = Template("""
QWidget { color: $text; }
QMainWindow, QDialog, QStackedWidget { background: $bg; }
QWidget#page, QWidget#content { background: $bg; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 4px 8px; }

QLineEdit, QComboBox, QTextEdit {
    background: $surface; border: 1px solid $border; border-radius: 9px;
    padding: 8px 12px; selection-background-color: $accent;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: $surface2; border: 1px solid $border; outline: 0;
    selection-background-color: $accent_dark; padding: 4px;
}

QPushButton, QToolButton {
    background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 8px 16px;
}
QPushButton:hover, QToolButton:hover { background: $surface3; border-color: $accent; }
QPushButton:pressed, QToolButton:pressed { background: $accent_dark; }
QPushButton:checked { background: $accent_dark; border-color: $accent; }
QPushButton:disabled { color: $muted; background: $surface; border-color: $surface2; }
QPushButton[primary="true"] { background: $accent; border-color: $accent; color: white; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#iconBtn { background: transparent; border: none; border-radius: 10px; padding: 0; font-size: 26pt; }
QPushButton#iconBtn:hover { background: $surface2; border: none; }
QPushButton#iconBtn:pressed { background: $surface3; }
QPushButton#plainIcon { background: transparent; border: none; padding: 0 6px; font-size: 26pt; }
QPushButton#plainIcon:hover { background: transparent; color: $accent_hover; }
QPushButton#plainIcon:pressed { background: transparent; color: $accent; }
QPushButton#bigIcon { background: transparent; border: none; padding: 0 10px; font-size: 22pt; }
QPushButton#bigIcon:hover { background: transparent; color: $accent_hover; }
QPushButton#bigIcon:checked { background: transparent; color: $accent_hover; }
QPushButton::menu-indicator, QToolButton::menu-indicator { image: none; width: 0; }

QTreeWidget#sidebar { background: $surface; border: none; outline: 0; padding: 10px 6px; }
QTreeWidget#sidebar::item { padding: 7px 10px; border-radius: 8px; margin: 1px 4px; }
QTreeWidget#sidebar::item:hover { background: $surface2; }
QTreeWidget#sidebar::item:selected { background: $accent_dark; color: white; }

QListView#grid { background: transparent; border: none; outline: 0; }

QListWidget { background: $surface; border: 1px solid $border; border-radius: 10px; outline: 0; padding: 4px; }
QListWidget::item { padding: 8px; border-radius: 8px; }
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

QMenu { background: $surface2; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 24px; border-radius: 6px; }
QMenu::item:selected { background: $accent_dark; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }

QProgressBar { background: $surface2; border: none; border-radius: 4px; max-height: 8px; text-align: center; }
QProgressBar::chunk { background: $accent; border-radius: 4px; }
QStatusBar { background: $surface; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid $border; background: $surface; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }

QFrame#infobar { background: $accent_dark; border-radius: 10px; }
QLabel#muted { color: $muted; }
QLabel#heading { font-size: 20pt; font-weight: 700; }
QLabel#movieTitle { font-size: 24pt; font-weight: 800; }
QLabel#welcomeTitle { font-size: 34pt; font-weight: 800; }
QLabel#section { color: $muted; font-weight: 700; font-size: 9pt; }
QLabel#rating { color: #ffd25e; font-weight: 700; font-size: 12pt; }
QLabel#warn { color: $warn; }
a { color: $accent_hover; }
""")


def stylesheet() -> str:
    return _QSS.safe_substitute(COLORS)


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
    palette.setColor(QPalette.HighlightedText, QColor("white"))
    palette.setColor(QPalette.PlaceholderText, c["muted"])
    palette.setColor(QPalette.Link, c["accent_hover"])
    app.setPalette(palette)
    font = QFont(app.font())
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
