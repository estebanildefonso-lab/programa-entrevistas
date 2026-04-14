"""
Piloto local (una sola PC): estructura tipo AppSheet.
Más adelante: apuntar data_loader a tu Excel o vincular varias hojas.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    APP_ENV,
    COLUMNS,
    DATA_DIR,
    DATE_FILTER_COLUMN,
    ENUMS,
    GOOGLE_SHEET_ID,
    RAILWAY_ENVIRONMENT,
    RECORD_ID_COLUMNS,
    SEARCH_COLUMNS,
    SLICES,
    SOURCE_WORKBOOK,
)
from data_loader import (
    ensure_dataframe,
    load_data_source,
    load_status,
    sample_dataframe,
)

st.set_page_config(page_title="APP PILOTO", layout="wide")

EXPORT_DIR = Path("exports")


def _strip_str(x) -> str:
    return str(x).strip() if x is not None and not (isinstance(x, float) and pd.isna(x)) else ""


def _find_row_index(full: pd.DataFrame, row: pd.Series) -> int | None:
    """Localiza la fila en `full` por AppKey."""
    for col in RECORD_ID_COLUMNS:
        val = _strip_str(row.get(col, ""))
        if not val:
            continue
        m = full[col].astype(str).str.strip() == val
        idx = full.index[m]
        if len(idx):
            return int(idx[0])
    return None


def _next_app_key(full: pd.DataFrame) -> str:
    prefix = "APP-"
    best = 0
    for v in full["AppKey"].astype(str):
        v = v.strip()
        if v.upper().startswith(prefix.upper()) and len(v) > len(prefix):
            tail = v[len(prefix) :]
            if tail.isdigit():
                best = max(best, int(tail))
    return f"{prefix}{best + 1:05d}"


def _merge_edited_into_full(full: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    full = full.copy()
    if edited is None or edited.empty:
        return full
    for _, row in edited.iterrows():
        i = _find_row_index(full, row)
        if i is not None:
            for c in COLUMNS:
                if c in row.index:
                    full.at[i, c] = row[c]
            continue
        # Fila nueva: exige al menos un ID o asigna AppKey
        new = {c: row.get(c, "") for c in COLUMNS}
        if not any(_strip_str(new.get(c)) for c in RECORD_ID_COLUMNS):
            new["AppKey"] = _next_app_key(full)
        full = pd.concat([full, pd.DataFrame([new])], ignore_index=True)
    return full


def _parse_dates(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    s = df[col]
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_datetime(s, errors="coerce", unit="d", origin="1899-12-30")
    parsed = pd.to_datetime(s, errors="coerce", dayfirst=False)
    if parsed.notna().sum() < max(1, len(s) // 5):
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return parsed


def _iso_week_range_label(iso_year: int, iso_week: int) -> str:
    try:
        d0 = date.fromisocalendar(int(iso_year), int(iso_week), 1)
        d1 = d0 + timedelta(days=6)
        return f"{d0.strftime('%d %b')} – {d1.strftime('%d %b %Y')}"
    except ValueError:
        return ""


def _years_in_data(dt: pd.Series) -> list[int]:
    ical = dt.dt.isocalendar()
    ys = ical["year"].dropna().unique()
    return sorted(int(y) for y in ys if pd.notna(y))


def _weeks_present_in_data(dt: pd.Series, year_choice: str) -> list[int]:
    """
    Semanas ISO que tienen al menos una fila con fecha válida.
    Si year_choice es un año concreto, solo semanas de ese año ISO.
    Si es "Todos los años", solo números de semana que existen en algún año (en tus datos).
    """
    parsed = dt
    valid = parsed.notna()
    if not valid.any():
        return []
    ical = parsed.dt.isocalendar()
    iso_y = pd.to_numeric(ical["year"], errors="coerce")
    iso_w = pd.to_numeric(ical["week"], errors="coerce")
    ok = valid & iso_y.notna() & iso_w.notna()
    if year_choice != "Todos los años":
        ok = ok & (iso_y == int(year_choice))
    weeks = iso_w[ok].dropna().unique()
    return sorted(int(w) for w in weeks)


def date_week_filter_mask(
    df: pd.DataFrame,
    date_col: str,
    year_choice: str,
    week_num: int | None,
) -> pd.Series:
    """
    Filtra por año ISO y semana ISO.
    year_choice: 'Todos los años' o '2025', etc.
    week_num: None = todas las semanas; 1–53 = semana ISO.
    """
    dt = _parse_dates(df, date_col)
    valid = dt.notna()
    if year_choice == "Todos los años" and week_num is None:
        return pd.Series(True, index=df.index)

    ical = dt.dt.isocalendar()
    # to_numeric evita fallos de comparación con UInt32 / tipos nullable de pandas
    iso_y = pd.to_numeric(ical["year"], errors="coerce")
    iso_w = pd.to_numeric(ical["week"], errors="coerce")
    mask = valid & iso_y.notna() & iso_w.notna()
    if year_choice != "Todos los años":
        mask = mask & (iso_y == int(year_choice))
    if week_num is not None:
        mask = mask & (iso_w == int(week_num))
    return mask


def search_mask(df: pd.DataFrame, query: str) -> pd.Series:
    q = query.strip().lower()
    if not q:
        return pd.Series(True, index=df.index)
    mask = pd.Series(False, index=df.index)
    for col in SEARCH_COLUMNS:
        if col not in df.columns:
            continue
        mask = mask | df[col].astype(str).str.lower().str.contains(q, regex=False, na=False)
    return mask


def apply_slice(name: str, df: pd.DataFrame) -> pd.DataFrame:
    fn = SLICES.get(name)
    if fn is None:
        return df
    try:
        out = fn(df)
        return out if len(out) else df.iloc[0:0].copy()
    except Exception:
        return df


def _apply_edited_view(edited: pd.DataFrame, success_message: str) -> None:
    full = _merge_edited_into_full(st.session_state.df.copy(), edited)
    st.session_state.df = ensure_dataframe(full)
    st.success(success_message)
    st.rerun()


def main() -> None:
    st.title("APP PILOTO — entrevistas")
    st.caption(
        "Cada registro se identifica por **AppKey**. "
        "La búsqueda acepta AppKey, nombre, correo o número. Puedes usar Google Sheets como fuente remota "
        "y descargar la salida actualizada como Excel."
    )

    if "df" not in st.session_state:
        loaded = load_data_source()
        if loaded is not None:
            st.session_state.df = ensure_dataframe(loaded)
            st.session_state._loaded_from_file = True
        else:
            st.session_state.df = sample_dataframe()
            st.session_state._loaded_from_file = False
        st.session_state._load_meta = load_status()

    col_a, col_b, col_c, col_d = st.columns([1, 1, 1, 2])
    with col_a:
        if st.button("Recargar fuente"):
            loaded = load_data_source()
            meta = load_status()
            st.session_state._load_meta = meta
            if loaded is not None:
                st.session_state.df = ensure_dataframe(loaded)
                st.session_state._loaded_from_file = True
            else:
                st.session_state._loaded_from_file = False
                st.warning(meta.get("message", "No se pudo cargar el archivo."))
            st.rerun()
    with col_b:
        if st.button("Recargar muestra demo"):
            st.session_state.df = sample_dataframe()
            st.session_state._loaded_from_file = False
            st.session_state._load_meta = load_status()
            st.rerun()
    with col_c:
        if st.session_state.get("_loaded_from_file"):
            meta = st.session_state.get("_load_meta") or load_status()
            st.success(meta.get("message", "Datos cargados correctamente"))
        else:
            if GOOGLE_SHEET_ID:
                st.warning(
                    "No se pudo leer el Google Sheet configurado → usando muestra demo. "
                    "Revisa variables y vuelve a pulsar **Recargar fuente**."
                )
            else:
                st.info(
                    f"Sin fuente remota y sin libro en **{DATA_DIR}/{SOURCE_WORKBOOK}** → muestra demo. "
                    "Configura Google Sheets o copia tu Excel local y pulsa **Recargar fuente**."
                )

    with col_d:
        slice_name = st.selectbox("Vista / etapa", list(SLICES.keys()))

    search = st.text_input(
        "Buscar por AppKey, nombre, correo o número",
        placeholder="Ej. APP-00042, Juan, 5512345678 o @dominio",
    )

    df = st.session_state.df.copy()
    if search.strip():
        df = df[search_mask(df, search)]

    st.markdown("**Filtro por semana (año ISO + semana ISO)**")
    st.caption(
        "Siempre según **Start Date**. Año y semana son **ISO**. "
        "Solo se listan **años y semanas que ya tienen al menos una entrevista** en tus datos "
        "(no aparecen semanas vacías ni meses sin registros)."
    )
    date_col = DATE_FILTER_COLUMN
    f2, f3 = st.columns([1, 1.4])
    dt_all = _parse_dates(st.session_state.df, date_col)
    years_opts = ["Todos los años"] + [str(y) for y in _years_in_data(dt_all)]
    if len(years_opts) == 1:
        years_opts = ["Todos los años", "2025", "2026"]
    with f2:
        year_sel = st.selectbox("Año (ISO)", years_opts, index=0)

    weeks_in_data = _weeks_present_in_data(dt_all, year_sel)

    def _week_option_label(w: int) -> str:
        if w == 0:
            return "Todas las semanas"
        if year_sel != "Todos los años":
            return f"Semana {w} · {_iso_week_range_label(int(year_sel), w)}"
        return f"Semana {w} (en tus datos, cualquier año)"

    week_options = [0] + weeks_in_data
    week_key = "iso_w_" + "".join(c if c.isalnum() else "_" for c in year_sel)
    with f3:
        week_pick = st.selectbox(
            "Semana (ISO)",
            week_options,
            index=0,
            format_func=_week_option_label,
            key=week_key,
        )
    week_num: int | None = None if week_pick == 0 else int(week_pick)

    df = df[date_week_filter_mask(df, date_col, year_sel, week_num)]

    df_view = apply_slice(slice_name, df)

    column_config = {
        "AppKey": st.column_config.TextColumn(
            "AppKey",
            help="Clave estable del piloto; enlaza la fila al exportar y al editar.",
        ),
        "Start Date": st.column_config.DateColumn(
            "Start Date",
            format="DD-MM-YYYY",
            help="Fecha de la entrevista sin hora.",
        ),
    }
    for col, options in ENUMS.items():
        if options:
            column_config[col] = st.column_config.SelectboxColumn(col, options=options)

    candidate_columns = [
        "AppKey",
        "Invitee Name",
        "Correo",
        "Numeros",
        "Start Date",
        "Date + Week",
        "canal",
    ]
    candidate_column_config = {
        "AppKey": column_config["AppKey"],
        "Start Date": column_config["Start Date"],
        "Date + Week": st.column_config.TextColumn(
            "Date + Week",
            help="Referencia rápida de fecha y semana ISO.",
            disabled=True,
        ),
    }
    if "canal" in column_config:
        candidate_column_config["canal"] = column_config["canal"]

    attendance_columns = [
        "AppKey",
        "Invitee Name",
        "Start Date",
        "Date + Week",
        "canal",
        "Interview status",
    ]
    attendance_column_config = {
        "AppKey": column_config["AppKey"],
        "Start Date": column_config["Start Date"],
        "Date + Week": st.column_config.TextColumn(
            "Date + Week",
            help="Referencia rápida de fecha y semana ISO.",
            disabled=True,
        ),
    }
    if "canal" in column_config:
        attendance_column_config["canal"] = column_config["canal"]
    if "Interview status" in column_config:
        attendance_column_config["Interview status"] = column_config["Interview status"]

    interview_background_columns = [
        "AppKey",
        "Invitee Name",
        "Start Date",
        "Date + Week",
        "canal",
        "interview result",
        "background approved",
    ]
    interview_background_column_config = {
        "AppKey": column_config["AppKey"],
        "Start Date": column_config["Start Date"],
        "Date + Week": st.column_config.TextColumn(
            "Date + Week",
            help="Referencia rápida de fecha y semana ISO.",
            disabled=True,
        ),
    }
    if "canal" in column_config:
        interview_background_column_config["canal"] = column_config["canal"]
    if "background approved" in column_config:
        interview_background_column_config["background approved"] = column_config["background approved"]

    tab_general, tab_candidate, tab_attendance, tab_interview_background = st.tabs(
        ["Vista general", "Datos del candidato", "1. Asistencia", "2. Entrevista y background"]
    )

    with tab_general:
        st.subheader(f"Registros: {len(df_view)}")
        edited_general = st.data_editor(
            df_view,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_general",
        )
        if st.button("Aplicar cambios de esta vista a la tabla completa", key="apply_general"):
            _apply_edited_view(edited_general, "Vista general actualizada.")

    with tab_candidate:
        st.subheader(f"Datos del candidato: {len(df_view)} registros")
        st.caption("Aquí solo se muestran los datos base de contacto y programación del candidato.")
        candidate_df = df_view[candidate_columns].copy()
        edited_candidate = st.data_editor(
            candidate_df,
            column_config=candidate_column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_candidate",
        )
        if st.button("Aplicar cambios de datos del candidato", key="apply_candidate"):
            _apply_edited_view(edited_candidate, "Datos del candidato actualizados.")

    with tab_attendance:
        st.subheader(f"1. Asistencia: {len(df_view)} registros")
        st.caption("Aquí se concentra la asistencia del candidato y su estatus de entrevista.")
        attendance_df = df_view[attendance_columns].copy()
        edited_attendance = st.data_editor(
            attendance_df,
            column_config=attendance_column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_attendance",
        )
        if st.button("Aplicar cambios de asistencia", key="apply_attendance"):
            _apply_edited_view(edited_attendance, "Asistencia actualizada.")

    with tab_interview_background:
        interview_background_df = df_view[df_view["Interview status"] == "Conducted"].copy()
        st.subheader(f"2. Entrevista y background: {len(interview_background_df)} registros")
        st.caption("Aquí solo aparecen candidatos cuya asistencia ya quedó marcada como **Conducted**.")
        interview_background_df = interview_background_df[interview_background_columns]
        edited_interview_background = st.data_editor(
            interview_background_df,
            column_config=interview_background_column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_interview_background",
        )
        if st.button("Aplicar cambios de entrevista y background", key="apply_interview_background"):
            _apply_edited_view(
                edited_interview_background,
                "Entrevista y background actualizados.",
            )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_name = f"captura_{ts}.xlsx"
    buffer = BytesIO()
    st.session_state.df.to_excel(buffer, index=False, sheet_name="APP_PILOTO")
    buffer.seek(0)

    st.download_button(
        "Descargar salida nueva (Excel)",
        data=buffer.getvalue(),
        file_name=export_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if RAILWAY_ENVIRONMENT or APP_ENV == "railway":
        st.caption("Modo Railway: la exportación se descarga en tu navegador y no se guarda en disco del servidor.")
    else:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = EXPORT_DIR / export_name
        if st.button("Guardar copia local en exports/"):
            st.session_state.df.to_excel(out_path, index=False, sheet_name="APP_PILOTO")
            st.success(f"Guardado: {out_path.resolve()}")


if __name__ == "__main__":
    main()
