"""
Загрузка данных из папки base (Excel): покупки по датам и кодам клиентов.
Строит справочник: код клиента → дата последней покупки (и при необходимости категория).
"""

from pathlib import Path
from typing import Optional

import pandas as pd

# Ожидаемые колонки в файлах base (Excel)
COL_GROUP = "Группа1"
COL_DATE = "Дата"
COL_CLIENTS = "Клиентов"
COL_CLIENT_CODE = "Код клиента"

BASE_DIR_NAME = "base"


def _parse_date(ser: pd.Series) -> pd.Series:
    """Приведение колонки даты к datetime (поддержка ДД.ММ.ГГГГ и других форматов)."""
    return pd.to_datetime(ser, dayfirst=True, errors="coerce")


def load_base_excel(path: Path) -> Optional[pd.DataFrame]:
    """
    Читает один Excel-файл из base.
    Возвращает DataFrame с колонками Группа1, Дата, Клиентов, Код клиента или None при ошибке.
    """
    try:
        df = pd.read_excel(path, engine="openpyxl")
        needed = [COL_GROUP, COL_DATE, COL_CLIENTS, COL_CLIENT_CODE]
        if not all(c in df.columns for c in needed):
            return None
        df[COL_DATE] = _parse_date(df[COL_DATE])
        df = df.dropna(subset=[COL_DATE, COL_CLIENT_CODE])
        return df
    except Exception:
        return None


def scan_base(base_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Сканирует папку base: читает все .xlsx/.xls файлы, объединяет в один DataFrame.
    base_dir — путь к папке base; по умолчанию — base/ относительно текущей рабочей директории.
    """
    if base_dir is None:
        base_dir = Path.cwd() / BASE_DIR_NAME
    if not base_dir.is_dir():
        return pd.DataFrame()

    frames = []
    for ext in ("*.xlsx", "*.xls"):
        for path in base_dir.glob(ext):
            df = load_base_excel(path)
            if df is not None and not df.empty:
                df["_source_file"] = path.name
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_last_purchase_per_client(
    df_base: pd.DataFrame,
) -> pd.DataFrame:
    """
    По сырой базе покупок строит таблицу: один ряд на клиента — дата последней покупки.
    Колонки: Код клиента, last_purchase_date (datetime), при наличии — Группа1 из последней покупки.
    """
    if df_base.empty:
        return pd.DataFrame(columns=[COL_CLIENT_CODE, "last_purchase_date"])

    last = (
        df_base.sort_values(COL_DATE)
        .groupby(COL_CLIENT_CODE, as_index=False)
        .agg(
            last_purchase_date=(COL_DATE, "max"),
            **({COL_GROUP: (COL_GROUP, "last")} if COL_GROUP in df_base.columns else {}),
        )
    )
    return last


def get_last_purchase_table(base_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Сканирует base и возвращает таблицу «код клиента → дата последней покупки»
    (и при наличии — Группа1). Удобная точка входа для приложения.
    """
    df = scan_base(base_dir)
    return build_last_purchase_per_client(df)
