"""可插拔双后端 — uia（控件树主）+ vision（gpt-5.5 兜底）。"""

from app.backends.base import ControlBackend, PageState, Coord, Action
from app.backends.uia_backend import UiaBackend
from app.backends.vision_backend import VisionBackend

__all__ = [
    "ControlBackend",
    "PageState",
    "Coord",
    "Action",
    "UiaBackend",
    "VisionBackend",
]
