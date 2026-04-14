"""Columnas y reglas del piloto APP_PILOTO (misma intención que en AppSheet)."""

from __future__ import annotations

import os

# Orden fijo = encabezados de la hoja normalizada
COLUMNS = [
    "AppKey",
    "ENTREVISTADOR",
    "Invitee Name",
    "Correo",
    "Numeros",
    "Start Date",
    "Date + Week",
    "canal",
    "Docs before interview",
    "Interview status",
    "interview result",
    "background approved",
    "Driving test",
    "status Driver",
]

# Identidad del registro: la app trata cada fila por AppKey (no por la posición en la tabla).
RECORD_ID_COLUMNS = ("AppKey",)

# Búsqueda: puedes escribir AppKey, nombre, correo o número.
SEARCH_COLUMNS = ("AppKey", "Invitee Name", "Correo", "Numeros")

# Filtro por año / semana ISO: siempre sobre la fecha de la cita (entrevista)
DATE_FILTER_COLUMN = "Start Date"

CANAL_OPTIONS = [
    "Facebook",
    "DiDi Campaign",
    "DiDi Call Center",
    "DIDI Premier",
    "Referidos",
    "repeated",
    "LTO",
    "Indeed",
    "CompuTrabajo",
    "Portal del trabajo",
    "Nexiu",
    "Reingreso",
    "N/A",
]

ENUMS = {
    "canal": CANAL_OPTIONS,
    "Interview status": [
        "Not arrived",
        "Conducted",
        "cancel",
        "NA",
        "Reschedule by driver",
        "Reschedule by LAFA",
    ],
    "interview result": [],  # definir cuando tengas lista cerrada
    "background approved": ["yes", "no", "NA"],
    "Driving test": [
        "Approved",
        "Rejected",
        "NA",
        "without driving test",
    ],
    "status Driver": [
        "Interview not conducted",
        "Rejected",
        "Decline offer",
        "Hired",
        "Not arrived to onboarding",
        "Contract not signed",
        "Decline Process",
        "ready to onboard",
        "backgroun not approved",
        "Waiting for mornings shift",
        "Waiting",
    ],
}

# Vistas por etapa (equivalente a slices en AppSheet)
SLICES = {
    "Todas (base)": None,
    "SL_Asistencia": lambda df: df,
    "SL_Entrevista_BG": lambda df: df[df["Interview status"] == "Conducted"],
    "SL_Prueba_Manejo": lambda df: df[df["background approved"] == "yes"],
    "SL_Docs": lambda df: df[df["Driving test"] == "Approved"],
    "SL_Contratados": lambda df: df[df["status Driver"] == "Hired"],
}

# Libro principal: copia el archivo dentro de data/ con este nombre exacto
DATA_DIR = "data"
SOURCE_WORKBOOK = "Entrevistas_copia 10 abril (1).xlsx"

# Hoja del piloto (orden = preferencia). Ajusta si tu pestaña tiene otro nombre.
SHEET_FALLBACKS = (
    "APP_P",
    "APP_PILOTO",
)

# Si no existe el libro principal, se intenta este (compatibilidad)
LEGACY_EXCEL_PATH = "data/APP_PILOTO.xlsx"
LEGACY_SHEET = "APP_PILOTO"

# Fuente remota opcional sin Google Cloud:
# 1) comparte o publica la hoja en Google Sheets
# 2) usa GOOGLE_SHEET_CSV_URL
#    o GOOGLE_SHEET_ID + GOOGLE_SHEET_GID
GOOGLE_SHEET_CSV_URL = os.getenv("GOOGLE_SHEET_CSV_URL", "").strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_GID = os.getenv("GOOGLE_SHEET_GID", "0").strip() or "0"

# Entorno web / Railway
APP_ENV = os.getenv("APP_ENV", "").strip().lower()
RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "").strip()
