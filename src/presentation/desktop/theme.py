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
    font-size: 12px;
}}
QMainWindow, QWidget#root {{
    background-color: {COLORS['background']};
}}
QScrollArea {{
    border: 0;
    background: transparent;
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
QFrame#emptyState {{
    background-color: #09131b;
    border: 1px dashed {COLORS['border']};
    border-radius: 10px;
}}
QLabel#brand {{
    color: {COLORS['gold']};
    font-family: "Georgia";
    font-size: 28px;
    font-weight: 700;
}}
QLabel#pageTitle {{
    color: {COLORS['gold']};
    font-size: 23px;
    font-weight: 700;
}}
QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 700;
}}
QLabel#queueEmpty {{
    color: {COLORS['muted']};
    font-size: 14px;
    padding: 26px;
}}
QLabel#muted {{ color: {COLORS['muted']}; }}
QLabel#metricValue {{ font-size: 25px; font-weight: 700; }}
QLabel#metricCaption {{ color: {COLORS['muted']}; font-size: 11px; }}
QPushButton {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 11px;
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
QPushButton#iconButton {{
    min-width: 34px;
    max-width: 34px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
}}
QPushButton#navButton {{
    border: 0;
    border-radius: 9px;
    padding: 10px 13px;
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
    padding: 8px 11px;
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
QTableWidget::item {{ padding: 6px; }}
QHeaderView::section {{
    background-color: #0b151e;
    color: {COLORS['muted']};
    border: 0;
    border-bottom: 1px solid {COLORS['border']};
    padding: 7px;
    font-weight: 600;
}}
QTabWidget::pane {{
    border: 0;
    border-top: 1px solid {COLORS['border']};
}}
QTabBar::tab {{
    background-color: #0a141d;
    color: {COLORS['muted']};
    border: 1px solid {COLORS['border']};
    border-bottom: 0;
    padding: 8px 16px;
    min-width: 130px;
}}
QTabBar::tab:selected {{
    background-color: #13202b;
    color: {COLORS['gold']};
    border-color: {COLORS['gold_soft']};
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
QSplitter::handle {{
    background-color: {COLORS['border']};
    margin: 8px 1px;
    border-radius: 2px;
}}
QSplitter::handle:hover {{ background-color: {COLORS['gold_soft']}; }}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #334554;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; background: transparent; }}
QToolTip {{
    background-color: #111d27;
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
}}
"""
