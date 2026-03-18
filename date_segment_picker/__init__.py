"""
Кастомный компонент Streamlit: ввод дат с автопереходом, значение через setComponentValue.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import streamlit.components.v1 as components

_dir = os.path.dirname(os.path.abspath(__file__))
_frontend = os.path.join(_dir, "frontend")

date_segment_picker = components.declare_component("date_segment_picker", path=_frontend)


def render_date_segment_picker(
    *,
    key: str,
    prefill: Optional[Dict[str, str]] = None,
    tab_index: int = 0,
    bounds: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    После «Сканировать выбранный период» возвращает dict: fd, fm, fy, td, tm, ty, _nonce.
    bounds: ok, min/max/today (ISO) при ok=True; иначе ok=False, reason.
    """
    return date_segment_picker(
        key=key,
        prefill=prefill or {},
        bounds=bounds or {"ok": False, "reason": "Нет данных для границ периода."},
        default=None,
        tab_index=tab_index,
    )
