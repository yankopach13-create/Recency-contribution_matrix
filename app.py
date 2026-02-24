"""
Recency Contribution Matrix — Streamlit.
Режим «только base»: круговая по реценси из базы (клиенты или единицы).
Режим «база + загрузка»: загрузка файла с выручкой/штуками → круговая по реценси.
"""

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
                            tables = contribution_tables_from_upload(
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

                if "contribution_tables" in st.session_state and "upload_totals" in st.session_state:
                    tables = st.session_state["contribution_tables"]
                    upload_totals = st.session_state["upload_totals"]
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
                                display = df_metric.copy()
                                display["pct"] = display["pct"].apply(lambda x: f"{x} %")
                                display = display.rename(columns={"month_label": "Месяц", "value": "Вклад (абс)", "pct": "Вклад %"})
                                total_value = df_metric["value"].sum()
                                display = pd.concat([
                                    display[["Месяц", "Вклад (абс)", "Вклад %"]],
                                    pd.DataFrame([{"Месяц": "Итого", "Вклад (абс)": total_value, "Вклад %": "100 %"}])
                                ], ignore_index=True)
                                st.dataframe(display, use_container_width=True, hide_index=True)
                            with col_chart:
                                fig = go.Figure(data=[go.Pie(
                                    labels=df_metric["month_label"],
                                    values=df_metric["value"],
                                    hole=0.6,
                                    textinfo="label+percent",
                                    textposition="outside",
                                    showlegend=True,
                                    legend=dict(orientation="v", yanchor="middle", y=0.5, x=1.02),
                                )])
                                total_str = f"{upload_totals[metric_key]:,.0f}".replace(",", " ")
                                fig.add_annotation(
                                    text=total_str,
                                    x=0.5, y=0.5, showarrow=False,
                                    font=dict(size=24, color="gray"),
                                )
                                fig.update_layout(
                                    title=f"Вклад по реценси — {metric_key}",
                                    height=500,
                                    margin=dict(t=50, b=30, l=10, r=180),
                                )
                                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Загрузите файл с колонками: Группа1, Продажи, Количество чеков, Количество товар, Код клиента."
        )
