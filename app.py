"""
Recency Contribution Matrix — Streamlit.
Режим «только base»: круговая по реценси из базы (клиенты или единицы).
Режим «база + загрузка»: загрузка файла с выручкой/штуками → круговая по реценси.
"""

import html
import sys
from pathlib import Path

# Чтобы импорт src работал при запуске из корня репозитория (Streamlit Cloud и др.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go

from src.load_base import get_last_purchase_table
from src.recency_contribution import (
    CATEGORY_COLUMNS,
    LABEL_NO_BONUS_CARD,
    contribution_from_base,
    contribution_from_upload,
    contribution_tables_from_upload,
    normalize_upload_columns,
    UPLOAD_REQUIRED_COLUMNS,
    _filter_by_categories,
)

BASE_DIR = Path(__file__).resolve().parent / "base"


def _fmt_num(x) -> str:
    """Форматирует число с пробелом в качестве разделителя тысяч: 3658837.22 → 3 658 837.22"""
    if pd.isna(x):
        return ""
    if isinstance(x, float) and x == int(x):
        x = int(x)
    s = f"{x:,.2f}" if isinstance(x, float) and x != int(x) else f"{int(x):,}"
    return s.replace(",", " ")


def _table_html(data_rows: list[tuple], total_fmt: str) -> str:
    """Таблица на 3 столбца: Месяц, Вклад (ABC), Вклад %. Закреплённые Итого и заголовки."""
    total_fmt = html.escape(total_fmt)
    cell_style = "padding: 8px 12px; border: 1px solid #ccc;"
    rows_html_parts = []
    for month, abs_val, pct in data_rows:
        rows_html_parts.append(
            f'<tr>'
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
    <th style="{cell_style} text-align: center; color: #000; vertical-align: middle;">Месяц</th>
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
    """HTML: скрытый textarea с текстом и кнопка «Скопировать коды» (Clipboard API + fallback)."""
    escaped = html.escape(text_to_copy)
    return f'''
<textarea id="codes_ta_{block_id}" style="position:absolute;left:-9999px;width:1px;height:1px;" readonly>{escaped}</textarea>
<button type="button" id="copy_btn_{block_id}" style="padding:6px 14px;cursor:pointer;font-size:0.95rem;">
  Скопировать коды
</button>
<script>
(function() {{
  var ta = document.getElementById("codes_ta_{block_id}");
  var btn = document.getElementById("copy_btn_{block_id}");
  if (!ta || !btn) return;
  btn.onclick = function() {{
    var s = ta.value;
    function showOk() {{
      btn.textContent = "✓ Скопировано!";
      btn.style.background = "#d4edda";
      setTimeout(function() {{ btn.textContent = "Скопировать коды"; btn.style.background = ""; }}, 2000);
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
'''


st.set_page_config(page_title="Recency Contribution", layout="wide")
st.title("Вклад по реценси (месяц последней покупки)")

use_upload = st.radio(
    "Режим",
    ["Только база (base)", "База + загружаемый документ"],
    horizontal=True,
)

if use_upload == "Только база (base)":
    metric = st.selectbox(
        "Метрика для круговой диаграммы",
        ["clients", "units"],
        format_func=lambda x: "Число клиентов" if x == "clients" else "Сумма «Клиентов» (единицы)",
    )
    if st.button("Сканировать базу и построить диаграмму"):
        with st.spinner("Сканирую base..."):
            df = contribution_from_base(base_dir=BASE_DIR, metric=metric)
        if df.empty:
            st.warning("Нет данных в папке base или не найден ожидаемый формат Excel.")
        else:
            st.dataframe(df, use_container_width=True)
            fig = px.pie(
                df,
                values="value",
                names="month_label",
                title="Вклад по месяцу последней покупки",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

else:
    uploaded = st.file_uploader(
        "Загрузите файл (Excel или CSV) с колонками: Группа1, Продажи, Количество чеков, Количество товар, Код клиента",
        type=["xlsx", "xls", "csv"],
    )
    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                df_upload = pd.read_csv(uploaded)
            else:
                df_upload = pd.read_excel(uploaded, engine="openpyxl")
        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")
            df_upload = None
        else:
            df_upload = normalize_upload_columns(df_upload)
            missing = [c for c in UPLOAD_REQUIRED_COLUMNS if c not in df_upload.columns]
            if missing:
                st.error(f"В файле не хватает колонок: {missing}. Ожидаются: {UPLOAD_REQUIRED_COLUMNS}")
            else:
                category_cols_present = [c for c in CATEGORY_COLUMNS if c in df_upload.columns]
                category_options = []
                for col in category_cols_present:
                    category_options.extend(df_upload[col].dropna().astype(str).str.strip().unique().tolist())
                category_options = sorted(set(category_options))
                selected_categories = st.multiselect(
                    "Строить по категориям (Группа1/2/3/4, Товар). Пусто — по всем.",
                    options=category_options,
                    default=[],
                    key="report_categories",
                )
                category_filter = selected_categories if selected_categories else None

                if st.button("Построить диаграммы"):
                    with st.spinner("Загружаю реценси из base и считаю вклад по 4 метрикам..."):
                        df_last = get_last_purchase_table(BASE_DIR)
                        if df_last.empty:
                            st.warning("База (base) пуста или не найдена. Сначала добавьте Excel-файлы в base.")
                        else:
                            tables, period_to_clients = contribution_tables_from_upload(
                                df_upload,
                                df_last,
                                category_filter=category_filter,
                            )
                            has_data = any(not t.empty for t in tables.values())
                            if not has_data:
                                st.warning("Нет пересечения кодов клиентов между загрузкой и базой.")
                            else:
                                work = _filter_by_categories(df_upload, selected_categories) if selected_categories else df_upload
                                upload_totals = {
                                    "Продажи": float(work["Продажи"].sum()),
                                    "Чеки": float(work["Количество чеков"].sum()),
                                    "Товар в шт.": float(work["Количество товар"].sum()),
                                    "Клиенты": int(work["Код клиента"].nunique()),
                                }
                                st.session_state["contribution_tables"] = tables
                                st.session_state["upload_totals"] = upload_totals
                                st.session_state["period_to_clients"] = period_to_clients

                if "contribution_tables" in st.session_state and "upload_totals" in st.session_state and "period_to_clients" in st.session_state:
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
                                table_markup = _table_html(data_rows, total_fmt)
                                st.markdown(table_markup, unsafe_allow_html=True)
                            with col_chart:
                                fig = go.Figure(data=[go.Pie(
                                    labels=df_metric["month_label"],
                                    values=df_metric["value"],
                                    hole=0.6,
                                    textinfo="label+percent",
                                    textposition="inside",
                                    insidetextorientation="radial",
                                    showlegend=False,
                                    textfont=dict(size=12),
                                    automargin=True,
                                )])
                                total_str = _fmt_num(upload_totals[metric_key])
                                fig.add_annotation(
                                    text=total_str,
                                    x=0.5, y=0.5, showarrow=False,
                                    font=dict(size=24, color="gray"),
                                )
                                fig.update_layout(
                                    height=500,
                                    margin=dict(t=20, b=20, l=20, r=20),
                                    uniformtext=dict(minsize=10, mode="hide"),
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            # Под таблицей и диаграммой: выбор месяца и копирование кодов
                            month_options = [
                                str(m) for m in df_metric["month_label"]
                                if str(m) != LABEL_NO_BONUS_CARD
                            ]
                            if month_options:
                                row_sel, row_copy = st.columns([1, 1])
                                with row_sel:
                                    sel_key = f"month_sel_{metric_key.replace(' ', '_').replace('.', '_')}"
                                    selected_month = st.selectbox(
                                        "Месяц",
                                        options=month_options,
                                        key=sel_key,
                                    )
                                with row_copy:
                                    codes = period_to_clients.get(selected_month, [])
                                    text_to_copy = "\n".join(str(c) for c in codes)
                                    block_id = sel_key
                                    copy_html = _copy_codes_block_html(text_to_copy, block_id)
                                    components.html(copy_html, height=50)
                            else:
                                st.caption("Нет периодов для выбора кодов (кроме «Клиенты без БК»).")
    else:
        st.info(
            "Загрузите файл с колонками: Группа1, Продажи, Количество чеков, Количество товар, Код клиента."
        )
