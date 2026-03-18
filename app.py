"""
Recency Contribution Matrix — Streamlit.
Период вводится вручную (даты), категории из файлов окна (Группа1–3),
предыдущая покупка — по всей истории base до начала периода.
"""

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

from src.base_period import (
    COL_CLIENT,
    COL_G1,
    COL_G2,
    COL_G3,
    available_period_from_base_filenames,
    filter_window_by_categories,
    load_window_dataframe,
    normalize_client_code,
    scan_previous_purchase_dates,
    sorted_unique_non_empty,
)
from src.recency_contribution import (
    LABEL_NO_BONUS_CARD,
    contribution_tables_from_prev_purchase,
)

BASE_DIR = Path(__file__).resolve().parent / "base"


def _parse_date_text(s: str):
    """Парсинг даты: ДД.ММ.ГГГГ (и похожие форматы, dayfirst)."""
    if s is None or not str(s).strip():
        return None
    ts = pd.to_datetime(str(s).strip(), dayfirst=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


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
    <th style="{cell_style} text-align: center; color: #000; vertical-align: middle;">Период реценси</th>
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
st.title("⏳ Матрица вклада в период по давности предыдущей покупки")

_avail = available_period_from_base_filenames(BASE_DIR)
if _avail:
    st.markdown(f"**Доступный период для анализа:** {_avail}")
else:
    st.markdown(
        "**Доступный период для анализа:** *не определён по именам файлов* "
        "(в имени Excel укажите год и месяц, например `2024 январь.xlsx`)."
    )

st.caption("Формат дат: **ДД.ММ.ГГГГ** (например, 01.04.2024).")
col_d1, col_d2 = st.columns(2)
with col_d1:
    t_from = st.text_input("Начало периода анализа", key="txt_d_from", placeholder="ДД.ММ.ГГГГ")
with col_d2:
    t_to = st.text_input("Конец периода анализа", key="txt_d_to", placeholder="ДД.ММ.ГГГГ")

d_from = _parse_date_text(t_from)
d_to = _parse_date_text(t_to)
if d_from is None or d_to is None:
    st.info("Укажите дату начала и дату конца периода.")
    st.stop()
if d_from > d_to:
    st.error("Начало периода не может быть позже конца. Проверьте ввод.")
    st.stop()

if st.button("Сканировать выбранный период", type="secondary"):
    with st.spinner("Читаю файлы, пересекающиеся с выбранными датами…"):
        df_win, warns, files_read = load_window_dataframe(BASE_DIR, d_from, d_to)
    st.session_state.pop("contribution_tables", None)
    st.session_state.pop("upload_totals", None)
    st.session_state.pop("period_to_clients", None)
    if df_win.empty:
        st.session_state.pop("window_df", None)
        st.session_state.pop("window_d_from", None)
        st.session_state.pop("window_d_to", None)
        st.warning(
            "Нет строк в выбранном периоде. Проверьте даты и формат файлов "
            "(нужны колонки: Группа1–3, Дата, Продажи, Количество чеков, Количество товар, Код клиента)."
        )
    else:
        st.session_state["window_df"] = df_win
        st.session_state["window_d_from"] = d_from
        st.session_state["window_d_to"] = d_to
    for w in warns:
        st.caption(f"⚠ {w}")

if "window_df" in st.session_state:
    if (
        st.session_state.get("window_d_from") != d_from
        or st.session_state.get("window_d_to") != d_to
    ):
        st.warning("Даты периода изменились — нажмите **Сканировать выбранный период** снова.")

if "window_df" not in st.session_state or st.session_state["window_df"].empty:
    st.stop()

df_cat = st.session_state["window_df"]
if st.session_state.get("window_d_from") != d_from or st.session_state.get("window_d_to") != d_to:
    st.stop()

st.subheader("Категории")
ALL = "(все)"

opts_g1 = [ALL] + sorted_unique_non_empty(df_cat[COL_G1])
sel1 = st.selectbox("Группа1", options=opts_g1, key="sel_g1")
df_g1 = df_cat if sel1 == ALL else df_cat[df_cat[COL_G1] == sel1]
opts_g2 = [ALL] + sorted_unique_non_empty(df_g1[COL_G2])
sel2 = st.selectbox("Группа2", options=opts_g2, key="sel_g2")
df_g2 = df_g1 if sel2 == ALL else df_g1[df_g1[COL_G2] == sel2]
opts_g3 = [ALL] + sorted_unique_non_empty(df_g2[COL_G3])
sel3 = st.selectbox("Группа3", options=opts_g3, key="sel_g3")

g1_f = None if sel1 == ALL else sel1
g2_f = None if sel2 == ALL else sel2
g3_f = None if sel3 == ALL else sel3

if st.button("Посчитать", type="primary"):
    df_work = filter_window_by_categories(df_cat, g1_f, g2_f, g3_f)
    mask_win = (
        pd.to_datetime(df_work["Дата"], errors="coerce").dt.date >= d_from
    ) & (pd.to_datetime(df_work["Дата"], errors="coerce").dt.date <= d_to)
    df_work = df_work.loc[mask_win].copy()
    if df_work.empty:
        st.warning("После фильтра по датам и категориям нет строк. Измените период или категории.")
        st.stop()
    df_work["_client_norm"] = df_work[COL_CLIENT].map(normalize_client_code)
    clients_set = set(df_work["_client_norm"].dropna().astype(str))

    progress = st.progress(0)
    status = st.empty()

    def _cb(cur: int, total: int, name: str):
        progress.progress(cur / max(total, 1))
        status.caption(f"Скан истории: файл **{cur}/{total}** — `{name}`")

    with st.spinner("Ищу предыдущие покупки по всей base…"):
        prev_map = scan_previous_purchase_dates(BASE_DIR, clients_set, d_from, progress=_cb)
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

if "contribution_tables" not in st.session_state:
    st.stop()

tables = st.session_state["contribution_tables"]
upload_totals = st.session_state["upload_totals"]
period_to_clients = st.session_state["period_to_clients"]

tab_names = ["Вклад в выручку", "Вклад в чеки", "Вклад в товар", "Вклад клиентов"]
metric_keys = ["Продажи", "Чеки", "Товар в шт.", "Клиенты"]
tabs = st.tabs(tab_names)
for tab, metric_key in zip(tabs, metric_keys):
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
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("---")
        st.subheader("👥 Коды клиентов")
        month_options = [
            str(m) for m in df_metric["month_label"] if str(m) != LABEL_NO_BONUS_CARD
        ]
        if month_options:
            st.caption("Выберите группу (период реценси) для копирования кодов")
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
                components.html(_copy_codes_block_html(text_to_copy, sel_key), height=52)
        else:
            st.caption("Нет периодов для выбора кодов (кроме «Клиенты без БК»).")
