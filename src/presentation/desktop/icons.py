from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import COLORS


_PATHS = {
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "projects": '<path d="M3 6h7l2 2h9v11H3z"/><path d="M3 6V4h7l2 2"/>',
    "episodes": '<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/>',
    "storyboard": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16M15 4v16"/>',
    "visual": '<path d="M12 3 21 12 12 21 3 12z"/><circle cx="12" cy="12" r="3"/>',
    "video": '<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 9h18M7 5l2 4M13 5l2 4M18 5l2 4"/>',
    "approvals": '<path d="M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
    "reports": '<path d="M5 20V10M12 20V4M19 20v-7"/><path d="M3 20h18"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "refresh": '<path d="M20 6v5h-5"/><path d="M19 11a8 8 0 1 0 1 5"/>',
    "folder": '<path d="M3 6h7l2 2h9v11H3z"/>',
    "first": '<path d="M6 5v14M18 6l-8 6 8 6z"/>',
    "previous": '<path d="M16 6 8 12l8 6z"/>',
    "play": '<path d="m9 6 9 6-9 6z"/>',
    "next": '<path d="m8 6 8 6-8 6z"/>',
    "last": '<path d="M18 5v14M6 6l8 6-8 6z"/>',
    "open": '<path d="M4 5h7l2 2h7v12H4z"/><path d="m10 15 7-7M13 8h4v4"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
}


def _svg(body: str, color: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


@lru_cache(maxsize=128)
def icon(name: str, tone: str = "muted", size: int = 18) -> QIcon:
    body = _PATHS.get(name)
    if body is None:
        raise KeyError(f"UNKNOWN_DESKTOP_ICON:{name}")
    color = COLORS.get(tone, COLORS["muted"])
    renderer = QSvgRenderer(QByteArray(_svg(body, color).encode("utf-8")))
    pixel_size = max(12, int(size))
    pixmap = QPixmap(QSize(pixel_size, pixel_size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
