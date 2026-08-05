"""
OAXACA — Configuración compartida entre el panel web (Flask) y el bot (aiogram).

Aquí vive una sola vez todo lo que estaba duplicado: cliente de Supabase,
coordenadas del PDF, constantes, los candados globales y UN SOLO generador
de folios.
"""

import os
import sys
import logging
import threading
from datetime import datetime, date
from zoneinfo import ZoneInfo
from supabase import create_client, Client

# ===================== LOGGING =====================
sys.dont_write_bytecode = True
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("oaxaca")

# ===================== ZONA HORARIA =====================
TZ_OAXACA = ZoneInfo("America/Mexico_City")
TZ_MEXICO = TZ_OAXACA      # alias


def now_oaxaca() -> datetime:
    return datetime.now(TZ_OAXACA)


def today_oaxaca() -> date:
    return now_oaxaca().date()


def parse_date_any(value) -> date:
    import re
    if not value:
        raise ValueError("Fecha vacía")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ_OAXACA)
        else:
            value = value.astimezone(TZ_OAXACA)
        return value.date()
    s = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_OAXACA)
    else:
        dt = dt.astimezone(TZ_OAXACA)
    return dt.date()


# ===================== SUPABASE =====================
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://xsagwqepoljfsogusubw.supabase.co"
)
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== CONFIG GENERAL =====================
BOT_TOKEN            = os.getenv("BOT_TOKEN", "")
BASE_URL             = os.getenv(
    "BASE_URL",
    "https://oaxaca-gob-semovi.onrender.com"
).rstrip("/")
URL_CONSULTA_BASE    = BASE_URL      # el QR apunta al mismo servicio fusionado

OUTPUT_DIR           = "documentos"
PLANTILLA_PRINCIPAL  = "oaxaca_plantilla_imagen.pdf"
PLANTILLA_SECUNDARIA = "oaxacaverga.pdf"

ENTIDAD              = "oaxaca"
DIAS_PERMISO         = 30
HORAS_TIMER_BOT      = 36
PRECIO_PERMISO       = 500
PAGE_SIZE            = 100

ADMIN_USER           = os.getenv("ADMIN_USER", "Serg890105tm3")
ADMIN_PASS           = os.getenv("ADMIN_PASS", "Serg890105tm3")
SECRET_KEY           = os.getenv("SECRET_KEY", "oaxaca_segura_123456")

# ⚠️ PANEL Y BOT COMPARTEN LA SERIE "1".
# Antes cada uno la generaba distinto:
#   · Panel: escaneaba TODOS los folios de la entidad (lento, sin watermark)
#   · Bot:   usaba el watermark "OAX"
# Ahora hay UN solo generador (abajo) con watermark y candado.
FOLIO_PREFIJO        = "1"
FOLIO_WATERMARK_KEY  = "OAX"
FOLIO_INICIO         = 670       # si no hay watermark, arranca en 1670

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===================== CANDADOS GLOBALES =====================
# ⚠️ PDF_LOCK — NINGUNO de los dos archivos tenía candado de PDF. PyMuPDF no es
# thread-safe: el panel genera en el hilo de Flask y el bot en el threadpool de
# asyncio. Al compartir proceso, sin este candado dos permisos simultáneos se
# corrompen entre sí. Es el fix más importante de esta fusión.
PDF_LOCK   = threading.Lock()

# Serializa la asignación de folios entre panel y bot
FOLIO_LOCK = threading.Lock()

# ===================== COORDENADAS PDF OAXACA =====================
COORDS_OAXACA = {
    "folio":    (553, 96,  16, (1, 0, 0)),
    "fecha1":   (168, 130, 12, (0, 0, 0)),
    "fecha2":   (140, 540, 10, (0, 0, 0)),
    "marca":    (50,  215, 12, (0, 0, 0)),
    "serie":    (200, 258, 12, (0, 0, 0)),
    "linea":    (200, 215, 12, (0, 0, 0)),
    "motor":    (360, 258, 12, (0, 0, 0)),
    "anio":     (360, 215, 12, (0, 0, 0)),
    "color":    (50,  258, 12, (0, 0, 0)),
    "vigencia": (410, 130, 12, (0, 0, 0)),
    "nombre":   (133, 149, 10, (0, 0, 0)),
}

COORDS_QR = {"x": 486, "y": 100, "ancho": 100, "alto": 100}

COORDS_OAXACA_SEGUNDA = {
    "fecha_exp":    (136, 141, 10, (0, 0, 0)),
    "numero_serie": (136, 166, 10, (0, 0, 0)),
    "hora":         (146, 206, 10, (0, 0, 0)),
}

# ===================== TABLAS EDITABLES DESDE EL PANEL =====================
TABLAS_DISPONIBLES = {
    'folios_registrados': {
        'nombre':   'Folios Registrados',
        'pk_col':   'folio',
        'columnas': ['folio', 'marca', 'linea', 'anio', 'numero_serie', 'numero_motor',
                     'color', 'nombre', 'fecha_expedicion', 'fecha_vencimiento',
                     'entidad', 'estado', 'creado_por'],
    },
    'usuarios_oaxaca': {
        'nombre':   'Usuarios del Sistema',
        'pk_col':   'id',
        'columnas': ['id', 'username', 'password', 'folios_asignados', 'folios_usados'],
    },
    'folio_watermark': {
        'nombre':   'Watermark de Folios',
        'pk_col':   'prefijo',
        'columnas': ['prefijo', 'ultimo_asignado'],
    },
}

# Columnas que el editor trata como fecha (le pone selector de calendario)
COLUMNAS_FECHA = {
    'fecha_expedicion', 'fecha_vencimiento', 'fecha_comprobante',
    'fecha_detencion', 'created_at',
}


# ===================== GENERADOR DE FOLIO COMPARTIDO =====================
def _leer_watermark() -> int | None:
    try:
        r = supabase.table("folio_watermark") \
            .select("ultimo_asignado").eq("prefijo", FOLIO_WATERMARK_KEY).execute()
        return r.data[0]["ultimo_asignado"] if r.data else None
    except Exception as e:
        logger.error(f"[WATERMARK] leer: {e}")
        return None


def _guardar_watermark(numero: int):
    try:
        supabase.table("folio_watermark").upsert({
            "prefijo":         FOLIO_WATERMARK_KEY,
            "ultimo_asignado": numero
        }).execute()
    except Exception as e:
        logger.error(f"[WATERMARK] guardar: {e}")


def generar_folio_oaxaca() -> str:
    """
    ÚNICO generador de folios — lo usan el panel Y el bot.
    Bloques de 500 con una sola consulta (.in_) + watermark + candado.
    El contador nunca retrocede aunque se borren folios vencidos.
    """
    with FOLIO_LOCK:
        wm = _leer_watermark()
        if wm is not None:
            inicio = wm + 1
        else:
            # Primera vez: buscar el máximo existente en la BD
            try:
                r = supabase.table("folios_registrados").select("folio") \
                    .eq("entidad", ENTIDAD).like("folio", f"{FOLIO_PREFIJO}%").execute()
                nums = []
                for row in r.data or []:
                    f = str(row.get("folio", ""))
                    if f.startswith(FOLIO_PREFIJO) and len(f) > len(FOLIO_PREFIJO):
                        suf = f[len(FOLIO_PREFIJO):]
                        if suf.isdigit():
                            nums.append(int(suf))
                inicio = (max(nums) + 1) if nums else FOLIO_INICIO
            except Exception as e:
                logger.error(f"[FOLIO] init: {e}")
                inicio = FOLIO_INICIO

        BLOQUE = 500
        for _ in range(0, 10_000_000, BLOQUE):
            candidatos = [f"{FOLIO_PREFIJO}{inicio + i}" for i in range(BLOQUE)]
            try:
                resp = supabase.table("folios_registrados") \
                    .select("folio").in_("folio", candidatos).execute()
                ocupados = {r["folio"] for r in (resp.data or [])}
            except Exception as e:
                logger.error(f"[FOLIO] bloque: {e}")
                ocupados = set()

            logger.info(f"[FOLIO] bloque {inicio}–{inicio+BLOQUE-1}, ocupados={len(ocupados)}")
            for i, folio in enumerate(candidatos):
                if folio not in ocupados:
                    numero_final = inicio + i
                    _guardar_watermark(numero_final)
                    logger.info(f"[FOLIO] ✅ Asignado: {folio}")
                    return folio
            inicio += BLOQUE

        raise Exception("Sin folio disponible tras 10,000,000 intentos")


def leer_siguiente_folio() -> str:
    """Sólo informativo (para /health) — no reserva nada."""
    wm = _leer_watermark()
    n = (wm + 1) if wm is not None else FOLIO_INICIO
    return f"{FOLIO_PREFIJO}{n}"
