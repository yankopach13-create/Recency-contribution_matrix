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

from src.load_base import get_last_purchase_table
from src.recency_contribution import (
    contribution_from_base,
    contribution_from_upload,
    contribution_tables_from_upload,
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
                                for metric_name, df_metric in tables.items():
                                    if df_metric.empty:
                                        continue
                                    display = df_metric.copy()
                                    display.columns = ["Месяц", "Вклад (абс)", "Вклад %"]
                                    st.subheader(metric_name)
                                    st.dataframe(display, use_container_width=True)
                                    fig = px.pie(
                                        df_metric,
                                        values="value",
                                        names="month_label",
                                        title=f"Вклад по реценси — {metric_name}",
                                    )
                                    fig.update_traces(textposition="inside", textinfo="percent+label")
                                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Загрузите файл с колонками: Группа1, Продажи, Количество чеков, Количество товар, Код клиента."
        )
