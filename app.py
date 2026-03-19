"""
Recency Contribution Matrix — Streamlit.
Период вводится вручную (даты), категории из файлов окна (Группа1–3),
предыдущая покупка — по всей истории base до начала периода.
"""

import html
import sys
import types
from datetime import date
import calendar
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))


def _ensure_project_src_package() -> None:
    """
    Регистрирует локальный каталог src/ как пакет `src`.

    На Streamlit Cloud и др. окружениях имя `src` иногда конфликтует с пакетом
    из site-packages; без явного __path__ импорт src.base_period падает.
    """
    src_dir = str(_ROOT / "src")
    pkg = types.ModuleType("src")
    pkg.__path__ = [src_dir]  # type: ignore[attr-defined]
    sys.modules["src"] = pkg


_ensure_project_src_package()

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

from src.base_period import (
    COL_CLIENT,
    COL_G1,
    COL_G2,
    COL_G3,
    available_date_bounds_from_base_filenames,
    available_period_from_base_filenames,
    filter_window_by_categories,
    load_window_dataframe,
    normalize_client_code,
    load_last_purchase_day_rows,
    scan_previous_purchase_dates,
    sorted_unique_non_empty,
    top_g2_last_purchase_day,
    validate_user_period_for_scan,
)
from date_segment_picker import render_date_segment_picker
from src.recency_contribution import (
    LABEL_NEW_CLIENTS,
    LABEL_NO_BONUS_CARD,
    contribution_tables_from_prev_purchase,
)

BASE_DIR = _ROOT / "base"


def _date_from_dmy_parts(dd_s, mm_s, yyyy_s) -> Optional[date]:
    """
    Календарная дата из полей ДД / ММ / ГГГГ.
    Несуществующие дни (35.06, 31.02), неверный месяц/год — None.
    """
    for x in (dd_s, mm_s, yyyy_s):
        if x is None or not str(x).strip():
            return None
    try:
        d, m, y = int(str(dd_s).strip()), int(str(mm_s).strip()), int(str(yyyy_s).strip())
    except ValueError:
        return None
    if not (1 <= m <= 12 and 1900 <= y <= 2100):
        return None
    last = calendar.monthrange(y, m)[1]
    if not (1 <= d <= last):
        return None
    return date(y, m, d)


def _prefill_after_date_error(
    picked: dict, _date_keys: tuple, clear: str
) -> dict:
    """
    clear: 'all' | 'start' | 'end' — стереть соответствующие поля, остальное из picked.
    """
    out = {k: str(picked.get(k, "") or "").strip() for k in _date_keys}
    if clear == "all":
        return {k: "" for k in _date_keys}
    if clear == "start":
        out["fd"] = out["fm"] = out["fy"] = ""
    elif clear == "end":
        out["td"] = out["tm"] = out["ty"] = ""
    return out


def _period_parse_error_message(picked: dict, _date_keys: tuple) -> str:
    """Сообщение, если не удалось разобрать начало или конец периода."""
    d0 = _date_from_dmy_parts(picked.get("fd"), picked.get("fm"), picked.get("fy"))
    d1 = _date_from_dmy_parts(picked.get("td"), picked.get("tm"), picked.get("ty"))
    if d0 is None and d1 is None:
        return "Проверьте **начало** и **конец** периода: заполните все поля корректными датами."
    if d0 is None:
        return "**Начало периода** — некорректная дата (проверьте день, месяц и год)."
    if d1 is None:
        return "**Конец периода** — некорректная дата (проверьте день, месяц и год)."
    return "Начало периода позже конца — исправьте даты."


def _fmt_num(x) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, float) and x == int(x):
        x = int(x)
    s = f"{x:,.2f}" if isinstance(x, float) and x != int(x) else f"{int(x):,}"
    return s.replace(",", " ")


def _table_html(data_rows: list[tuple], total_fmt: str) -> str:
    total_fmt = html.escape(total_fmt)
    cell_style = "padding: 8px 12px; border: 1px solid #ccc;"
    rows_html_parts = []
    for month, abs_val, pct in data_rows:
        rows_html_parts.append(
            f"<tr>"
            f'<td style="{cell_style}">{html.escape(month)}</td>'
            f'<td style="{cell_style} text-align: right;">{html.escape(abs_val)}</td>'
            f'<td style="{cell_style} text-align: right;">{html.escape(pct)}</td></tr>'
        )
    rows_html = "".join(rows_html_parts)
    sticky_row1 = "position: sticky; top: 0; z-index: 3; background-color: #e8e8e8; border-bottom: 1px solid #ccc;"
    sticky_row2 = "position: sticky; top: 46px; z-index: 2; background-color: #f5f5f5; border-bottom: 1px solid #ccc;"
    return f"""
<div style="height: 75vh; overflow-y: auto; overflow-x: hidden; border: 1px solid #ccc; border-bottom: 2px solid #ccc; box-sizing: border-box;">
<table class="contribution-table-wrap" style="
  width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 0.95rem;
">
  <colgroup>
    <col style="width: 33.33%">
    <col style="width: 33.33%">
    <col style="width: 33.34%">
  </colgroup>
  <tr style="font-weight: bold; color: #000; {sticky_row1}">
    <td style="{cell_style} text-align: center; color: #000; height: 46px; vertical-align: middle;">Итого</td>
    <td style="{cell_style} text-align: center; color: #000; vertical-align: middle;">{total_fmt}</td>
    <td style="{cell_style} text-align: center; color: #000; vertical-align: middle;">100 %</td>
  </tr>
  <tr style="color: #000; {sticky_row2}">
    <th style="{cell_style} text-align: center; color: #000; vertical-align: middle;">Группа по давности</th>
    <th style="{cell_style} text-align: center; color: #000; vertical-align: middle;">Вклад (ABC)</th>
    <th style="{cell_style} text-align: center; color: #000; vertical-align: middle;">Вклад %</th>
  </tr>
  <tbody>
    {rows_html}
  </tbody>
</table>
</div>
"""


def _copy_codes_block_html(text_to_copy: str, block_id: str) -> str:
    escaped = html.escape(text_to_copy)
    return f"""
<style>
#copy_btn_{block_id} {{ transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease; }}
#copy_btn_{block_id}:hover {{ background: #d8d8d8 !important; box-shadow: 0 2px 6px rgba(0,0,0,0.12); transform: scale(1.02); }}
</style>
<textarea id="codes_ta_{block_id}" style="position:absolute;left:-9999px;width:1px;height:1px;" readonly>{escaped}</textarea>
<div style="margin-top:2px;">
<button type="button" id="copy_btn_{block_id}" style="padding:8px 20px;cursor:pointer;font-size:0.95rem;min-width:280px;width:100%;box-sizing:border-box;background:#e8e8e8;border:1px solid #ccc;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);color:#333;">
  📋 Скопировать коды
</button>
</div>
<script>
(function() {{
  var ta = document.getElementById("codes_ta_{block_id}");
  var btn = document.getElementById("copy_btn_{block_id}");
  if (!ta || !btn) return;
  var defaultLabel = "📋 Скопировать коды";
  btn.onclick = function() {{
    var s = ta.value;
    function showOk() {{
      btn.innerHTML = "✓ Скопировано!";
      btn.style.background = "#d4edda";
      setTimeout(function() {{ btn.innerHTML = defaultLabel; btn.style.background = "#e8e8e8"; }}, 2000);
    }}
    function fallback() {{
      var t = document.createElement("textarea");
      t.value = s;
      t.style.position = "fixed";
      t.style.left = "-9999px";
      document.body.appendChild(t);
      t.focus();
      t.select();
      try {{ document.execCommand("copy"); }} finally {{ document.body.removeChild(t); }}
      showOk();
    }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(s).then(showOk).catch(fallback);
    }} else {{
      fallback();
    }}
  }};
}})();
</script>
"""


st.set_page_config(page_title="Recency Contribution", layout="wide")
st.markdown(
    """
    <style>
    button[kind="primary"] {
        background-color: #0d2847 !important;
        border: 1px solid #0d2847 !important;
        color: #fff !important;
    }
    button[kind="primary"]:hover {
        background-color: #164a7d !important;
        border-color: #164a7d !important;
        color: #fff !important;
    }
    button[kind="primary"]:focus { box-shadow: 0 0 0 2px #fff, 0 0 0 4px #0d2847 !important; }
    /* Внутренние отступы у рамок блоков */
    [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 1.25rem 1.5rem !important;
        border-radius: 10px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("⏳ Матрица вклада в период по давности предыдущей покупки")

_avail = available_period_from_base_filenames(BASE_DIR)
_bounds = available_date_bounds_from_base_filenames(BASE_DIR)
_today = date.today()

if _avail:
    _avail_esc = html.escape(_avail)
    st.markdown(
        f'<div style="font-size:1.9rem;line-height:1.4;margin:0.35rem 0 0.6rem 0;">'
        f"<strong>Доступный период для анализа:</strong> "
        f'<span style="color:#1e40af;font-weight:650;">{_avail_esc}</span></div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div style="font-size:1.9rem;line-height:1.4;margin:0.35rem 0 0.6rem 0;">'
        "<strong>Доступный период для анализа:</strong> "
        "<em>не определён по именам файлов</em> "
        "(в имени Excel укажите год и месяц, например <code>2024 январь.xlsx</code>)."
        "</div>",
        unsafe_allow_html=True,
    )

if _bounds is None:
    for _k in (
        "period_d_from",
        "period_d_to",
        "window_df",
        "window_d_from",
        "window_d_to",
        "contribution_tables",
        "upload_totals",
        "period_to_clients",
        "_date_picker_last_nonce",
        "_dsp_prefill",
        "_date_picker_error",
        "_period_scan_warns",
        "_prev_purchase_map",
        "_lp_cache_sig",
        "_lp_top_df",
    ):
        st.session_state.pop(_k, None)

if _bounds:
    _picker_bounds = {
        "ok": True,
        "min": _bounds[0].isoformat(),
        "max": _bounds[1].isoformat(),
        "today": _today.isoformat(),
    }
else:
    _picker_bounds = {
        "ok": False,
        "reason": (
            "Сканирование недоступно: в имени файлов base нет года и месяца "
            "(например, «2024 январь.xlsx»)."
        ),
    }

st.divider()
with st.container(border=True):
    _period_scan_warns_show = st.session_state.pop("_period_scan_warns", None)
    if _period_scan_warns_show:
        for _w in _period_scan_warns_show:
            st.caption(f"⚠ {_w}")
    st.subheader("Период анализа")
    _date_keys = ("fd", "fm", "fy", "td", "tm", "ty")
    _prefill = None
    # После ошибки валидации — показываем очищенные/частичные поля, а не последний успешный период
    if "_dsp_prefill" in st.session_state:
        _prefill = dict(st.session_state["_dsp_prefill"])
    elif st.session_state.get("period_d_from") and st.session_state.get("period_d_to"):
        _df0, _dt0 = st.session_state["period_d_from"], st.session_state["period_d_to"]
        _prefill = {
            "fd": str(_df0.day),
            "fm": str(_df0.month),
            "fy": str(_df0.year),
            "td": str(_dt0.day),
            "tm": str(_dt0.month),
            "ty": str(_dt0.year),
        }

    picked = render_date_segment_picker(
        key="date_segments",
        prefill=_prefill,
        tab_index=0,
        bounds=_picker_bounds,
    )

    if isinstance(picked, dict) and picked.get("_nonce") is not None:
        _nonce = picked["_nonce"]
        if _nonce != st.session_state.get("_date_picker_last_nonce"):
            st.session_state["_date_picker_last_nonce"] = _nonce
            _cerr = picked.get("_clientValidationError")
            if _cerr:
                st.session_state["_date_picker_error"] = str(_cerr)
                _clr = str(picked.get("_clearFields") or "all").lower()
                if _clr not in ("all", "start", "end"):
                    _clr = "all"
                st.session_state["_dsp_prefill"] = _prefill_after_date_error(
                    picked, _date_keys, _clr
                )
            else:
                d0 = _date_from_dmy_parts(picked.get("fd"), picked.get("fm"), picked.get("fy"))
                d1 = _date_from_dmy_parts(picked.get("td"), picked.get("tm"), picked.get("ty"))

            if not _cerr and (d0 is None or d1 is None):
                st.session_state["_date_picker_error"] = _period_parse_error_message(
                    picked, _date_keys
                )
                if d0 is None and d1 is None:
                    _clr = "all"
                elif d0 is None:
                    _clr = "start"
                else:
                    _clr = "end"
                st.session_state["_dsp_prefill"] = _prefill_after_date_error(
                    picked, _date_keys, _clr
                )
            elif not _cerr and d0 > d1:
                st.session_state["_date_picker_error"] = (
                    "Начало периода не может быть позже конца."
                )
                st.session_state["_dsp_prefill"] = _prefill_after_date_error(
                    picked, _date_keys, "start"
                )
            elif not _cerr:
                _vmsg = validate_user_period_for_scan(d0, d1, _bounds, _today)
                if _vmsg:
                    st.session_state["_date_picker_error"] = _vmsg
                    st.session_state["_dsp_prefill"] = _prefill_after_date_error(
                        picked, _date_keys, "all"
                    )
                else:
                    st.session_state.pop("_date_picker_error", None)
                    st.session_state["period_d_from"] = d0
                    st.session_state["period_d_to"] = d1
                    st.session_state.pop("_dsp_prefill", None)
                    with st.spinner("Читаю файлы, пересекающиеся с выбранными датами…"):
                        df_win, warns, _files_read = load_window_dataframe(BASE_DIR, d0, d1)
                    st.session_state.pop("contribution_tables", None)
                    st.session_state.pop("upload_totals", None)
                    st.session_state.pop("period_to_clients", None)
                    st.session_state.pop("_prev_purchase_map", None)
                    st.session_state.pop("_lp_rows_all", None)
                    if df_win.empty:
                        st.session_state.pop("window_df", None)
                        st.session_state.pop("window_d_from", None)
                        st.session_state.pop("window_d_to", None)
                        st.warning(
                            "Нет строк в выбранном периоде. Проверьте даты и формат файлов "
                            "(нужны колонки: Группа1–3, Дата, Продажи, Количество чеков, "
                            "Количество товар, Код клиента)."
                        )
                    else:
                        st.session_state["window_df"] = df_win
                        st.session_state["window_d_from"] = d0
                        st.session_state["window_d_to"] = d1
                    if warns:
                        st.session_state["_period_scan_warns"] = list(warns)
                    else:
                        st.session_state.pop("_period_scan_warns", None)
                    st.rerun()

    if st.session_state.get("_date_picker_error"):
        st.error(st.session_state["_date_picker_error"], icon="⚠️")

    d_from = st.session_state.get("period_d_from")
    d_to = st.session_state.get("period_d_to")

    if "window_df" not in st.session_state or st.session_state["window_df"].empty:
        st.stop()

    df_cat = st.session_state["window_df"]

    st.markdown(
        '<div style="height:1px;background:linear-gradient(90deg,transparent,#b8c5d6,transparent);'
        'margin:1.1rem 0 0.85rem 0;"></div>',
        unsafe_allow_html=True,
    )
    st.subheader("Отбор товаров для анализа")
    opts_g1 = sorted_unique_non_empty(df_cat[COL_G1])
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        sel1 = st.multiselect(
            "Группа1",
            options=opts_g1,
            default=[],
            key="msel_g1",
            placeholder="Все",
        )
    with col_b:
        df_g1 = df_cat if not sel1 else df_cat[df_cat[COL_G1].isin(sel1)]
        opts_g2 = sorted_unique_non_empty(df_g1[COL_G2])
        sel2 = st.multiselect(
            "Группа2",
            options=opts_g2,
            default=[],
            key="msel_g2",
            placeholder="Все",
        )
    with col_c:
        df_g2 = df_g1 if not sel2 else df_g1[df_g1[COL_G2].isin(sel2)]
        opts_g3 = sorted_unique_non_empty(df_g2[COL_G3])
        sel3 = st.multiselect(
            "Группа3",
            options=opts_g3,
            default=[],
            key="msel_g3",
            placeholder="Все",
        )

    g1_f = sel1 if sel1 else None
    g2_f = sel2 if sel2 else None
    g3_f = sel3 if sel3 else None

    if st.button(
        "Применить все фильтры для анализа", type="primary", key="btn_apply_filters"
    ):
        st.session_state.pop("_lp_rows_all", None)
        df_work = filter_window_by_categories(df_cat, g1_f, g2_f, g3_f)
        mask_win = (
            pd.to_datetime(df_work["Дата"], errors="coerce").dt.date >= d_from
        ) & (pd.to_datetime(df_work["Дата"], errors="coerce").dt.date <= d_to)
        df_work = df_work.loc[mask_win].copy()
        if df_work.empty:
            st.warning(
                "После фильтра по датам и отбору товаров нет строк. "
                "Измените период или отбор."
            )
            st.stop()
        df_work["_client_norm"] = df_work[COL_CLIENT].map(normalize_client_code)
        clients_set = set(df_work["_client_norm"].dropna().astype(str))

        progress = st.progress(0)
        status = st.empty()

        def _cb(cur: int, total: int, name: str):
            progress.progress(cur / max(total, 1))
            status.caption(f"Скан истории: файл **{cur}/{total}** — `{name}`")

        with st.spinner("Ищу предыдущие покупки по всей base…"):
            prev_map = scan_previous_purchase_dates(
                BASE_DIR, clients_set, d_from, progress=_cb
            )
        progress.empty()
        status.empty()

        tables, period_to_clients = contribution_tables_from_prev_purchase(
            df_work, prev_map, analysis_start=d_from
        )
        upload_totals = {
            "Продажи": float(df_work["Продажи"].sum()),
            "Чеки": float(df_work["Количество чеков"].sum()),
            "Товар в шт.": float(df_work["Количество товар"].sum()),
            "Клиенты": int(df_work[COL_CLIENT].nunique()),
        }
        st.session_state["contribution_tables"] = tables
        st.session_state["upload_totals"] = upload_totals
        st.session_state["period_to_clients"] = period_to_clients
        st.session_state["_prev_purchase_map"] = {
            str(k): pd.Timestamp(v) for k, v in prev_map.items()
        }
        all_segment_clients: set[str] = set()
        for seg, raw_codes in period_to_clients.items():
            if seg == LABEL_NEW_CLIENTS:
                continue
            for code in raw_codes:
                norm = normalize_client_code(code)
                if norm:
                    all_segment_clients.add(str(norm))
        clients_with_prev = {
            c for c in all_segment_clients if c in st.session_state["_prev_purchase_map"]
        }
        if clients_with_prev:
            with st.spinner("Готовлю блок «Анализ последней покупки»…"):
                st.session_state["_lp_rows_all"] = load_last_purchase_day_rows(
                    BASE_DIR,
                    clients_with_prev,
                    st.session_state["_prev_purchase_map"],
                    d_from,
                )
        else:
            st.session_state["_lp_rows_all"] = pd.DataFrame()

if "contribution_tables" not in st.session_state:
    st.stop()

st.divider()
st.subheader("Результаты анализа")

tables = st.session_state["contribution_tables"]
upload_totals = st.session_state["upload_totals"]
period_to_clients = st.session_state["period_to_clients"]
_d0 = st.session_state.get("period_d_from")
_d1 = st.session_state.get("period_d_to")

with st.container(border=True):
    if _d0 and _d1:
        _range_s = html.escape(
            f"{_d0.strftime('%d.%m.%Y')} — {_d1.strftime('%d.%m.%Y')}"
        )
        st.markdown(
            f'<div style="font-size:1.35rem;line-height:1.4;margin:0 0 0.65rem 0;">'
            f"<strong>Анализируемый период:</strong> "
            f'<span style="color:#1e40af;font-weight:600;">{_range_s}</span></div>',
            unsafe_allow_html=True,
        )

    tab_names = ["Вклад в выручку", "Вклад в чеки", "Вклад в товар", "Вклад клиентов"]
    metric_keys = ["Продажи", "Чеки", "Товар в шт.", "Клиенты"]
    tabs = st.tabs(tab_names)
    for _tab_idx, (tab, metric_key) in enumerate(zip(tabs, metric_keys)):
        df_metric = tables.get(metric_key)
        if df_metric is None or df_metric.empty:
            with tab:
                st.info("Нет данных по этой метрике.")
            continue
        with tab:
            col_table, col_chart = st.columns([1, 1.4])
            with col_table:
                total_value = df_metric["value"].sum()
                total_fmt = _fmt_num(total_value)
                data_df = df_metric.copy()
                data_df["pct"] = data_df["pct"].apply(lambda x: f"{x} %")
                data_df["value_fmt"] = data_df["value"].apply(_fmt_num)
                data_rows = [
                    (str(row["month_label"]), row["value_fmt"], row["pct"])
                    for _, row in data_df.iterrows()
                ]
                st.markdown(_table_html(data_rows, total_fmt), unsafe_allow_html=True)
            with col_chart:
                fig = go.Figure(
                    data=[
                        go.Pie(
                            labels=df_metric["month_label"],
                            values=df_metric["value"],
                            hole=0.6,
                            textinfo="label+percent",
                            textposition="inside",
                            insidetextorientation="radial",
                            showlegend=False,
                            textfont=dict(size=12),
                            automargin=True,
                        )
                    ]
                )
                total_str = _fmt_num(upload_totals[metric_key])
                fig.add_annotation(
                    text=total_str,
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=24, color="gray"),
                )
                fig.update_layout(
                    height=500,
                    margin=dict(t=20, b=20, l=20, r=20),
                    uniformtext=dict(minsize=10, mode="hide"),
                )
                st.plotly_chart(
                    fig, use_container_width=True, key=f"plotly_pie_{_tab_idx}"
                )
            st.markdown("---")
            st.subheader("👥 Коды клиентов")
            month_options = [
                str(m) for m in df_metric["month_label"] if str(m) != LABEL_NO_BONUS_CARD
            ]
            if month_options:
                st.caption("Выберите группу по давности для копирования кодов")
                col_sel, _ = st.columns([1, 3])
                with col_sel:
                    sel_key = f"month_sel_{metric_key.replace(' ', '_').replace('.', '_')}"
                    selected_month = st.selectbox(
                        "Период",
                        options=month_options,
                        key=sel_key,
                        label_visibility="collapsed",
                    )
                    codes = period_to_clients.get(selected_month, [])

                    def _fmt_code(c):
                        try:
                            f = float(c)
                            return str(int(f)) if f == int(f) else str(c)
                        except (ValueError, TypeError):
                            return str(c)

                    text_to_copy = "\n".join(_fmt_code(c) for c in codes)
                    components.html(
                        _copy_codes_block_html(text_to_copy, sel_key), height=52
                    )
            else:
                st.caption("Нет периодов для выбора кодов (кроме «Клиенты без БК»).")

    st.markdown("---")
    st.subheader("🛒 Анализ предыдущей покупки")
    _seg_opts = sorted(
        k
        for k in period_to_clients
        if k != LABEL_NEW_CLIENTS and period_to_clients.get(k)
    )
    if not _seg_opts:
        st.info("Нет сегментов для анализа (кроме «Новых клиентов»).")
    elif "_prev_purchase_map" not in st.session_state:
        st.warning("Нажмите **Применить все фильтры для анализа** заново, чтобы загрузить данные.")
    elif "_lp_rows_all" not in st.session_state:
        st.warning("Нажмите **Применить все фильтры для анализа** заново, чтобы подготовить блок.")
    else:
        _lp_sel = st.multiselect(
            "Отберите группы по давности предыдущей покупки",
            options=_seg_opts,
            default=[],
            key="msel_last_purchase_segments",
            placeholder="Выберите один или несколько сегментов",
        )
        if not _lp_sel:
            st.info("Выберите хотя бы один сегмент реценси.")
        else:
            _clients_u: set = set()
            for _seg in _lp_sel:
                for _c in period_to_clients.get(_seg, []):
                    _nc = normalize_client_code(_c)
                    if _nc:
                        _clients_u.add(str(_nc))
            _pm_raw = st.session_state["_prev_purchase_map"]
            _pm = {
                str(k): pd.Timestamp(v) if not isinstance(v, pd.Timestamp) else v
                for k, v in _pm_raw.items()
            }
            _clients_prev = {c for c in _clients_u if c in _pm}
            _n_den = len(_clients_prev)
            if _n_den == 0:
                st.warning("У выбранных клиентов нет даты предыдущей покупки в данных.")
            else:
                st.markdown(
                    '<div style="font-size:2rem;line-height:1.3;margin:0.1rem 0 0.55rem 0;">'
                    '<span style="color:#000;">Клиентов в выбранных группах: </span>'
                    f'<span style="color:#1e40af;font-weight:700;">{_n_den}</span>'
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div style="text-align:center;font-size:1.2rem;line-height:1.3;'
                    'font-weight:700;color:#111;margin:0.15rem 0 0.55rem 0;">'
                    "Топ 10 продуктов предыдущих покупок"
                    "</div>",
                    unsafe_allow_html=True,
                )
                _raw_lp_all = st.session_state.get("_lp_rows_all")
                if isinstance(_raw_lp_all, pd.DataFrame) and not _raw_lp_all.empty:
                    _raw_lp = _raw_lp_all[_raw_lp_all["_cc"].isin(_clients_prev)]
                else:
                    _raw_lp = pd.DataFrame()
                _top_lp = top_g2_last_purchase_day(_raw_lp, _n_den, top_n=10)

                if _top_lp.empty:
                    st.warning("Нет строк за последний день покупки в base.")
                else:
                    _top_lp_show = _top_lp.copy()
                    if "% клиентов" in _top_lp_show.columns:
                        _top_lp_show["% клиентов"] = (
                            _top_lp_show["% клиентов"]
                            .map(lambda x: f"{float(x):.1f} %")
                        )
                    st.dataframe(
                        _top_lp_show,
                        use_container_width=True,
                        hide_index=True,
                    )
