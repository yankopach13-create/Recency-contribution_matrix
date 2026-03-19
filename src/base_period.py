"""
Работа с Excel в base по периодам: разбор имён файлов (год + русский месяц),
загрузка оконных данных для категорий и полный скан истории для «предыдущей покупки».
"""

from __future__ import annotations

import re
import calendar
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

import pandas as pd

# Колонки в новом формате base
COL_G1 = "Группа1"
COL_G2 = "Группа2"
COL_G3 = "Группа3"
COL_DATE = "Дата"
COL_SALES = "Продажи"
COL_RECEIPTS = "Количество чеков"
COL_ITEMS = "Количество товар"
COL_CLIENT = "Код клиента"

SALES_REQUIRED = [COL_G1, COL_G2, COL_G3, COL_DATE, COL_SALES, COL_RECEIPTS, COL_ITEMS, COL_CLIENT]

COL_ALIASES = {"Количество товара": COL_ITEMS}

NUM_TO_RU_MONTH = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

RU_MONTH_TO_NUM = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

# «2024 январь», «2024 январь 2», «prefix 2024 январь»
_YEAR_MONTH_RE = re.compile(
    r"(\d{4})\s*(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)",
    re.IGNORECASE,
)


def parse_year_month_from_filename(name: str) -> Optional[Tuple[int, int]]:
    """
    Из имени файла извлекает (год, месяц), если есть шаблон «YYYY русский_месяц».
    """
    stem = Path(name).stem
    m = _YEAR_MONTH_RE.search(stem.lower())
    if not m:
        return None
    y, mon = int(m.group(1)), RU_MONTH_TO_NUM[m.group(2).lower()]
    return (y, mon)


def _month_start(y: int, m: int) -> date:
    return date(y, m, 1)


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def month_range_intersects_window(y: int, m: int, d_from: date, d_to: date) -> bool:
    """Календарный месяц (y,m) пересекается с [d_from, d_to]."""
    start = _month_start(y, m)
    end = _month_end(y, m)
    return start <= d_to and end >= d_from


def normalize_client_code(x) -> Optional[str]:
    """Единый вид кода клиента для множеств и джойнов."""
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        f = float(s.replace(",", "."))
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return s


def _strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    for a, c in COL_ALIASES.items():
        if a in df.columns and c not in df.columns:
            df = df.rename(columns={a: c})
    return df


def load_sales_excel(path: Path) -> Optional[pd.DataFrame]:
    """
    Читает один Excel с полным набором колонок продаж.
    Возвращает None, если формат не подходит.
    """
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception:
        return None
    df = _strip_columns(df)
    if not all(c in df.columns for c in SALES_REQUIRED):
        return None
    df = df[SALES_REQUIRED].copy()
    df[COL_DATE] = pd.to_datetime(df[COL_DATE], dayfirst=True, errors="coerce")
    for c in (COL_SALES, COL_RECEIPTS, COL_ITEMS):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df[COL_G1] = df[COL_G1].astype(str).str.strip()
    df[COL_G2] = df[COL_G2].astype(str).str.strip()
    df[COL_G3] = df[COL_G3].astype(str).str.strip()
    return df


def load_sales_excel_minimal(path: Path, cols: List[str]) -> Optional[pd.DataFrame]:
    """Читает только указанные колонки (для ускорения скана истории)."""
    try:
        df = pd.read_excel(path, engine="openpyxl", usecols=cols)
    except Exception:
        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception:
            return None
    df = _strip_columns(df)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return None
    return df[cols].copy()


def available_period_from_base_filenames(base_dir: Path) -> Optional[str]:
    """
    Диапазон по минимальному и максимальному (год, месяц) из имён файлов
    вида «2024 январь». Если таких имён нет — None.
    """
    months: List[Tuple[int, int]] = []
    for p in list_sales_files(base_dir):
        ym = parse_year_month_from_filename(p.name)
        if ym:
            months.append(ym)
    if not months:
        return None
    months.sort()
    y1, m1 = months[0]
    y2, m2 = months[-1]
    return f"{NUM_TO_RU_MONTH[m1]} {y1} — {NUM_TO_RU_MONTH[m2]} {y2}"


def available_date_bounds_from_base_filenames(base_dir: Path) -> Optional[Tuple[date, date]]:
    """
    Первый день самого раннего и последний день самого позднего месяца
    по файлам с шаблоном «ГГГГ русский_месяц» в имени. Иначе None.
    """
    months: List[Tuple[int, int]] = []
    for p in list_sales_files(base_dir):
        ym = parse_year_month_from_filename(p.name)
        if ym:
            months.append(ym)
    if not months:
        return None
    months.sort()
    y1, m1 = months[0]
    y2, m2 = months[-1]
    return (_month_start(y1, m1), _month_end(y2, m2))


def validate_user_period_for_scan(
    d_from: date,
    d_to: date,
    base_bounds: Optional[Tuple[date, date]],
    today: date,
) -> Optional[str]:
    """
    Проверка перед сканированием. Возвращает текст ошибки или None.
    Период должен лежать внутри календарных границ base и не заходить в будущее.
    """
    if base_bounds is None:
        return (
            "Нельзя определить доступный период base: в имени ни одного Excel нет "
            "года и русского месяца (пример: «2024 январь.xlsx»)."
        )
    b0, b1 = base_bounds
    if d_from < b0 or d_to > b1:
        return (
            f"Период анализа должен полностью находиться внутри доступного диапазона base: "
            f"с {b0.strftime('%d.%m.%Y')} по {b1.strftime('%d.%m.%Y')}."
        )
    if d_from > today or d_to > today:
        return "Начало и конец периода не могут быть позже сегодняшней даты."
    if d_from > d_to:
        return "Начало периода не может быть позже конца."
    return None


def list_sales_files(base_dir: Path) -> List[Path]:
    paths = []
    if not base_dir.is_dir():
        return paths
    for ext in ("*.xlsx", "*.xls"):
        paths.extend(sorted(base_dir.glob(ext)))
    return paths


def classify_files(base_dir: Path) -> List[Tuple[Path, Optional[Tuple[int, int]]]]:
    """Список (путь, (год, месяц) или None)."""
    out = []
    for p in list_sales_files(base_dir):
        ym = parse_year_month_from_filename(p.name)
        out.append((p, ym))
    return out


def paths_for_window(
    classified: List[Tuple[Path, Optional[Tuple[int, int]]]], d_from: date, d_to: date
) -> List[Path]:
    """Файлы, чей календарный месяц пересекает окно анализа; без распознанного месяца — читаем и фильтруем по дате."""
    need_scan: List[Path] = []
    for path, ym in classified:
        if ym is not None:
            if month_range_intersects_window(ym[0], ym[1], d_from, d_to):
                need_scan.append(path)
        else:
            need_scan.append(path)
    return need_scan


def mask_rows_date_in_window(date_series: pd.Series, d_from: date, d_to: date) -> pd.Series:
    """Булева маска: дата в [d_from, d_to] (по календарным датам)."""
    dt = pd.to_datetime(date_series, errors="coerce")
    d = dt.dt.date
    return dt.notna() & (d >= d_from) & (d <= d_to)


def load_window_dataframe(
    base_dir: Path, d_from: date, d_to: date
) -> Tuple[pd.DataFrame, List[str], int]:
    """
    Объединяет все строки из файлов окна, у которых Дата попадает в [d_from, d_to].
    Возвращает (df, warnings, files_read).
    """
    warnings: List[str] = []
    classified = classify_files(base_dir)
    paths = paths_for_window(classified, d_from, d_to)
    frames = []
    files_read = 0
    ym_by_path = {p: ym for p, ym in classified}

    for path in paths:
        df = load_sales_excel(path)
        if df is None:
            try:
                pd.read_excel(path, engine="openpyxl", nrows=0)
                warnings.append(f"Пропуск (нет нужных колонок): {path.name}")
            except Exception:
                warnings.append(f"Не прочитан: {path.name}")
            continue
        if df.empty:
            continue
        files_read += 1
        ym = ym_by_path.get(path)
        sub = df.loc[mask_rows_date_in_window(df[COL_DATE], d_from, d_to)].copy()
        if ym is None and sub.empty and not df.empty:
            warnings.append(
                f"Файл без года/месяца в имени «{path.name}»: отобраны только строки в окне дат."
            )
        if not sub.empty:
            sub = sub.copy()
            sub["_source_file"] = path.name
            frames.append(sub)

    if not frames:
        return pd.DataFrame(), warnings, files_read
    out = pd.concat(frames, ignore_index=True)
    return out, warnings, files_read


def mask_date_strictly_before_start(date_series: pd.Series, window_start: date) -> pd.Series:
    """Дата строго раньше calendar window_start."""
    dt = pd.to_datetime(date_series, errors="coerce")
    d = dt.dt.date
    return dt.notna() & (d < window_start)


def scan_previous_purchase_dates(
    base_dir: Path,
    client_codes: Set[str],
    window_start: date,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, pd.Timestamp]:
    """
    Для каждого кода из client_codes — максимальная дата покупки строго раньше window_start
    по всем файлам base (любые категории).
    """
    if not client_codes:
        return {}
    classified = classify_files(base_dir)
    y0, m0 = window_start.year, window_start.month
    prev: Dict[str, pd.Timestamp] = {}
    n_files = len(classified)
    for idx, (path, ym) in enumerate(classified):
        if progress:
            progress(idx + 1, n_files, path.name)
        skip_entire = False
        if ym is not None:
            fy, fm = ym
            if (fy, fm) > (y0, m0):
                skip_entire = True
            elif (fy, fm) < (y0, m0):
                need_filter_before = False
            else:
                need_filter_before = True
        else:
            need_filter_before = True

        if skip_entire:
            continue

        df = load_sales_excel_minimal(path, [COL_DATE, COL_CLIENT])
        if df is None or df.empty:
            continue
        df[COL_DATE] = pd.to_datetime(df[COL_DATE], dayfirst=True, errors="coerce")
        df = df.dropna(subset=[COL_DATE])
        codes = df[COL_CLIENT].map(normalize_client_code)
        df = df.assign(_cc=codes)
        df = df[df["_cc"].notna() & df["_cc"].isin(client_codes)]
        if df.empty:
            continue
        if need_filter_before:
            df = df.loc[mask_date_strictly_before_start(df[COL_DATE], window_start)]
        if df.empty:
            continue
        for cc, grp in df.groupby("_cc", sort=False):
            mx = grp[COL_DATE].max()
            old = prev.get(cc)
            if old is None or mx > old:
                prev[cc] = mx
    return prev


def load_last_purchase_day_rows(
    base_dir: Path,
    client_codes: Set[str],
    prev_map: Dict[str, pd.Timestamp],
    window_start: date,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> pd.DataFrame:
    """
    Для каждого клиента из client_codes с записью в prev_map — все строки продаж
    за календарный день последней покупки (строго до window_start).
    """
    last_day: Dict[str, date] = {}
    for cc in client_codes:
        ts = prev_map.get(cc)
        if ts is None or (isinstance(ts, float) and pd.isna(ts)):
            continue
        t = pd.Timestamp(ts)
        if pd.isna(t):
            continue
        last_day[cc] = t.normalize().date()
    if not last_day:
        return pd.DataFrame()

    y0, m0 = window_start.year, window_start.month
    frames: List[pd.DataFrame] = []
    classified = classify_files(base_dir)
    n_files = len(classified)
    for idx, (path, ym) in enumerate(classified):
        if progress:
            progress(idx + 1, n_files, path.name)
        skip_entire = False
        if ym is not None:
            fy, fm = ym
            if (fy, fm) > (y0, m0):
                skip_entire = True
        if skip_entire:
            continue

        df = load_sales_excel(path)
        if df is None or df.empty:
            continue
        df = df.copy()
        codes = df[COL_CLIENT].map(normalize_client_code)
        df = df.assign(_cc=codes)
        df = df[df["_cc"].notna() & df["_cc"].isin(last_day)]
        if df.empty:
            continue
        row_d = df[COL_DATE].dt.normalize().dt.date
        ld = df["_cc"].map(last_day)
        df = df.loc[row_d == ld].copy()
        if df.empty:
            continue
        df["_source_file"] = path.name
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def top_g2_last_purchase_day(
    df_lines: pd.DataFrame, total_clients: int, top_n: int = 10
) -> pd.DataFrame:
    """
    Топ top_n по связке Группа1 + Группа2.
    В итоговую таблицу выводится только % клиентов (доля от total_clients).
    """
    if df_lines.empty or total_clients <= 0:
        return pd.DataFrame(columns=["Группа1", "Группа2", "% клиентов"])
    if "_cc" not in df_lines.columns:
        df_lines = df_lines.copy()
        df_lines["_cc"] = df_lines[COL_CLIENT].map(normalize_client_code)
    g = (
        df_lines.groupby([COL_G1, COL_G2], as_index=False)
        .agg(Клиентов=("_cc", "nunique"))
        .sort_values("Клиентов", ascending=False)
        .head(top_n)
    )
    g["% клиентов"] = (g["Клиентов"] / total_clients * 100).round(1)
    return g[["Группа1", "Группа2", "% клиентов"]].reset_index(drop=True)


def filter_window_by_categories(
    df: pd.DataFrame,
    g1: Optional[Union[str, Sequence[str]]] = None,
    g2: Optional[Union[str, Sequence[str]]] = None,
    g3: Optional[Union[str, Sequence[str]]] = None,
) -> pd.DataFrame:
    """
    Фильтр по Группа1–3.
    None / пустая строка / пустой список — без ограничения по этому уровню.
    Строка — одно значение; непустой список — строки, где поле входит в список.
    """

    def _norm_list(val: Union[str, Sequence[str], None]) -> Optional[List[str]]:
        if val is None:
            return None
        if isinstance(val, str):
            s = val.strip()
            return [s] if s else None
        seq = [str(x).strip() for x in val if x is not None and str(x).strip()]
        return seq if seq else None

    out = df
    for col, raw in ((COL_G1, g1), (COL_G2, g2), (COL_G3, g3)):
        lst = _norm_list(raw)
        if lst is not None:
            out = out[out[col].isin(lst)]
    return out


def sorted_unique_non_empty(series: pd.Series) -> List[str]:
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    return sorted(s.unique().tolist())
