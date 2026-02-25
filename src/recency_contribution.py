"""
Расчёт вклада по реценси: группировка по месяцу последней покупки и доля (%). 
Режим «только base»: метрика — число клиентов или сумма «Клиентов».
Режим «base + загрузка»: метрика — выручка или штуки из загружаемого файла.
"""

from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Union

import numpy as np
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

# Варианты названий колонок в файле (приводятся к каноническим)
UPLOAD_COL_ALIASES = {
    "Количество товара": UPLOAD_COL_ITEMS,  # часто в файлах с окончанием "а"
}

# Специальные строки в таблице вклада
LABEL_NO_BONUS_CARD = "Клиенты без БК"
LABEL_NEW_CLIENTS = "Новые клиенты"

# Столбцы загружаемого документа, по которым можно фильтровать категории (мультиотбор)
CATEGORY_COLUMNS = ["Группа1", "Группа2", "Группа3", "Группа4", "Товар"]


def normalize_upload_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Убирает пробелы в названиях колонок и переименовывает известные варианты
    (например «Количество товара») в канонические имена.
    """
    out = df.copy()
    out.columns = out.columns.astype(str).str.strip()
    for alias, canonical in UPLOAD_COL_ALIASES.items():
        if alias in out.columns and canonical not in out.columns:
            out = out.rename(columns={alias: canonical})
    return out

# Имена месяцев для подписи на диаграмме (русская локаль)
MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _add_recency_month(df: pd.DataFrame, date_col: str = "last_purchase_date") -> pd.DataFrame:
    """Добавляет year_month, month_label и period_label (2024 — по кварталам, остальные годы — по месяцам)."""
    out = df.copy()
    out["year_month"] = out[date_col].dt.to_period("M").astype(str)
    out["month_label"] = (
        out[date_col].dt.month.map(MONTH_NAMES) + " " + out[date_col].dt.year.astype(str)
    )
    year = out[date_col].dt.year
    month = out[date_col].dt.month
    quarter = (month - 1) // 3 + 1
    out["period_label"] = np.where(
        year == 2024,
        "C" + quarter.astype(str) + " " + year.astype(str),
        out["month_label"],
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


def _filter_by_categories(df: pd.DataFrame, selected: List[str]) -> pd.DataFrame:
    """Оставляет строки, у которых хотя бы в одном из столбцов CATEGORY_COLUMNS значение входит в selected."""
    if not selected:
        return df
    selected_set = {s.strip() for s in selected}
    cols = [c for c in CATEGORY_COLUMNS if c in df.columns]
    if not cols:
        return df
    mask = pd.Series(False, index=df.index)
    for col in cols:
        mask |= df[col].astype(str).str.strip().isin(selected_set)
    return df[mask].copy()


def contribution_tables_from_upload(
    df_upload: pd.DataFrame,
    df_last_purchase: pd.DataFrame,
    category_filter: Optional[Union[str, List[str]]] = None,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, List[str]]]:
    """
    Строит 4 таблицы вклада по реценси для метрик: Продажи, Чеки, Товар в шт., Клиенты.
    Учитывает: реценси из базы, «Клиенты без БК», «Новые клиенты».
    category_filter: одна категория (строка), список категорий (мультиотбор по Группа1/2/3/4, Товар) или None — по всем.
    """
    empty_df = pd.DataFrame(columns=["month_label", "value", "pct"])
    empty_tables = {
        "Продажи": empty_df.copy(),
        "Чеки": empty_df.copy(),
        "Товар в шт.": empty_df.copy(),
        "Клиенты": empty_df.copy(),
    }
    if df_upload.empty:
        return (empty_tables, {})
    if not all(c in df_upload.columns for c in UPLOAD_REQUIRED_COLUMNS):
        return (empty_tables, {})

    work = df_upload.copy()
    if category_filter is not None:
        if isinstance(category_filter, list):
            work = _filter_by_categories(work, category_filter)
        else:
            work = work[work[COL_GROUP].astype(str).str.strip() == str(category_filter).strip()]
    if work.empty:
        return (empty_tables, {})

    # Строки с пустым кодом клиента — клиенты без бонусной карты
    code_empty = work[COL_CLIENT_CODE].isna() | (work[COL_CLIENT_CODE].astype(str).str.strip() == "")
    work_empty = work[code_empty]
    work_with_code = work[~code_empty]

    # Объединяем с базой по коду клиента (left: остаются и те, кого нет в базе — новые клиенты)
    if df_last_purchase.empty:
        merged = work_with_code.copy()
        merged["period_label"] = np.nan
    else:
        df_last = _add_recency_month(df_last_purchase)
        merged = work_with_code.merge(
            df_last[[COL_CLIENT_CODE, "period_label"]],
            on=COL_CLIENT_CODE,
            how="left",
        )
    merged_in_base = merged[merged["period_label"].notna()]
    new_clients = merged[merged["period_label"].isna()]

    def _one_metric(
        metric_col: str,
        agg: Literal["sum", "nunique"],
        in_base: pd.DataFrame,
        no_bk: pd.DataFrame,
        new: pd.DataFrame,
    ) -> pd.DataFrame:
        parts = []
        if not in_base.empty:
            if agg == "sum":
                by_period = in_base.groupby("period_label", as_index=False)[metric_col].sum()
            else:
                by_period = in_base.groupby("period_label", as_index=False)[COL_CLIENT_CODE].nunique()
            by_period = by_period.rename(columns={"period_label": "month_label"})
            by_period.columns = ["month_label", "value"]
            parts.append(by_period)
        if not new.empty:
            if agg == "sum":
                val = new[metric_col].sum()
            else:
                val = new[COL_CLIENT_CODE].nunique()
            parts.append(pd.DataFrame([{"month_label": LABEL_NEW_CLIENTS, "value": val}]))
        if not no_bk.empty:
            if agg == "sum":
                val = no_bk[metric_col].sum()
            else:
                # Метрика «Клиенты»: точное число клиентов без БК неизвестно — выводим 0
                val = 0
            parts.append(pd.DataFrame([{"month_label": LABEL_NO_BONUS_CARD, "value": val}]))
        if not parts:
            return empty_df.copy()
        combined = pd.concat(parts, ignore_index=True)
        # В метрике «Клиенты» итог и доли считаем без строки «Клиенты без БК»
        total = combined["value"].sum()
        if agg == "nunique":
            total = combined.loc[combined["month_label"] != LABEL_NO_BONUS_CARD, "value"].sum()
        combined["pct"] = 0.0
        if total and total > 0:
            mask = combined["month_label"] != LABEL_NO_BONUS_CARD if agg == "nunique" else slice(None)
            combined.loc[mask, "pct"] = (combined.loc[mask, "value"] / total * 100).round(1)
        return combined.sort_values("value", ascending=False).reset_index(drop=True)

    period_to_clients = {}
    if not merged_in_base.empty:
        period_to_clients = merged_in_base.groupby("period_label")[COL_CLIENT_CODE].apply(
            lambda s: [str(x) for x in s.unique().tolist()]
        ).to_dict()
    if not new_clients.empty:
        period_to_clients[LABEL_NEW_CLIENTS] = [str(x) for x in new_clients[COL_CLIENT_CODE].unique().tolist()]
    period_to_clients[LABEL_NO_BONUS_CARD] = []

    tables = {
        "Продажи": _one_metric(UPLOAD_COL_SALES, "sum", merged_in_base, work_empty, new_clients),
        "Чеки": _one_metric(UPLOAD_COL_RECEIPTS, "sum", merged_in_base, work_empty, new_clients),
        "Товар в шт.": _one_metric(UPLOAD_COL_ITEMS, "sum", merged_in_base, work_empty, new_clients),
        "Клиенты": _one_metric(COL_CLIENT_CODE, "nunique", merged_in_base, work_empty, new_clients),
    }
    return (tables, period_to_clients)
