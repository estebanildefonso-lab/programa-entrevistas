"""Carga desde el Excel de entrevistas (hoja APP_P / APP_PILOTO)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from config import (
    CANAL_OPTIONS,
    COLUMNS,
    DATA_DIR,
    GOOGLE_SHEET_CSV_URL,
    GOOGLE_SHEET_GID,
    GOOGLE_SHEET_ID,
    LEGACY_EXCEL_PATH,
    LEGACY_SHEET,
    SHEET_FALLBACKS,
    SOURCE_WORKBOOK,
)


def _empty_row() -> dict:
    return {c: "" for c in COLUMNS}


def sample_dataframe(n: int = 12) -> pd.DataFrame:
    """Filas de demostración para ver la estructura sin archivo."""
    rows = []
    for i in range(1, n + 1):
        r = _empty_row()
        r["AppKey"] = f"APP-{i:05d}"
        r["Invitee Name"] = f"Candidato Demo {i}"
        r["Correo"] = f"candidato{i}@ejemplo.test"
        r["Numeros"] = f"5510000{i:03d}"
        r["Interview status"] = "Not arrived" if i % 3 else "Conducted"
        r["background approved"] = "NA"
        r["Driving test"] = "NA"
        r["status Driver"] = "Waiting"
        # Fechas de demo (2025 / 2026) para probar filtros por semana
        m = ((i - 1) % 12) + 1
        if i % 2:
            r["Start Date"] = f"2025-{m:02d}-10 09:00:00"
        else:
            r["Start Date"] = f"2026-{m:02d}-15 11:00:00"
        rows.append(r)
    return finalize_pilot_frame(pd.DataFrame(rows, columns=COLUMNS))


def _workbook_candidates() -> list[Path]:
    base = Path(DATA_DIR)
    return [
        base / SOURCE_WORKBOOK,
        Path(LEGACY_EXCEL_PATH),
    ]


def build_google_sheet_csv_url() -> str | None:
    """URL CSV pública/compartida del Google Sheet."""
    if GOOGLE_SHEET_CSV_URL:
        return GOOGLE_SHEET_CSV_URL
    if GOOGLE_SHEET_ID:
        return (
            f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export"
            f"?format=csv&gid={GOOGLE_SHEET_GID}"
        )
    return None


def resolve_workbook_path(path: str | Path | None = None) -> Path | None:
    """Primer .xlsx existente: ruta explícita, libro principal o legado."""
    if path is not None:
        p = Path(path)
        return p if p.is_file() else None
    for p in _workbook_candidates():
        if p.is_file():
            return p
    return None


def _pick_sheet_name(xl: pd.ExcelFile) -> str | None:
    names = xl.sheet_names
    if not names:
        return None
    for wanted in SHEET_FALLBACKS:
        if wanted in names:
            return wanted
    lower_map = {n.lower().strip(): n for n in names}
    for wanted in SHEET_FALLBACKS:
        key = wanted.lower().strip()
        if key in lower_map:
            return lower_map[key]
    for wanted in SHEET_FALLBACKS:
        w = wanted.lower()
        for n in names:
            if w in n.lower():
                return n
    return names[0]


def _strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _align_to_expected_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Alinea columnas del Excel a COLUMNS (mismo nombre o solo mayúsculas/minúsculas)."""
    df = _strip_columns(df)
    lower_to_actual = {}
    for c in df.columns:
        lower_to_actual.setdefault(c.lower(), c)
    aliases = {
        "Start Date": ("Start Date & Time",),
    }
    series_list = []
    for exp in COLUMNS:
        if exp in df.columns:
            series_list.append(df[exp])
        elif exp.lower() in lower_to_actual:
            series_list.append(df[lower_to_actual[exp.lower()]])
        elif exp in aliases:
            matched_alias = next(
                (
                    alias
                    for alias in aliases[exp]
                    if alias in df.columns or alias.lower() in lower_to_actual
                ),
                None,
            )
            if matched_alias is not None:
                actual = matched_alias if matched_alias in df.columns else lower_to_actual[matched_alias.lower()]
                series_list.append(df[actual])
            else:
                series_list.append(pd.Series([""] * len(df), dtype=object))
        else:
            series_list.append(pd.Series([""] * len(df), dtype=object))
    out = pd.concat(series_list, axis=1)
    out.columns = COLUMNS
    return out


DATE_PARSE_COLUMNS = ("Start Date",)

CANAL_NORMALIZATION = {
    "": "N/A",
    "n/a": "N/A",
    "na": "N/A",
    "facebook": "Facebook",
    "didi campaign": "DiDi Campaign",
    "didi call center": "DiDi Call Center",
    "didi premier": "DIDI Premier",
    "referidos": "Referidos",
    "repeated": "repeated",
    "lto": "LTO",
    "lto event": "LTO",
    "indeed": "Indeed",
    "computrabajo": "CompuTrabajo",
    "portal del trabajo": "Portal del trabajo",
    "nexiu": "Nexiu",
    "reingreso": "Reingreso",
    "not found": "N/A",
    "volante": "N/A",
}


def _normalize_canal_value(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    normalized = str(value).strip()
    if not normalized:
        return "N/A"
    canonical = CANAL_NORMALIZATION.get(normalized.lower())
    if canonical:
        return canonical
    return normalized if normalized in CANAL_OPTIONS else "N/A"


def _build_date_week_label(value) -> str:
    if value is None or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    iso = parsed.isocalendar()
    return f"{parsed.strftime('%d-%m-%Y')} · Semana {int(iso.week)}"


def finalize_pilot_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja fechas como datetime (para ISO año/semana) y el resto como texto para la tabla.
    Evita .astype(str) en fechas: rompe isocalendar() al filtrar por semana.
    """
    if df.empty:
        return df.copy()
    out = df.copy()
    for col in DATE_PARSE_COLUMNS:
        if col not in out.columns:
            continue
        ser = out[col]
        if pd.api.types.is_datetime64_any_dtype(ser):
            parsed = ser
        elif pd.api.types.is_numeric_dtype(ser):
            parsed = pd.to_datetime(ser, errors="coerce", unit="d", origin="1899-12-30")
        else:
            parsed = pd.to_datetime(ser, errors="coerce", dayfirst=False)
            if parsed.notna().sum() < max(1, len(ser) // 5):
                parsed = pd.to_datetime(ser, errors="coerce", dayfirst=True)
        out[col] = pd.to_datetime(parsed, errors="coerce").dt.date
    if "Date + Week" in out.columns and "Start Date" in out.columns:
        current_labels = out["Date + Week"].copy()
        generated_labels = out["Start Date"].map(_build_date_week_label)
        missing_mask = current_labels.isna() | (current_labels.astype(str).str.strip() == "")
        out.loc[missing_mask, "Date + Week"] = generated_labels[missing_mask]
    for col in COLUMNS:
        if col in DATE_PARSE_COLUMNS:
            continue
        out[col] = out[col].map(lambda x: "" if (x is None or (isinstance(x, float) and pd.isna(x))) else str(x).strip())
        out[col] = out[col].replace({"nan": "", "NaT": "", "<NA>": ""})
    if "canal" in out.columns:
        out["canal"] = out["canal"].map(_normalize_canal_value)
    return out


def load_workbook_meta(path: Path) -> tuple[list[str], str | None]:
    xl = pd.ExcelFile(path, engine="openpyxl")
    sheet = _pick_sheet_name(xl)
    return xl.sheet_names, sheet


def load_from_google_sheet() -> pd.DataFrame | None:
    """
    Lee un Google Sheet accesible por URL CSV pública o compartida.
    No requiere Google Cloud ni credenciales si la hoja se puede descargar.
    """
    csv_url = build_google_sheet_csv_url()
    if not csv_url:
        return None
    try:
        request = Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            payload = response.read()
        df = pd.read_csv(BytesIO(payload))
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    except Exception:
        return None
    if df is None:
        return None
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    aligned = _align_to_expected_columns(df)
    return finalize_pilot_frame(aligned)


def load_from_excel(path: str | Path | None = None) -> pd.DataFrame | None:
    """
    Lee la hoja APP_P (o la primera coincidencia en SHEET_FALLBACKS).
    Devuelve None si no hay archivo o falla la lectura.
    """
    p = resolve_workbook_path(path)
    if p is None:
        return None
    try:
        xl = pd.ExcelFile(p, engine="openpyxl")
        sheet = _pick_sheet_name(xl)
        if sheet is None:
            return None
        df = pd.read_excel(xl, sheet_name=sheet, engine="openpyxl")
    except Exception:
        try:
            df = pd.read_excel(p, sheet_name=LEGACY_SHEET, engine="openpyxl")
        except Exception:
            return None
    if df is None:
        return None
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    aligned = _align_to_expected_columns(df)
    return finalize_pilot_frame(aligned)


def load_data_source(path: str | Path | None = None) -> pd.DataFrame | None:
    """
    Prioridad:
    1. Google Sheets público/compartido por CSV
    2. Excel local
    """
    remote = load_from_google_sheet()
    if remote is not None:
        return remote
    return load_from_excel(path)


def load_status(path: str | Path | None = None) -> dict:
    """Información para la UI: fuente usada y detalles."""
    csv_url = build_google_sheet_csv_url()
    if csv_url:
        loaded = load_from_google_sheet()
        if loaded is not None:
            return {
                "ok": True,
                "source_type": "google_sheet",
                "path": csv_url,
                "sheet": GOOGLE_SHEET_GID,
                "sheets": [],
                "message": "Datos desde Google Sheets (CSV remoto).",
            }
        return {
            "ok": False,
            "source_type": "google_sheet",
            "path": csv_url,
            "sheet": GOOGLE_SHEET_GID,
            "sheets": [],
            "message": "No se pudo leer Google Sheets. Revisa que el enlace CSV sea público o accesible.",
        }

    p = resolve_workbook_path(path)
    if p is None:
        return {
            "ok": False,
            "source_type": "excel",
            "path": None,
            "sheet": None,
            "sheets": [],
            "message": f"No se encontró el libro. Colócalo en: {Path(DATA_DIR) / SOURCE_WORKBOOK}",
        }
    try:
        sheets, picked = load_workbook_meta(p)
        return {
            "ok": True,
            "source_type": "excel",
            "path": str(p.resolve()),
            "sheet": picked,
            "sheets": sheets,
            "message": f"Libro: {p.name} · Hoja: {picked}",
        }
    except Exception as e:
        return {
            "ok": False,
            "source_type": "excel",
            "path": str(p.resolve()),
            "sheet": None,
            "sheets": [],
            "message": f"Error al leer Excel: {e}",
        }


def ensure_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None:
        return sample_dataframe()
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    aligned = _align_to_expected_columns(df)
    return finalize_pilot_frame(aligned)
