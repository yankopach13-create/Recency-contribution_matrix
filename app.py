"""
Recency Contribution Matrix — Streamlit.
Режим «только base»: круговая по реценси из базы (клиенты или единицы).
Режим «база + загрузка»: загрузка файла с выручкой/штуками → круговая по реценси.
"""

from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px

from src.load_base import get_last_purchase_table
from src.recency_contribution import contribution_from_base, contribution_from_upload

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
    uploaded = st.file_uploader("Загрузите файл (Excel или CSV) с кодами клиентов и метрикой", type=["xlsx", "xls", "csv"])
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
            st.caption("Колонки в файле:")
            st.write(list(df_upload.columns))
            client_col = st.selectbox("Колонка с кодом клиента", options=df_upload.columns.tolist())
            value_col = st.selectbox("Колонка для вклада (выручка / штуки)", options=df_upload.columns.tolist())
            if st.button("Построить диаграмму по загрузке"):
                with st.spinner("Загружаю реценси из base и считаю вклад..."):
                    df_last = get_last_purchase_table(BASE_DIR)
                    if df_last.empty:
                        st.warning("База (base) пуста или не найдена. Сначала добавьте Excel-файлы в base.")
                    else:
                        df = contribution_from_upload(
                            df_upload,
                            df_last,
                            value_column=value_col,
                            client_code_column=client_col,
                        )
                        if df.empty:
                            st.warning("Нет пересечения кодов клиентов между загрузкой и базой.")
                        else:
                            st.dataframe(df, use_container_width=True)
                            fig = px.pie(
                                df,
                                values="value",
                                names="month_label",
                                title=f"Вклад по месяцу последней покупки ({value_col})",
                            )
                            fig.update_traces(textposition="inside", textinfo="percent+label")
                            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Загрузите файл с колонками: код клиента, выручка и/или продажи в шт.")
