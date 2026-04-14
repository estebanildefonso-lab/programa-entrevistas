# Programa de entrevistas en Railway

Esta version del programa esta preparada para publicarse como web app en Railway sin usar Google Cloud.

## Como funciona la fuente de datos

La app intenta cargar datos en este orden:

1. `Google Sheets` por CSV remoto
2. `Excel` local dentro de `data/`
3. `muestra demo`

## Opcion recomendada sin Google Cloud

Usa un Google Sheet como fuente remota de lectura.

Tienes dos formas:

### Opcion A: URL CSV completa

Define:

```env
GOOGLE_SHEET_CSV_URL=https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0
```

### Opcion B: Spreadsheet ID + gid

Define:

```env
GOOGLE_SHEET_ID=TU_SPREADSHEET_ID
GOOGLE_SHEET_GID=0
```

La app construira la URL CSV automaticamente.

## Importante sobre Google Sheets

Como no vamos a usar Google Cloud ni credenciales, la hoja debe poder descargarse por URL CSV.

La forma mas simple es:

1. abrir el Google Sheet
2. compartirlo como `Cualquiera con el enlace`
3. dar permiso de `Lector`

Si en tu cuenta no basta con compartirlo, usa `Archivo > Compartir > Publicar en la web` y publica la pestaña que quieras leer.

## Variables de entorno en Railway

Configura al menos una de estas opciones:

```env
GOOGLE_SHEET_CSV_URL=
```

o

```env
GOOGLE_SHEET_ID=
GOOGLE_SHEET_GID=0
```

Y opcionalmente:

```env
APP_ENV=railway
```

## Despliegue en Railway

### Opcion simple

1. Sube esta carpeta a un repositorio Git.
2. En Railway crea un nuevo proyecto.
3. Conecta el repositorio.
4. En la configuracion del servicio, usa como `Root Directory`:

```text
programa-entrevistas
```

5. Railway detectara el `Dockerfile` y construira la app.
6. Agrega tus variables de entorno.
7. Despliega.

## Comportamiento de exportacion

En Railway la app no guarda el Excel exportado en disco del servidor. En su lugar:

- genera el Excel en memoria
- lo descarga directamente al navegador del usuario

En local, ademas de la descarga, puedes seguir guardando una copia en `exports/`.

## Ejecucion local

```bash
cd programa-entrevistas
source ../.venv/bin/activate
streamlit run app.py
```

## Formato esperado de columnas

La hoja remota debe tener columnas alineadas con el piloto. La app intenta mapearlas por nombre, ignorando mayusculas/minusculas.

## Limitacion importante

En esta version sin Google Cloud:

- la lectura desde Google Sheets es de solo lectura
- no se escriben cambios de vuelta al Google Sheet
- la app sigue trabajando en sesion y exportando un nuevo Excel

Esto mantiene el comportamiento actual del piloto, pero ya funcionando como pagina web.
