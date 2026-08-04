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
QMainWindow, QWidget#root {{ background-color: {COLORS['background']}; }}
QScrollArea {{ border: 0; background: transparent; }}
QFrame#sidebar, QFrame#panel, QFrame#headerPanel, QFrame#projectHero,
QFrame#previewPanel {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}
QFrame#projectHero {{ background-color: #101b25; }}
QFrame#queuePanel {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['gold']};
    border-radius: 12px;
}}
QLabel#brand {{
    color: {COLORS['gold']};
    font-family: "Georgia";
    font-size: 27px;
    font-weight: 700;
}}
QLabel#heroKicker {{ color: {COLORS['gold']}; font-size: 12px; font-weight: 700; }}
QLabel#pageTitle {{ color: {COLORS['gold']}; font-size: 21px; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: 15px; font-weight: 700; }}
QLabel#queueEmpty {{ color: {COLORS['muted']}; font-size: 13px; padding: 22px; }}
QLabel#muted {{ color: {COLORS['muted']}; }}
QLabel#metricValue {{ font-size: 24px; font-weight: 700; }}
QLabel#metricCaption {{ color: {COLORS['muted']}; font-size: 11px; }}
QLabel#fileName {{ color: {COLORS['text']}; font-weight: 600; }}
QLabel#activityText {{ color: {COLORS['text']}; line-height: 1.25; }}
QPushButton {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 10px;
}}
QPushButton:hover {{ background-color: {COLORS['surface_hover']}; border-color: {COLORS['gold_soft']}; }}
QPushButton:pressed {{ background-color: #0a131c; }}
QPushButton:disabled {{ color: #5f6d79; background-color: #0b141c; }}
QPushButton#primaryButton {{
    background-color: #123c2b;
    border-color: #267a56;
    color: #72e3a5;
    font-weight: 700;
}}
QPushButton#iconButton {{ min-width: 32px; max-width: 32px; min-height: 30px; max-height: 30px; padding: 0; }}
QPushButton#miniIconButton {{ min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; }}
QPushButton#navButton {{
    border: 0;
    border-radius: 9px;
    padding: 9px 12px;
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
    padding: 8px 10px;
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
QTableWidget::item {{ padding: 5px; }}
QHeaderView::section {{
    background-color: #0b151e;
    color: {COLORS['muted']};
    border: 0;
    border-bottom: 1px solid {COLORS['border']};
    padding: 6px;
    font-weight: 600;
}}
QTabWidget::pane {{ border: 0; border-top: 1px solid {COLORS['border']}; }}
QTabBar::tab {{
    background-color: #0a141d;
    color: {COLORS['muted']};
    border: 1px solid {COLORS['border']};
    border-bottom: 0;
    padding: 7px 14px;
    min-width: 125px;
}}
QTabBar::tab:selected {{ background-color: #13202b; color: {COLORS['gold']}; border-color: {COLORS['gold_soft']}; }}
QListWidget, QPlainTextEdit {{
    background-color: #09131b;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 5px;
}}
QListWidget::item {{ padding: 2px; border-bottom: 1px solid #13212c; }}
QProgressBar {{ background-color: #0a131b; border: 1px solid {COLORS['border']}; border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background-color: {COLORS['gold']}; border-radius: 5px; }}
QSplitter::handle {{ background-color: {COLORS['border']}; margin: 8px 1px; border-radius: 2px; }}
QSplitter::handle:hover {{ background-color: {COLORS['gold_soft']}; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #334554; min-height: 24px; border-radius: 4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; background: transparent; }}
QToolTip {{ background-color: #111d27; color: {COLORS['text']}; border: 1px solid {COLORS['border']}; }}
"""
