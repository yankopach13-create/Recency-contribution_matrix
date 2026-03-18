"""
Recency Contribution Matrix — Streamlit.
Период вводится вручную (даты), категории из файлов окна (Группа1–3),
предыдущая покупка — по всей истории base до начала периода.
"""

import html
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

from src.base_period import (
    COL_CLIENT,
    COL_G1,
    COL_G2,
    COL_G3,
    available_period_from_base_filenames,
    filter_window_by_categories,
    load_window_dataframe,
    normalize_client_code,
    scan_previous_purchase_dates,
    sorted_unique_non_empty,
)
from src.recency_contribution import (
    LABEL_NO_BONUS_CARD,
    contribution_tables_from_prev_purchase,
)

BASE_DIR = Path(__file__).resolve().parent / "base"


def _date_from_dmy_parts(dd_s, mm_s, yyyy_s):
    """Собирает date из полей день / месяц / год (только цифры, без точек)."""
    for x in (dd_s, mm_s, yyyy_s):
        if x is None or not str(x).strip():
            return None
    try:
        d, m, y = int(str(dd_s).strip()), int(str(mm_s).strip()), int(str(yyyy_s).strip())
    except ValueError:
        return None
    if not (1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _qp_get_one(qp, key: str):
    v = qp.get(key)
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return str(v[0]) if v else None
    return str(v)


def _date_picker_autoadvance_html(fd, fm, fy, td, tm, ty) -> str:
    """Один блок ввода: автопереход ДД→ММ→ГГГГ для начала и конца; Применить передаёт даты через URL."""
    return f"""
<div style="font-family: system-ui, sans-serif; max-width: 520px;">
  <p style="margin:0 0 6px 0; font-weight:600;">Начало периода</p>
  <div style="display:flex; align-items:center; gap:6px; margin-bottom:14px;">
    <input id="fd" type="text" inputmode="numeric" maxlength="2" placeholder="ДД" value="{html.escape(fd)}"
      style="width:2.5rem; padding:8px; text-align:center; font-size:1rem; border:1px solid #ccc; border-radius:6px;">
    <span style="font-size:1.2rem;">.</span>
    <input id="fm" type="text" inputmode="numeric" maxlength="2" placeholder="ММ" value="{html.escape(fm)}"
      style="width:2.5rem; padding:8px; text-align:center; font-size:1rem; border:1px solid #ccc; border-radius:6px;">
    <span style="font-size:1.2rem;">.</span>
    <input id="fy" type="text" inputmode="numeric" maxlength="4" placeholder="ГГГГ" value="{html.escape(fy)}"
      style="width:4rem; padding:8px; text-align:center; font-size:1rem; border:1px solid #ccc; border-radius:6px;">
  </div>
  <p style="margin:0 0 6px 0; font-weight:600;">Конец периода</p>
  <div style="display:flex; align-items:center; gap:6px; margin-bottom:16px;">
    <input id="td" type="text" inputmode="numeric" maxlength="2" placeholder="ДД" value="{html.escape(td)}"
      style="width:2.5rem; padding:8px; text-align:center; font-size:1rem; border:1px solid #ccc; border-radius:6px;">
    <span style="font-size:1.2rem;">.</span>
    <input id="tm" type="text" inputmode="numeric" maxlength="2" placeholder="ММ" value="{html.escape(tm)}"
      style="width:2.5rem; padding:8px; text-align:center; font-size:1rem; border:1px solid #ccc; border-radius:6px;">
    <span style="font-size:1.2rem;">.</span>
    <input id="ty" type="text" inputmode="numeric" maxlength="4" placeholder="ГГГГ" value="{html.escape(ty)}"
      style="width:4rem; padding:8px; text-align:center; font-size:1rem; border:1px solid #ccc; border-radius:6px;">
  </div>
  <button type="button" id="applyDates" style="padding:10px 20px; font-size:1rem; cursor:pointer; background:#1f77b4; color:#fff; border:none; border-radius:8px;">
    Применить даты
  </button>
  <p style="margin:10px 0 0 0; font-size:0.85rem; color:#666;">Только цифры; после 2 цифр дня/месяца и 4 цифр года курсор переходит дальше. Tab / Shift+Tab — между полями.</p>
</div>
<script>
(function() {{
  function digits(el, maxLen) {{
    el.value = el.value.replace(/\\D/g, '').slice(0, maxLen);
  }}
  var prevMap = {{ fm: 'fd', fy: 'fm', td: 'fy', tm: 'td', ty: 'tm' }};
  function chain(id, maxLen, nextId) {{
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', function() {{
      digits(this, maxLen);
      if (this.value.length >= maxLen && nextId) document.getElementById(nextId).focus();
    }});
    el.addEventListener('keydown', function(e) {{
      if (e.key === 'Backspace' && this.value === '' && prevMap[id]) {{
        var p = document.getElementById(prevMap[id]);
        if (p) {{ p.focus(); p.value = p.value.slice(0, -1); }}
      }}
    }});
  }}
  chain('fd', 2, 'fm');
  chain('fm', 2, 'fy');
  chain('fy', 4, 'td');
  chain('td', 2, 'tm');
  chain('tm', 2, 'ty');
  chain('ty', 4, null);
  document.getElementById('ty').addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') document.getElementById('applyDates').click();
  }});
  document.getElementById('applyDates').onclick = function() {{
    var fd = document.getElementById('fd').value.trim();
    var fm = document.getElementById('fm').value.trim();
    var fy = document.getElementById('fy').value.trim();
    var td = document.getElementById('td').value.trim();
    var tm = document.getElementById('tm').value.trim();
    var ty = document.getElementById('ty').value.trim();
    var base = (window.top && window.top.location) ? window.top.location : window.location;
    var u = new URL(base.href);
    u.searchParams.set('apply_dates', '1');
    u.searchParams.set('fd', fd); u.searchParams.set('fm', fm); u.searchParams.set('fy', fy);
    u.searchParams.set('td', td); u.searchParams.set('tm', tm); u.searchParams.set('ty', ty);
    try {{ window.top.location.assign(u.toString()); }} catch (e) {{ base.assign(u.toString()); }}
  }};
  setTimeout(function() {{ document.getElementById('fd').focus(); }}, 300);
}})();
</script>
"""


def _fmt_num(x) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, float) and x == int(x):
        x = int(x)
    s = f"{x:,.2f}" if isinstance(x, float) and x != int(x) else f"{int(x):,}"
    return s.replace(",", " ")


def _table_html(data_rows: list[tuple], total_fmt: str) -> str:
    total_fmt = html.escape(total_fmt)
    cell_style = "padding: 8px 12px; border: 1px solid #ccc;"
    rows_html_parts = []
    for month, abs_val, pct in data_rows:
        rows_html_parts.append(
            f"<tr>"
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
    <th style="{cell_style} text-align: center; color: #000; vertical-align: middle;">Период реценси</th>
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
    escaped = html.escape(text_to_copy)
    return f"""
<style>
#copy_btn_{block_id} {{ transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease; }}
#copy_btn_{block_id}:hover {{ background: #d8d8d8 !important; box-shadow: 0 2px 6px rgba(0,0,0,0.12); transform: scale(1.02); }}
</style>
<textarea id="codes_ta_{block_id}" style="position:absolute;left:-9999px;width:1px;height:1px;" readonly>{escaped}</textarea>
<div style="margin-top:2px;">
<button type="button" id="copy_btn_{block_id}" style="padding:8px 20px;cursor:pointer;font-size:0.95rem;min-width:280px;width:100%;box-sizing:border-box;background:#e8e8e8;border:1px solid #ccc;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);color:#333;">
  📋 Скопировать коды
</button>
</div>
<script>
(function() {{
  var ta = document.getElementById("codes_ta_{block_id}");
  var btn = document.getElementById("copy_btn_{block_id}");
  if (!ta || !btn) return;
  var defaultLabel = "📋 Скопировать коды";
  btn.onclick = function() {{
    var s = ta.value;
    function showOk() {{
      btn.innerHTML = "✓ Скопировано!";
      btn.style.background = "#d4edda";
      setTimeout(function() {{ btn.innerHTML = defaultLabel; btn.style.background = "#e8e8e8"; }}, 2000);
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
"""


st.set_page_config(page_title="Recency Contribution", layout="wide")
st.title("⏳ Матрица вклада в период по давности предыдущей покупки")

_avail = available_period_from_base_filenames(BASE_DIR)
if _avail:
    st.markdown(f"**Доступный период для анализа:** {_avail}")
else:
    st.markdown(
        "**Доступный период для анализа:** *не определён по именам файлов* "
        "(в имени Excel укажите год и месяц, например `2024 январь.xlsx`)."
    )

qp = st.query_params
_raw_apply = qp.get("apply_dates")
_wants_apply = False
if _raw_apply is not None:
    if isinstance(_raw_apply, (list, tuple)):
        _wants_apply = any(str(x).strip() == "1" for x in _raw_apply)
    else:
        _wants_apply = str(_raw_apply).strip() == "1"

if _wants_apply:
    fd, fm, fy = _qp_get_one(qp, "fd"), _qp_get_one(qp, "fm"), _qp_get_one(qp, "fy")
    td, tm, ty = _qp_get_one(qp, "td"), _qp_get_one(qp, "tm"), _qp_get_one(qp, "ty")
    d_from_try = _date_from_dmy_parts(fd, fm, fy)
    d_to_try = _date_from_dmy_parts(td, tm, ty)
    st.query_params.clear()
    if d_from_try and d_to_try and d_from_try <= d_to_try:
        st.session_state["period_d_from"] = d_from_try
        st.session_state["period_d_to"] = d_to_try
        st.rerun()
    else:
        st.session_state.pop("period_d_from", None)
        st.session_state.pop("period_d_to", None)
        st.error("Проверьте даты: корректные день, месяц, год и чтобы начало не было позже конца.")
        st.session_state["_date_prefill"] = {
            "fd": fd or "", "fm": fm or "", "fy": fy or "",
            "td": td or "", "tm": tm or "", "ty": ty or "",
        }

if "period_d_from" not in st.session_state or "period_d_to" not in st.session_state:
    pre = st.session_state.pop("_date_prefill", None) or {}
    fd, fm, fy = pre.get("fd", ""), pre.get("fm", ""), pre.get("fy", "")
    td, tm, ty = pre.get("td", ""), pre.get("tm", ""), pre.get("ty", "")
    st.markdown("**Период анализа** — ввод с **автопереходом** (после 2 цифр дня/месяца и 4 цифр года курсор сам переходит дальше).")
    components.html(_date_picker_autoadvance_html(fd, fm, fy, td, tm, ty), height=340)
    with st.expander("Если кнопка «Применить даты» не сработала (браузер/облако)"):
        st.caption("Те же 6 полей — применение без перезагрузки страницы.")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            bf = st.text_input("ДД н.", value=fd, key="fb_fd", max_chars=2, placeholder="ДД")
        with c2:
            bm = st.text_input("ММ н.", value=fm, key="fb_fm", max_chars=2, placeholder="ММ")
        with c3:
            by = st.text_input("ГГГГ н.", value=fy, key="fb_fy", max_chars=4, placeholder="ГГГГ")
        with c4:
            bt = st.text_input("ДД к.", value=td, key="fb_td", max_chars=2, placeholder="ДД")
        with c5:
            btm = st.text_input("ММ к.", value=tm, key="fb_tm", max_chars=2, placeholder="ММ")
        with c6:
            bty = st.text_input("ГГГГ к.", value=ty, key="fb_ty", max_chars=4, placeholder="ГГГГ")
        if st.button("Применить (запасной вариант)", key="fb_apply"):
            df_b = _date_from_dmy_parts(bf, bm, by)
            dt_b = _date_from_dmy_parts(bt, btm, bty)
            if df_b and dt_b and df_b <= dt_b:
                st.session_state["period_d_from"] = df_b
                st.session_state["period_d_to"] = dt_b
                st.rerun()
            else:
                st.error("Некорректные даты.")
    st.stop()

d_from = st.session_state["period_d_from"]
d_to = st.session_state["period_d_to"]
c1, c2 = st.columns([3, 1])
with c1:
    st.caption(f"**Текущий период:** {d_from.strftime('%d.%m.%Y')} — {d_to.strftime('%d.%m.%Y')}")
with c2:
    if st.button("Сменить даты", key="btn_change_dates"):
        for k in (
            "period_d_from",
            "period_d_to",
            "window_df",
            "window_d_from",
            "window_d_to",
            "contribution_tables",
            "upload_totals",
            "period_to_clients",
        ):
            st.session_state.pop(k, None)
        st.rerun()

if st.button("Сканировать выбранный период", type="secondary"):
    with st.spinner("Читаю файлы, пересекающиеся с выбранными датами…"):
        df_win, warns, files_read = load_window_dataframe(BASE_DIR, d_from, d_to)
    st.session_state.pop("contribution_tables", None)
    st.session_state.pop("upload_totals", None)
    st.session_state.pop("period_to_clients", None)
    if df_win.empty:
        st.session_state.pop("window_df", None)
        st.session_state.pop("window_d_from", None)
        st.session_state.pop("window_d_to", None)
        st.warning(
            "Нет строк в выбранном периоде. Проверьте даты и формат файлов "
            "(нужны колонки: Группа1–3, Дата, Продажи, Количество чеков, Количество товар, Код клиента)."
        )
    else:
        st.session_state["window_df"] = df_win
        st.session_state["window_d_from"] = d_from
        st.session_state["window_d_to"] = d_to
    for w in warns:
        st.caption(f"⚠ {w}")

if "window_df" in st.session_state:
    if (
        st.session_state.get("window_d_from") != d_from
        or st.session_state.get("window_d_to") != d_to
    ):
        st.warning("Даты периода изменились — нажмите **Сканировать выбранный период** снова.")

if "window_df" not in st.session_state or st.session_state["window_df"].empty:
    st.stop()

df_cat = st.session_state["window_df"]
if st.session_state.get("window_d_from") != d_from or st.session_state.get("window_d_to") != d_to:
    st.stop()

st.subheader("Категории")
ALL = "(все)"

opts_g1 = [ALL] + sorted_unique_non_empty(df_cat[COL_G1])
sel1 = st.selectbox("Группа1", options=opts_g1, key="sel_g1")
df_g1 = df_cat if sel1 == ALL else df_cat[df_cat[COL_G1] == sel1]
opts_g2 = [ALL] + sorted_unique_non_empty(df_g1[COL_G2])
sel2 = st.selectbox("Группа2", options=opts_g2, key="sel_g2")
df_g2 = df_g1 if sel2 == ALL else df_g1[df_g1[COL_G2] == sel2]
opts_g3 = [ALL] + sorted_unique_non_empty(df_g2[COL_G3])
sel3 = st.selectbox("Группа3", options=opts_g3, key="sel_g3")

g1_f = None if sel1 == ALL else sel1
g2_f = None if sel2 == ALL else sel2
g3_f = None if sel3 == ALL else sel3

if st.button("Посчитать", type="primary"):
    df_work = filter_window_by_categories(df_cat, g1_f, g2_f, g3_f)
    mask_win = (
        pd.to_datetime(df_work["Дата"], errors="coerce").dt.date >= d_from
    ) & (pd.to_datetime(df_work["Дата"], errors="coerce").dt.date <= d_to)
    df_work = df_work.loc[mask_win].copy()
    if df_work.empty:
        st.warning("После фильтра по датам и категориям нет строк. Измените период или категории.")
        st.stop()
    df_work["_client_norm"] = df_work[COL_CLIENT].map(normalize_client_code)
    clients_set = set(df_work["_client_norm"].dropna().astype(str))

    progress = st.progress(0)
    status = st.empty()

    def _cb(cur: int, total: int, name: str):
        progress.progress(cur / max(total, 1))
        status.caption(f"Скан истории: файл **{cur}/{total}** — `{name}`")

    with st.spinner("Ищу предыдущие покупки по всей base…"):
        prev_map = scan_previous_purchase_dates(BASE_DIR, clients_set, d_from, progress=_cb)
    progress.empty()
    status.empty()

    tables, period_to_clients = contribution_tables_from_prev_purchase(
        df_work, prev_map, analysis_start=d_from
    )
    upload_totals = {
        "Продажи": float(df_work["Продажи"].sum()),
        "Чеки": float(df_work["Количество чеков"].sum()),
        "Товар в шт.": float(df_work["Количество товар"].sum()),
        "Клиенты": int(df_work[COL_CLIENT].nunique()),
    }
    st.session_state["contribution_tables"] = tables
    st.session_state["upload_totals"] = upload_totals
    st.session_state["period_to_clients"] = period_to_clients

if "contribution_tables" not in st.session_state:
    st.stop()

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
            st.markdown(_table_html(data_rows, total_fmt), unsafe_allow_html=True)
        with col_chart:
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=df_metric["month_label"],
                        values=df_metric["value"],
                        hole=0.6,
                        textinfo="label+percent",
                        textposition="inside",
                        insidetextorientation="radial",
                        showlegend=False,
                        textfont=dict(size=12),
                        automargin=True,
                    )
                ]
            )
            total_str = _fmt_num(upload_totals[metric_key])
            fig.add_annotation(
                text=total_str,
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=24, color="gray"),
            )
            fig.update_layout(
                height=500,
                margin=dict(t=20, b=20, l=20, r=20),
                uniformtext=dict(minsize=10, mode="hide"),
            )
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("---")
        st.subheader("👥 Коды клиентов")
        month_options = [
            str(m) for m in df_metric["month_label"] if str(m) != LABEL_NO_BONUS_CARD
        ]
        if month_options:
            st.caption("Выберите группу (период реценси) для копирования кодов")
            col_sel, _ = st.columns([1, 3])
            with col_sel:
                sel_key = f"month_sel_{metric_key.replace(' ', '_').replace('.', '_')}"
                selected_month = st.selectbox(
                    "Период",
                    options=month_options,
                    key=sel_key,
                    label_visibility="collapsed",
                )
                codes = period_to_clients.get(selected_month, [])

                def _fmt_code(c):
                    try:
                        f = float(c)
                        return str(int(f)) if f == int(f) else str(c)
                    except (ValueError, TypeError):
                        return str(c)

                text_to_copy = "\n".join(_fmt_code(c) for c in codes)
                components.html(_copy_codes_block_html(text_to_copy, sel_key), height=52)
        else:
            st.caption("Нет периодов для выбора кодов (кроме «Клиенты без БК»).")
