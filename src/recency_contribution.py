"""
Расчёт вклада по реценси: группировка по месяцу последней покупки и доля (%). 
Режим «только base»: метрика — число клиентов или сумма «Клиентов».
Режим «base + загрузка»: метрика — выручка или штуки из загружаемого файла.
"""

from pathlib import Path
from typing import Literal, Optional

import pandas as pd

from .load_base import (
    COL_CLIENT_CODE,
    COL_CLIENTS,
    scan_base,
    build_last_purchase_per_client,
)

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
