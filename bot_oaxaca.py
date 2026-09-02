"""
OAXACA — Bot de Telegram (aiogram).

Cambios respecto a tu archivo original:
  · Ya NO crea su propia app FastAPI (eso lo hace main.py)
  · ⚠️ SE LE AGREGÓ EL CANDADO DE PDF (antes no tenía ninguno)
  · El folio usa el generador compartido con el panel (watermark + candado)
  · Se quitaron las rutas /consulta/{folio} y /consulta_folio del bot:
    CHOCABAN con las del panel. Gana el panel, que usa tus plantillas.
  · Se agregó snapshot_timers() para que el panel web liste los timers
  · El lifespan se partió en arranque_bot() / cierre_bot()
Los handlers, el FSM y las coordenadas quedaron idénticos.
"""

from datetime import datetime, timedelta
import os
import asyncio
import aiohttp
import qrcode
import fitz
from io import BytesIO

from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import (FSInputFile, ContentType, InlineKeyboardMarkup,
                           InlineKeyboardButton, CallbackQuery)

from config_oaxaca import (
    supabase, logger, BOT_TOKEN, BASE_URL, URL_CONSULTA_BASE,
    OUTPUT_DIR, PLANTILLA_PRINCIPAL, PLANTILLA_SECUNDARIA,
    PRECIO_PERMISO, DIAS_PERMISO, HORAS_TIMER_BOT, TZ_MEXICO,
    PDF_LOCK, COORDS_OAXACA, COORDS_QR, COORDS_OAXACA_SEGUNDA,
    FOLIO_PREFIJO, generar_folio_oaxaca, leer_siguiente_folio,
)

PLANTILLA_OAXACA         = PLANTILLA_PRINCIPAL
PLANTILLA_OAXACA_SEGUNDA = PLANTILLA_SECUNDARIA
coords_oaxaca            = COORDS_OAXACA
coords_qr_dinamico       = COORDS_QR
coords_oaxaca_segunda    = COORDS_OAXACA_SEGUNDA

_bot_session = AiohttpSession(timeout=aiohttp.ClientTimeout(total=300))
bot     = Bot(token=BOT_TOKEN, session=_bot_session)
storage = MemoryStorage()
dp      = Dispatcher(storage=storage)

# ------------ TIMER MANAGEMENT ------------
timers_activos       = {}
user_folios          = {}
pending_comprobantes = {}
TOTAL_MINUTOS_TIMER  = HORAS_TIMER_BOT * 60

# ⚠️ El candado de PDF es el COMPARTIDO con el panel.
# ANTES DE LA FUSIÓN NI EL BOT NI EL PANEL TENÍAN CANDADO.
_pdf_generation_lock = PDF_LOCK

_folio_lock = asyncio.Lock()


async def obtener_siguiente_folio() -> str:
    """Usa el generador compartido (mismo candado que el panel)."""
    async with _folio_lock:
        return await asyncio.to_thread(generar_folio_oaxaca)


# ------------ TIMERS ------------
async def eliminar_folio_automatico_oaxaca(folio: str):
    try:
        user_id = timers_activos.get(folio, {}).get("user_id")
        await asyncio.to_thread(lambda:
            supabase.table("folios_registrados").delete().eq("folio", folio).execute()
        )
        if user_id:
            await bot.send_message(user_id,
                f"TIEMPO AGOTADO - OAXACA\n\n"
                f"El folio {folio} ha sido eliminado del sistema por no completar el pago en {HORAS_TIMER_BOT} horas.\n\n"
                f"Para generar otro permiso use /banamex")
        limpiar_timer_folio(folio)
    except Exception as e:
        print(f"Error eliminando folio Oaxaca {folio}: {e}")


async def enviar_recordatorio_oaxaca(folio: str, minutos_restantes: int):
    try:
        if folio not in timers_activos:
            return
        user_id = timers_activos[folio]["user_id"]
        await bot.send_message(user_id,
            f"RECORDATORIO DE PAGO - OAXACA\n\n"
            f"Folio: {folio}\n"
            f"Tiempo restante: {minutos_restantes} minutos\n"
            f"Monto: ${PRECIO_PERMISO} pesos\n\n"
            f"Envie su comprobante de pago (imagen) para validar el tramite.\n\n"
            f"Para generar otro permiso use /banamex")
    except Exception as e:
        print(f"Error enviando recordatorio Oaxaca para folio {folio}: {e}")


async def iniciar_timer_pago_oaxaca(user_id: int, folio: str, nombre: str = ""):
    async def timer_task():
        print(f"[TIMER OAXACA] Iniciado folio {folio}, usuario {user_id} ({HORAS_TIMER_BOT}h)")
        await asyncio.sleep(34.5 * 3600)
        if folio not in timers_activos: return
        await enviar_recordatorio_oaxaca(folio, 90)
        await asyncio.sleep(30 * 60)
        if folio not in timers_activos: return
        await enviar_recordatorio_oaxaca(folio, 60)
        await asyncio.sleep(30 * 60)
        if folio not in timers_activos: return
        await enviar_recordatorio_oaxaca(folio, 30)
        await asyncio.sleep(20 * 60)
        if folio not in timers_activos: return
        await enviar_recordatorio_oaxaca(folio, 10)
        await asyncio.sleep(10 * 60)
        if folio in timers_activos:
            print(f"[TIMER OAXACA] Expirado folio {folio} - eliminando")
            await eliminar_folio_automatico_oaxaca(folio)

    task = asyncio.create_task(timer_task())
    timers_activos[folio] = {
        "task":       task,
        "user_id":    user_id,
        "start_time": datetime.now(),
        "nombre":     nombre,
    }
    user_folios.setdefault(user_id, []).append(folio)
    print(f"[SISTEMA OAXACA] Timer {HORAS_TIMER_BOT}h iniciado folio {folio} ({nombre}), total: {len(timers_activos)}")


def cancelar_timer_folio(folio: str):
    if folio in timers_activos:
        try:
            timers_activos[folio]["task"].cancel()
        except Exception:
            pass
        user_id = timers_activos[folio]["user_id"]
        del timers_activos[folio]
        if user_id in user_folios and folio in user_folios[user_id]:
            user_folios[user_id].remove(folio)
            if not user_folios[user_id]:
                del user_folios[user_id]
        print(f"[SISTEMA OAXACA] Timer cancelado folio {folio}")
        return True
    return False


def limpiar_timer_folio(folio: str):
    if folio in timers_activos:
        user_id = timers_activos[folio]["user_id"]
        del timers_activos[folio]
        if user_id in user_folios and folio in user_folios[user_id]:
            user_folios[user_id].remove(folio)
            if not user_folios[user_id]:
                del user_folios[user_id]


def obtener_folios_usuario(user_id: int) -> list:
    return user_folios.get(user_id, [])


def snapshot_timers() -> list:
    """Lista los timers activos para que el PANEL WEB pueda mostrarlos."""
    salida = []
    for folio, info in timers_activos.items():
        mins = max(0, TOTAL_MINUTOS_TIMER - int(
            (datetime.now() - info["start_time"]).total_seconds() / 60))
        salida.append({
            "folio":    folio,
            "nombre":   info.get("nombre", ""),
            "user_id":  info.get("user_id"),
            "restante": f"{mins//60}h {mins%60}min",
            "minutos":  mins,
        })
    salida.sort(key=lambda x: x["minutos"])
    return salida


# ------------ FSM ------------
class PermisoForm(StatesGroup):
    marca  = State()
    linea  = State()
    anio   = State()
    serie  = State()
    motor  = State()
    color  = State()
    nombre = State()


# ------------ QR ------------
def generar_qr_dinamico_oaxaca(folio):
    try:
        url = f"{URL_CONSULTA_BASE}/consulta/{folio}"
        qr  = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_M,
                            box_size=4, border=1)
        qr.add_data(url); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        print(f"[QR OAXACA] {folio} -> {url}")
        return img, url
    except Exception as e:
        print(f"[ERROR QR] {e}")
        return None, None


# ------------ PDF UNIFICADO ------------
def generar_pdf_oaxaca_completo(folio, datos, fecha_exp, fecha_ven):
    """
    ⚠️ FIX DE LA FUSIÓN: todo dentro del candado compartido.
    PyMuPDF no es thread-safe y el panel también genera en hilos.
    """
    with _pdf_generation_lock:
        print(f"[OAXACA] Generando PDF para folio: {folio}")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        try:
            doc_original = fitz.open(PLANTILLA_OAXACA)
            pg1          = doc_original[0]
            f1           = fecha_exp.strftime("%d/%m/%Y")
            f_ven        = fecha_ven.strftime("%d/%m/%Y")

            pg1.insert_text(coords_oaxaca["folio"][:2],    str(folio), fontsize=coords_oaxaca["folio"][2],    color=coords_oaxaca["folio"][3])
            pg1.insert_text(coords_oaxaca["fecha1"][:2],   f1,         fontsize=coords_oaxaca["fecha1"][2],   color=coords_oaxaca["fecha1"][3])
            pg1.insert_text(coords_oaxaca["fecha2"][:2],   f1,         fontsize=coords_oaxaca["fecha2"][2],   color=coords_oaxaca["fecha2"][3])
            pg1.insert_text(coords_oaxaca["vigencia"][:2], f_ven,      fontsize=coords_oaxaca["vigencia"][2], color=coords_oaxaca["vigencia"][3])
            pg1.insert_text(coords_oaxaca["nombre"][:2],   str(datos.get("nombre", "")), fontsize=coords_oaxaca["nombre"][2], color=coords_oaxaca["nombre"][3])

            for key in ["marca", "serie", "linea", "motor", "anio", "color"]:
                if key in datos:
                    x, y, s, col = coords_oaxaca[key]
                    pg1.insert_text((x, y), str(datos[key]), fontsize=s, color=col)

            img_qr, _ = generar_qr_dinamico_oaxaca(folio)
            if img_qr:
                buf = BytesIO(); img_qr.save(buf, format="PNG"); buf.seek(0)
                qr_pix = fitz.Pixmap(buf.read())
                x_qr, y_qr = coords_qr_dinamico["x"], coords_qr_dinamico["y"]
                w_qr, h_qr = coords_qr_dinamico["ancho"], coords_qr_dinamico["alto"]
                pg1.insert_image(fitz.Rect(x_qr, y_qr, x_qr+w_qr, y_qr+h_qr), pixmap=qr_pix, overlay=True)

            doc_segunda = fitz.open(PLANTILLA_OAXACA_SEGUNDA)
            pg2         = doc_segunda[0]
            pg2.insert_text(coords_oaxaca_segunda["fecha_exp"][:2],    fecha_exp.strftime("%d/%m/%Y"), fontsize=coords_oaxaca_segunda["fecha_exp"][2],    color=coords_oaxaca_segunda["fecha_exp"][3])
            pg2.insert_text(coords_oaxaca_segunda["numero_serie"][:2], str(datos.get("serie", "")),    fontsize=coords_oaxaca_segunda["numero_serie"][2], color=coords_oaxaca_segunda["numero_serie"][3])
            pg2.insert_text(coords_oaxaca_segunda["hora"][:2],         fecha_exp.strftime("%H:%M:%S"), fontsize=coords_oaxaca_segunda["hora"][2],         color=coords_oaxaca_segunda["hora"][3])

            doc_final = fitz.open()
            doc_final.insert_pdf(doc_original, from_page=0, to_page=0)
            doc_final.insert_pdf(doc_segunda,  from_page=0, to_page=0)

            salida = os.path.join(OUTPUT_DIR, f"{folio}_oaxaca_completo.pdf")
            doc_final.save(salida)
            doc_original.close(); doc_segunda.close(); doc_final.close()

            print(f"[OAXACA] PDF generado: {salida}")
            return salida

        except Exception as e:
            print(f"[ERROR PDF OAXACA] {e}")
            salida = os.path.join(OUTPUT_DIR, f"{folio}_oaxaca_completo.pdf")
            fb = fitz.open()
            fb.new_page().insert_text((50, 50), f"ERROR - Folio: {folio}", fontsize=12)
            fb.save(salida); fb.close()
            return salida


# ============ BACKGROUND TASK =================================================
async def _generar_y_enviar_background(chat_id: int, datos: dict, user_id: int,
                                       folio: str, nombre: str,
                                       hoy: datetime, fecha_ven: datetime):
    """PDF, insert y envío en background. El webhook ya respondió."""
    try:
        pdf_path = await asyncio.to_thread(
            generar_pdf_oaxaca_completo, folio, datos, hoy, fecha_ven
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Validar Admin",  callback_data=f"validar_{folio}"),
            InlineKeyboardButton(text="Detener Timer",  callback_data=f"detener_{folio}")
        ]])

        await bot.send_document(
            chat_id,
            FSInputFile(pdf_path),
            caption=(
                f"PERMISO OFICIAL OAXACA\n"
                f"Folio: {folio}\n"
                f"Titular: {nombre}\n"
                f"Vigencia: {DIAS_PERMISO} dias\n"
                f"PDF unificado (2 paginas)\n"
                f"QR dinamico incluido\n\n"
                f"TIMER ACTIVO ({HORAS_TIMER_BOT} horas)"
            ),
            reply_markup=keyboard
        )

        folio_final = folio

        def _insert(folio_usar: str):
            supabase.table("folios_registrados").insert({
                "folio":             folio_usar,
                "marca":             datos["marca"],
                "linea":             datos["linea"],
                "anio":              datos["anio"],
                "numero_serie":      datos["serie"],
                "numero_motor":      datos["motor"],
                "nombre":            nombre,
                "color":             datos["color"],
                "fecha_expedicion":  hoy.date().isoformat(),
                "fecha_vencimiento": fecha_ven.date().isoformat(),
                "entidad":           "oaxaca",
                "estado":            "PENDIENTE",
                "user_id":           user_id,
                "creado_por":        f"BOT_TG_{datos.get('username', 'unknown')}",
            }).execute()

        for _ in range(20):
            try:
                await asyncio.to_thread(_insert, folio_final)
                print(f"[DB] Insertado folio {folio_final}")
                break
            except Exception as e:
                em = str(e).lower()
                if any(k in em for k in ("duplicate", "unique", "23505")):
                    print(f"[DB] Folio {folio_final} duplicado — obteniendo nuevo...")
                    folio_final = await obtener_siguiente_folio()
                else:
                    print(f"[DB ERROR] {e}")
                    break

        await iniciar_timer_pago_oaxaca(user_id, folio_final, nombre)

        await bot.send_message(user_id,
            f"INSTRUCCIONES DE PAGO OAXACA\n\n"
            f"Folio: {folio_final}\n"
            f"Monto: ${PRECIO_PERMISO} pesos\n"
            f"Tiempo limite: {HORAS_TIMER_BOT} HORAS\n\n"
            f"TRANSFERENCIA BANCARIA:\n"
            f"Banco: AZTECA\n"
            f"Titular: ADMINISTRADOR OAXACA\n"
            f"Cuenta: 127180013037579543\n"
            f"Concepto: Permiso {folio_final}\n\n"
            f"Envie foto del comprobante de pago.\n"
            f"El folio sera eliminado si no paga en {HORAS_TIMER_BOT} horas.\n\n"
            f"Para generar otro permiso use /banamex\n"
            f"QR incluido para consulta: {URL_CONSULTA_BASE}/consulta/{folio_final}"
        )

    except Exception as e:
        print(f"[ERROR background] folio {folio}: {e}")
        try:
            await bot.send_message(user_id,
                f"ERROR al generar el documento: {e}\n\nUse /banamex para reintentar.")
        except Exception:
            pass


# ------------ HANDLERS ------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Sistema Digital de Permisos OAXACA\n"
        "Servicio oficial automatizado para tramites vehiculares\n\n"
        f"Costo: ${PRECIO_PERMISO} pesos\n"
        f"Tiempo limite para pago: {HORAS_TIMER_BOT} horas\n\n"
        "PDF unificado con QR dinamico + folio"
    )


@dp.message(Command("banamex"))
async def chuleta_cmd(message: types.Message, state: FSMContext):
    await state.clear()

    mis_folios = [f for f in timers_activos
                  if timers_activos[f].get("user_id") == message.from_user.id]

    if mis_folios:
        texto   = "FOLIOS ACTIVOS CON TIMER\n" + "─" * 28 + "\n\n"
        botones = []
        for f in mis_folios:
            info   = timers_activos[f]
            nombre = info.get("nombre", "Sin nombre")
            mins   = max(0, TOTAL_MINUTOS_TIMER - int((datetime.now() - info["start_time"]).total_seconds() / 60))
            texto += f"Folio: {f}\n{nombre}\n{mins//60}h {mins%60}min restantes\n\n"
            botones.append([InlineKeyboardButton(
                text=f"Detener timer {f}", callback_data=f"detener_{f}")])
        await message.answer(texto.strip(), reply_markup=InlineKeyboardMarkup(inline_keyboard=botones))
        await message.answer(
            f"Para NUEVO permiso escribe la MARCA del vehiculo:\n\nCosto: ${PRECIO_PERMISO} | Plazo: {HORAS_TIMER_BOT}h")
    else:
        await message.answer(
            f"TRAMITE DE PERMISO OAXACA\n\n"
            f"Costo: ${PRECIO_PERMISO} pesos\n"
            f"Tiempo para pagar: {HORAS_TIMER_BOT} horas\n\n"
            "Comenzamos con la MARCA del vehiculo:")

    await state.set_state(PermisoForm.marca)


@dp.message(PermisoForm.marca)
async def get_marca(message: types.Message, state: FSMContext):
    await state.update_data(marca=message.text.strip().upper())
    await message.answer("LINEA del vehiculo:")
    await state.set_state(PermisoForm.linea)


@dp.message(PermisoForm.linea)
async def get_linea(message: types.Message, state: FSMContext):
    await state.update_data(linea=message.text.strip().upper())
    await message.answer("ANO del vehiculo (4 digitos):")
    await state.set_state(PermisoForm.anio)


@dp.message(PermisoForm.anio)
async def get_anio(message: types.Message, state: FSMContext):
    anio = message.text.strip()
    if not anio.isdigit() or len(anio) != 4:
        await message.answer("El ano debe ser de 4 digitos (ej: 2020):")
        return
    await state.update_data(anio=anio)
    await message.answer("NUMERO DE SERIE del vehiculo:")
    await state.set_state(PermisoForm.serie)


@dp.message(PermisoForm.serie)
async def get_serie(message: types.Message, state: FSMContext):
    await state.update_data(serie=message.text.strip().upper())
    await message.answer("NUMERO DE MOTOR:")
    await state.set_state(PermisoForm.motor)


@dp.message(PermisoForm.motor)
async def get_motor(message: types.Message, state: FSMContext):
    await state.update_data(motor=message.text.strip().upper())
    await message.answer("COLOR del vehiculo:")
    await state.set_state(PermisoForm.color)


@dp.message(PermisoForm.color)
async def get_color(message: types.Message, state: FSMContext):
    await state.update_data(color=message.text.strip().upper())
    await message.answer("NOMBRE COMPLETO del solicitante:")
    await state.set_state(PermisoForm.nombre)


@dp.message(PermisoForm.nombre)
async def get_nombre(message: types.Message, state: FSMContext):
    datos  = await state.get_data()
    nombre = message.text.strip().upper()
    datos["nombre"]   = nombre
    datos["username"] = message.from_user.username or "Sin username"

    try:
        folio = await obtener_siguiente_folio()
    except Exception as e:
        await message.answer(f"ERROR generando folio: {e}\n\nPara generar otro permiso use /banamex")
        await state.clear()
        return

    hoy       = datetime.now(TZ_MEXICO)
    fecha_ven = hoy + timedelta(days=DIAS_PERMISO - 1)

    # Limpia estado ANTES — evita re-triggers si Telegram reintenta
    await state.clear()

    await message.answer(
        f"PROCESANDO PERMISO OAXACA...\n"
        f"Folio: {folio}\n"
        f"Titular: {nombre}\n\n"
        "Generando PDF unificado con QR dinamico..."
    )

    asyncio.create_task(
        _generar_y_enviar_background(
            message.chat.id, datos, message.from_user.id,
            folio, nombre, hoy, fecha_ven
        )
    )


# ------------ CALLBACKS ------------
@dp.callback_query(lambda c: c.data and c.data.startswith("validar_"))
async def callback_validar_admin(callback: CallbackQuery):
    folio = callback.data.replace("validar_", "")
    if not folio.startswith(FOLIO_PREFIJO):
        await callback.answer("Folio invalido", show_alert=True); return
    if folio in timers_activos:
        uid    = timers_activos[folio]["user_id"]
        nombre = timers_activos[folio].get("nombre", "")
        cancelar_timer_folio(folio)
        try:
            await asyncio.to_thread(lambda: supabase.table("folios_registrados").update({
                "estado": "VALIDADO_ADMIN", "fecha_comprobante": datetime.now().isoformat()
            }).eq("folio", folio).execute())
        except Exception as e:
            print(f"Error BD validar {folio}: {e}")
        await callback.answer("Folio validado por administracion", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        try:
            await bot.send_message(uid,
                f"PAGO VALIDADO POR ADMINISTRACION - OAXACA\n"
                f"Folio: {folio}\nTitular: {nombre}\n"
                f"Tu permiso esta activo para circular.\n\n"
                f"Para generar otro permiso use /banamex")
        except Exception as e:
            print(f"Error notificando usuario {uid}: {e}")
    else:
        await callback.answer("Folio no encontrado en timers activos", show_alert=True)


@dp.callback_query(lambda c: c.data and c.data.startswith("detener_"))
async def callback_detener_timer(callback: CallbackQuery):
    folio = callback.data.replace("detener_", "")
    if folio in timers_activos:
        nombre = timers_activos[folio].get("nombre", "")
        cancelar_timer_folio(folio)
        try:
            await asyncio.to_thread(lambda: supabase.table("folios_registrados").update({
                "estado": "TIMER_DETENIDO", "fecha_detencion": datetime.now().isoformat()
            }).eq("folio", folio).execute())
        except Exception as e:
            print(f"Error BD detener {folio}: {e}")
        await callback.answer("Timer detenido exitosamente", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"TIMER DETENIDO\nFolio: {folio}\nTitular: {nombre}\n\n"
            f"El folio ya NO se eliminara automaticamente.\n\n"
            f"Para generar otro permiso use /banamex")
    else:
        await callback.answer("Timer ya no esta activo", show_alert=True)


# ------------ ADMIN SERO ------------
@dp.message(lambda message: message.text and message.text.strip().upper().startswith("SERO"))
async def codigo_admin_sero(message: types.Message):
    texto = message.text.strip().upper()
    if len(texto) <= 4:
        await message.answer(
            "FORMATO INCORRECTO\n\n"
            "Use el formato: SERO[folio]\nEjemplo: SERO1770\n\n"
            "Para generar otro permiso use /banamex"); return

    folio_admin = texto[4:]
    if not folio_admin.startswith(FOLIO_PREFIJO):
        await message.answer(
            f"FOLIO INVALIDO\n\nEl folio {folio_admin} no es OAXACA (debe iniciar con {FOLIO_PREFIJO}).\n\n"
            f"Para generar otro permiso use /banamex"); return

    if folio_admin in timers_activos:
        uid    = timers_activos[folio_admin]["user_id"]
        nombre = timers_activos[folio_admin].get("nombre", "")
        cancelar_timer_folio(folio_admin)
        try:
            await asyncio.to_thread(lambda: supabase.table("folios_registrados").update({
                "estado": "VALIDADO_ADMIN", "fecha_comprobante": datetime.now().isoformat()
            }).eq("folio", folio_admin).execute())
        except Exception as e:
            print(f"Error BD SERO {folio_admin}: {e}")
        await message.answer(
            f"VALIDACION OK\nFolio: {folio_admin}\nTitular: {nombre}\nTimer cancelado.\n\n"
            f"Para generar otro permiso use /banamex")
        try:
            await bot.send_message(uid,
                f"PAGO VALIDADO POR ADMINISTRACION - OAXACA\n"
                f"Folio: {folio_admin}\nTu permiso esta activo.\n\n"
                f"Para generar otro permiso use /banamex")
        except Exception as e:
            print(f"Error notificando usuario {uid}: {e}")
    else:
        await message.answer(
            f"FOLIO NO LOCALIZADO EN TIMERS ACTIVOS\n"
            f"Folio: {folio_admin}\n\n"
            f"Para generar otro permiso use /banamex")


# ------------ COMPROBANTE FOTO ------------
@dp.message(lambda message: message.content_type == ContentType.PHOTO)
async def recibir_comprobante_oaxaca(message: types.Message):
    uid    = message.from_user.id
    folios = obtener_folios_usuario(uid)
    if not folios:
        await message.answer(
            "No tienes folios pendientes de pago en Oaxaca.\n\n"
            "Para generar otro permiso use /banamex"); return
    if len(folios) > 1:
        lista = '\n'.join([f"- {f}" for f in folios])
        pending_comprobantes[uid] = "waiting_folio"
        await message.answer(
            f"MULTIPLES FOLIOS OAXACA\n\n{lista}\n\n"
            f"Responde con el NUMERO DE FOLIO para este comprobante.\n\n"
            f"Para generar otro permiso use /banamex"); return
    folio = folios[0]; cancelar_timer_folio(folio)
    try:
        await asyncio.to_thread(lambda: supabase.table("folios_registrados").update({
            "estado": "COMPROBANTE_ENVIADO", "fecha_comprobante": datetime.now().isoformat()
        }).eq("folio", folio).execute())
    except Exception as e:
        print(f"Error actualizando estado: {e}")
    await message.answer(
        f"COMPROBANTE RECIBIDO\n\nFolio: {folio}\nTimer detenido.\n\n"
        f"Para generar otro permiso use /banamex")


@dp.message(lambda message: message.from_user.id in pending_comprobantes
            and pending_comprobantes[message.from_user.id] == "waiting_folio")
async def especificar_folio_comprobante(message: types.Message):
    uid                = message.from_user.id
    folio_especificado = message.text.strip().upper()
    folios_usuario     = obtener_folios_usuario(uid)
    if folio_especificado not in folios_usuario:
        await message.answer(
            "Ese folio no esta entre tus expedientes activos.\n\n"
            "Para generar otro permiso use /banamex"); return
    cancelar_timer_folio(folio_especificado)
    del pending_comprobantes[uid]
    try:
        await asyncio.to_thread(lambda: supabase.table("folios_registrados").update({
            "estado": "COMPROBANTE_ENVIADO", "fecha_comprobante": datetime.now().isoformat()
        }).eq("folio", folio_especificado).execute())
    except Exception as e:
        print(f"Error actualizando estado: {e}")
    await message.answer(
        f"Comprobante asociado.\nFolio: {folio_especificado}\nTimer detenido.\n\n"
        f"Para generar otro permiso use /banamex")


@dp.message(Command("folios"))
async def ver_folios_activos(message: types.Message):
    uid    = message.from_user.id
    folios = obtener_folios_usuario(uid)
    if not folios:
        await message.answer(
            "NO HAY FOLIOS ACTIVOS OAXACA\n\n"
            "Para generar otro permiso use /banamex"); return
    lista   = []
    botones = []
    for folio in folios:
        if folio in timers_activos:
            info   = timers_activos[folio]
            nombre = info.get("nombre", "Sin nombre")
            mins   = max(0, TOTAL_MINUTOS_TIMER - int((datetime.now() - info["start_time"]).total_seconds() / 60))
            lista.append(f"- {folio} — {nombre}\n  {mins//60}h {mins%60}min restantes")
        else:
            lista.append(f"- {folio} (sin timer)")
        botones.append([InlineKeyboardButton(
            text=f"Detener timer {folio}", callback_data=f"detener_{folio}"
        )])
    await message.answer(
        f"FOLIOS OAXACA ACTIVOS ({len(folios)})\n\n" + '\n\n'.join(lista) +
        f"\n\nCada folio tiene timer de {HORAS_TIMER_BOT} horas.\n\n"
        f"Para generar otro permiso use /banamex",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=botones)
    )


@dp.message(lambda message: message.text and any(p in message.text.lower() for p in
    ['costo','precio','cuanto','cuánto','deposito','depósito','pago','valor','monto']))
async def responder_costo(message: types.Message):
    await message.answer(
        f"INFORMACION DE COSTO\n\n"
        f"El costo del permiso es ${PRECIO_PERMISO} pesos.\n\n"
        "Para generar otro permiso use /banamex")


@dp.message()
async def fallback(message: types.Message):
    await message.answer("Sistema Digital Oaxaca.")


# ── ARRANQUE / CIERRE (los llama main.py) ─────────────────────────────────────
_keep_task = None


async def _keep_alive():
    while True:
        await asyncio.sleep(600)
        print(f"[HEARTBEAT] Oaxaca activo — timers: {len(timers_activos)}")


async def arranque_bot():
    """Registra el webhook. Lo llama el lifespan de main.py."""
    global _keep_task
    if not BOT_TOKEN:
        print("[BOT] Sin BOT_TOKEN — el bot queda inactivo")
        return
    await bot.delete_webhook(drop_pending_updates=True)
    if BASE_URL:
        wh = f"{BASE_URL}/webhook"
        await bot.set_webhook(wh, allowed_updates=["message", "callback_query"])
        print(f"[WEBHOOK] {wh}")
    else:
        print("[BOT] Sin BASE_URL — no se registró webhook")
    _keep_task = asyncio.create_task(_keep_alive())


async def cierre_bot():
    global _keep_task
    if _keep_task:
        _keep_task.cancel()
        try:
            await _keep_task
        except asyncio.CancelledError:
            pass
        _keep_task = None
    try:
        await bot.session.close()
    except Exception:
        pass


async def procesar_update(data: dict):
    update = types.Update(**data)
    await dp.feed_webhook_update(bot, update)
