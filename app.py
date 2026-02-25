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
import plotly.express as px
import plotly.graph_objects as go

from src.load_base import get_last_purchase_table
from src.recency_contribution import (
    contribution_from_base,
    contribution_from_upload,
    contribution_tables_from_upload,
    normalize_upload_columns,
    UPLOAD_REQUIRED_COLUMNS,
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


def _table_html(data_rows: list[tuple], total_fmt: str, period_to_clients: dict) -> str:
    """Одна таблица: Итого, заголовки, данные; 4-й столбец — кнопка «Скопировать коды»; скролл по вертикали."""
    total_fmt = html.escape(total_fmt)
    cell_style = "padding: 8px 12px; border: 1px solid #ccc;"
    btn_style = "padding: 6px 10px; cursor: pointer; font-size: 0.85rem; white-space: nowrap;"
    rows_html_parts = []
    for month, abs_val, pct in data_rows:
        codes = period_to_clients.get(month, [])
        codes_attr = html.escape(",".join(str(c) for c in codes)) if codes else ""
        copy_btn = (
            f'<button type="button" style="{btn_style}" class="copy-codes-btn" '
            f'data-codes="{codes_attr}" onclick="var t=this.getAttribute(\'data-codes\'); '
            f'if(t) navigator.clipboard.writeText(t.replace(/,/g,\'\\n\'));">Скопировать</button>'
        )
        rows_html_parts.append(
            f'<tr>'
            f'<td style="{cell_style}">{html.escape(month)}</td>'
            f'<td style="{cell_style} text-align: right;">{html.escape(abs_val)}</td>'
            f'<td style="{cell_style} text-align: right;">{html.escape(pct)}</td>'
            f'<td style="{cell_style} text-align: center;">{copy_btn}</td></tr>'
        )
    rows_html = "".join(rows_html_parts)
    return f"""
<div style="height: 65vh; overflow-y: auto; overflow-x: hidden;">
<table class="contribution-table-wrap" style="
  width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 0.95rem;
">
  <colgroup>
    <col style="width: 25%">
    <col style="width: 25%">
    <col style="width: 25%">
    <col style="width: 25%">
  </colgroup>
  <tr style="font-weight: bold; background-color: #e8e8e8; color: #000;">
    <td style="{cell_style} text-align: center; color: #000;">Итого</td>
    <td style="{cell_style} text-align: center; color: #000;">{total_fmt}</td>
    <td style="{cell_style} text-align: center; color: #000;">100 %</td>
    <td style="{cell_style} text-align: center; color: #000;">—</td>
  </tr>
  <tr style="background-color: #f5f5f5; color: #000;">
    <th style="{cell_style} text-align: center; color: #000;">Месяц</th>
    <th style="{cell_style} text-align: center; color: #000;">Вклад (ABC)</th>
    <th style="{cell_style} text-align: center; color: #000;">Вклад %</th>
    <th style="{cell_style} text-align: center; color: #000;">Скопировать коды клиентов</th>
  </tr>
  <tbody>
    {rows_html}
  </tbody>
</table>
</div>
"""


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
                categories = ["По всем категориям"] + sorted(df_upload["Группа1"].dropna().astype(str).unique().tolist())
                choice = st.selectbox("Строить по категориям", options=categories)
                category_filter = None if choice == "По всем категориям" else choice

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
                                work = df_upload if category_filter is None else df_upload[df_upload["Группа1"].astype(str).str.strip() == str(category_filter).strip()]
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
                                table_markup = _table_html(data_rows, total_fmt, period_to_clients)
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
    else:
        st.info(
            "Загрузите файл с колонками: Группа1, Продажи, Количество чеков, Количество товар, Код клиента."
        )
