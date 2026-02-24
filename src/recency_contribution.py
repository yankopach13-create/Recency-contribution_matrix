"""
Расчёт вклада по реценси: группировка по месяцу последней покупки и доля (%). 
Режим «только base»: метрика — число клиентов или сумма «Клиентов».
Режим «base + загрузка»: метрика — выручка или штуки из загружаемого файла.
"""

from pathlib import Path
from typing import Dict, Literal, Optional

import pandas as pd

from .load_base import (
    COL_CLIENT_CODE,
    COL_CLIENTS,
    COL_GROUP,
    scan_base,
    build_last_purchase_per_client,
)

# Ожидаемые колонки в загружаемом документе (фиксированная структура)
UPLOAD_COL_SALES = "Продажи"
UPLOAD_COL_RECEIPTS = "Количество чеков"
UPLOAD_COL_ITEMS = "Количество товар"
UPLOAD_REQUIRED_COLUMNS = [COL_GROUP, UPLOAD_COL_SALES, UPLOAD_COL_RECEIPTS, UPLOAD_COL_ITEMS, COL_CLIENT_CODE]

# Имена месяцев для подписи на диаграмме (русская локаль)
MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _add_recency_month(df: pd.DataFrame, date_col: str = "last_purchase_date") -> pd.DataFrame:
    """Добавляет колонки year_month (YYYY-MM) и month_label (например «Январь 2024»)."""
    out = df.copy()
    out["year_month"] = out[date_col].dt.to_period("M").astype(str)
    out["month_label"] = (
        out[date_col].dt.month.map(MONTH_NAMES) + " " + out[date_col].dt.year.astype(str)
    )
    return out


def contribution_from_base(
    base_dir: Optional[Path] = None,
    metric: Literal["clients", "units"] = "clients",
) -> pd.DataFrame:
    """
    Режим «только base»: сканирует base, считает вклад по месяцам реценси.
    - clients: доля уникальных клиентов по месяцу последней покупки.
    - units: доля суммы колонки «Клиентов» по месяцу последней покупки.
    Возвращает DataFrame: month_label, value, pct.
    """
    df_base = scan_base(base_dir)
    if df_base.empty:
        return pd.DataFrame(columns=["month_label", "value", "pct"])

    df_last = build_last_purchase_per_client(df_base)
    if df_last.empty:
        return pd.DataFrame(columns=["month_label", "value", "pct"])

    df_last = _add_recency_month(df_last)

    if metric == "clients":
        by_month = df_last.groupby("month_label", as_index=False).size()
        by_month.columns = ["month_label", "value"]
    else:
        # units: каждой строке base приписываем месяц последней покупки клиента, затем суммируем «Клиентов»
        merged = df_base[[COL_CLIENT_CODE, COL_CLIENTS]].merge(
            df_last[[COL_CLIENT_CODE, "month_label"]],
            on=COL_CLIENT_CODE,
            how="left",
        )
        merged = merged.dropna(subset=["month_label"])
        by_month = merged.groupby("month_label", as_index=False)[COL_CLIENTS].sum()
        by_month.columns = ["month_label", "value"]

    total = by_month["value"].sum()
    by_month["pct"] = (by_month["value"] / total * 100).round(1) if total else 0
    return by_month.sort_values("value", ascending=False).reset_index(drop=True)


def contribution_from_upload(
    df_upload: pd.DataFrame,
    df_last_purchase: pd.DataFrame,
    value_column: str,
    client_code_column: str = COL_CLIENT_CODE,
) -> pd.DataFrame:
    """
    Режим «base + загрузка»: джойн загружаемых данных с реценси по коду клиента,
    агрегация по месяцу последней покупки по выбранной колонке (выручка/штуки).
    Возвращает DataFrame: month_label, value, pct.
    """
    if df_upload.empty or df_last_purchase.empty:
        return pd.DataFrame(columns=["month_label", "value", "pct"])
    if value_column not in df_upload.columns or client_code_column not in df_upload.columns:
        return pd.DataFrame(columns=["month_label", "value", "pct"])

    df_last = _add_recency_month(df_last_purchase)
    merged = df_upload[[client_code_column, value_column]].merge(
        df_last[[client_code_column, "month_label"]],
        on=client_code_column,
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=["month_label", "value", "pct"])

    by_month = merged.groupby("month_label", as_index=False)[value_column].sum()
    by_month.columns = ["month_label", "value"]
    total = by_month["value"].sum()
    by_month["pct"] = (by_month["value"] / total * 100).round(1) if total else 0
    return by_month.sort_values("value", ascending=False).reset_index(drop=True)


def contribution_tables_from_upload(
    df_upload: pd.DataFrame,
    df_last_purchase: pd.DataFrame,
    category_filter: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Строит 4 таблицы вклада по реценси для метрик: Продажи, Чеки, Товар в шт., Клиенты.
    Загружаемый документ должен содержать: Группа1, Продажи, Количество чеков, Количество товар, Код клиента.
    - category_filter is None → по всем категориям; иначе только строки с Группа1 == category_filter.
    Возвращает словарь { "Продажи": df, "Чеки": df, "Товар в шт.": df, "Клиенты": df },
    каждый df: month_label, value (абсолютный вклад), pct (доля %).
    """
    if df_upload.empty or df_last_purchase.empty:
        empty = pd.DataFrame(columns=["month_label", "value", "pct"])
        return {"Продажи": empty.copy(), "Чеки": empty.copy(), "Товар в шт.": empty.copy(), "Клиенты": empty.copy()}
    if not all(c in df_upload.columns for c in UPLOAD_REQUIRED_COLUMNS):
        empty = pd.DataFrame(columns=["month_label", "value", "pct"])
        return {"Продажи": empty.copy(), "Чеки": empty.copy(), "Товар в шт.": empty.copy(), "Клиенты": empty.copy()}

    work = df_upload.copy()
    if category_filter is not None:
        work = work[work[COL_GROUP].astype(str).str.strip() == str(category_filter).strip()]
    if work.empty:
        empty = pd.DataFrame(columns=["month_label", "value", "pct"])
        return {"Продажи": empty.copy(), "Чеки": empty.copy(), "Товар в шт.": empty.copy(), "Клиенты": empty.copy()}

    df_last = _add_recency_month(df_last_purchase)
    merged = work.merge(
        df_last[[COL_CLIENT_CODE, "month_label"]],
        on=COL_CLIENT_CODE,
        how="inner",
    )
    if merged.empty:
        empty = pd.DataFrame(columns=["month_label", "value", "pct"])
        return {"Продажи": empty.copy(), "Чеки": empty.copy(), "Товар в шт.": empty.copy(), "Клиенты": empty.copy()}

    def _table_for_metric(metric_col: str, agg: Literal["sum", "nunique"]) -> pd.DataFrame:
        if agg == "sum":
            by_month = merged.groupby("month_label", as_index=False)[metric_col].sum()
        else:
            by_month = merged.groupby("month_label", as_index=False)[COL_CLIENT_CODE].nunique()
        by_month.columns = ["month_label", "value"]
        total = by_month["value"].sum()
        by_month["pct"] = (by_month["value"] / total * 100).round(1) if total else 0
        return by_month.sort_values("value", ascending=False).reset_index(drop=True)

    return {
        "Продажи": _table_for_metric(UPLOAD_COL_SALES, "sum"),
        "Чеки": _table_for_metric(UPLOAD_COL_RECEIPTS, "sum"),
        "Товар в шт.": _table_for_metric(UPLOAD_COL_ITEMS, "sum"),
        "Клиенты": _table_for_metric(COL_CLIENT_CODE, "nunique"),
    }
