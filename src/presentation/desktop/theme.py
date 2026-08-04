from __future__ import annotations

COLORS = {
    "background": "#071019",
    "surface": "#0d1721",
    "surface_alt": "#111e29",
    "surface_hover": "#172633",
    "border": "#283746",
    "text": "#f2f5f7",
    "muted": "#98a8b7",
    "gold": "#e8ad35",
    "gold_soft": "#7b5b21",
    "green": "#39c477",
    "blue": "#3da7e6",
    "orange": "#ef8b36",
    "red": "#e65f5f",
}

APP_STYLESHEET = f"""
QWidget {{
    color: {COLORS['text']};
    background: transparent;
    font-family: "Segoe UI", "Tahoma", "Arial";
    font-size: 13px;
}}
QMainWindow, QWidget#root {{
    background-color: {COLORS['background']};
}}
QFrame#sidebar, QFrame#panel, QFrame#headerPanel, QFrame#heroPanel {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}
QFrame#heroPanel {{
    background-color: #101b25;
}}
QFrame#queuePanel {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['gold']};
    border-radius: 12px;
}}
QLabel#brand {{
    color: {COLORS['gold']};
    font-family: "Georgia";
    font-size: 28px;
    font-weight: 700;
}}
QLabel#pageTitle {{
    color: {COLORS['gold']};
    font-size: 24px;
    font-weight: 700;
}}
QLabel#sectionTitle {{
    font-size: 16px;
    font-weight: 700;
}}
QLabel#muted {{ color: {COLORS['muted']}; }}
QLabel#metricValue {{ font-size: 28px; font-weight: 700; }}
QLabel#metricCaption {{ color: {COLORS['muted']}; }}
QPushButton {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 9px 12px;
}}
QPushButton:hover {{
    background-color: {COLORS['surface_hover']};
    border-color: {COLORS['gold_soft']};
}}
QPushButton:pressed {{ background-color: #0a131c; }}
QPushButton:disabled {{ color: #5f6d79; background-color: #0b141c; }}
QPushButton#primaryButton {{
    background-color: #123c2b;
    border-color: #267a56;
    color: #72e3a5;
    font-weight: 700;
}}
QPushButton#navButton {{
    border: 0;
    border-radius: 9px;
    padding: 11px 14px;
    text-align: right;
    background-color: transparent;
}}
QPushButton#navButton:hover {{ background-color: {COLORS['surface_hover']}; }}
QPushButton#navButton[active="true"] {{
    background-color: #2a271d;
    color: {COLORS['gold']};
    border-left: 3px solid {COLORS['gold']};
}}
QLineEdit, QComboBox {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 9px 12px;
    selection-background-color: {COLORS['gold_soft']};
}}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QTableWidget {{
    background-color: transparent;
    alternate-background-color: #0b151e;
    border: 0;
    gridline-color: {COLORS['border']};
    selection-background-color: #17344a;
}}
QHeaderView::section {{
    background-color: #0b151e;
    color: {COLORS['muted']};
    border: 0;
    border-bottom: 1px solid {COLORS['border']};
    padding: 8px;
    font-weight: 600;
}}
QListWidget, QPlainTextEdit {{
    background-color: #09131b;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 6px;
}}
QListWidget::item {{ padding: 6px; }}
QProgressBar {{
    background-color: #0a131b;
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {COLORS['gold']};
    border-radius: 5px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #334554;
    min-height: 24px;
    border-radius: 5px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{
    background-color: #111d27;
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
}}
"""
