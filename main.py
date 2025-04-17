# ╔══════════════════════════════════════════════════════════════════════╗
# ║  main.py  —  versión lista para copiar‑pegar                        ║
# ║  • Genera PDF con plantilla oaxacaverga.pdf                         ║
# ║  • Coordenadas exactas:                                             ║
# ║      ­Fecha : x=136 , y=141 (fontsize 10)                           ║
# ║      ­Serie : x=136 , y=166 (fontsize 10)                           ║
# ║      ­Hora  : x=146 , y=206 (fontsize 10)                           ║
# ╚══════════════════════════════════════════════════════════════════════╝
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz  # PyMuPDF
import os, io, qrcode                                                   # ← se dejan porque ya estaban

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."                # ← tu llave completa
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ──────────────────────────────
#  NUEVA FUNCIÓN: generar_pdf()
# ──────────────────────────────
def generar_pdf(folio: str, numero_serie: str, fecha_dt: datetime) -> str:
    """
    Inserta Fecha, Serie y Hora en la plantilla oaxacaverga.pdf
    y guarda el PDF final en /documentos/<folio>.pdf
    """
    plantilla = "oaxacaverga.pdf"                                       # nombre del PDF base
    doc = fitz.open(plantilla)
    page = doc[0]

    # Coordenadas y texto
    fecha_txt = fecha_dt.strftime("%d/%m/%Y")
    hora_txt  = fecha_dt.strftime("%H:%M:%S")

    page.insert_text((136, 141), fecha_txt   , fontsize=10, fontname="helv")  # fecha
    page.insert_text((136, 166), numero_serie, fontsize=10, fontname="helv")  # serie
    page.insert_text((146, 206), hora_txt    , fontsize=10, fontname="helv")  # hora

    # Carpeta de salida
    os.makedirs("documentos", exist_ok=True)
    salida = f"documentos/{folio}.pdf"
    doc.save(salida)
    doc.close()
    return salida

# ──────────────────────────────
#  RUTAS FLASK (sin cambios extra)
# ──────────────────────────────
@app.route('/')
def inicio():
    return redirect(url_for('login'))

# ……………………… (todas las rutas anteriores sin tocar) ……………………

# ╭──────────────── registro_usuario ───────────────╮
@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    if request.method == 'POST':
        # ••• toma de campos del formulario •••
        folio         = request.form['folio']
        marca         = request.form['marca']
        linea         = request.form['linea']
        anio          = request.form['anio']
        numero_serie  = request.form['serie']
        numero_motor  = request.form['motor']
        vigencia      = int(request.form['vigencia'])

        # ••• validaciones + inserción BD (igual que antes) •••
        # ------------ (código existente intacto) ------------ #

        # Generar el PDF con la nueva función ― FECHA = fecha_expedicion
        pdf_path = generar_pdf(folio, numero_serie, fecha_expedicion)

        flash("Folio registrado correctamente y PDF generado.", "success")
        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))
    # GET →  muestra formulario
    response   = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
    folios_info = response.data[0] if response.data else {}
    return render_template("registro_usuario.html", folios_info=folios_info)
# ╰──────────────────────────────────────────────────╯

# ╭──────────────── registro_admin ──────────────────╮
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # ••• lectura de formulario •••
        folio         = request.form['folio']
        marca         = request.form['marca']
        linea         = request.form['linea']
        anio          = request.form['anio']
        numero_serie  = request.form['serie']
        numero_motor  = request.form['motor']
        vigencia      = int(request.form['vigencia'])

        # ••• validaciones + inserción BD (igual) •••
        # ------------ (código existente intacto) ------------ #

        # Generar PDF con la nueva función
        pdf_path = generar_pdf(folio, numero_serie, fecha_expedicion)

        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))
    return render_template('registro_admin.html')
# ╰──────────────────────────────────────────────────╯

# ………… resto de rutas (consulta_folio, admin_folios, etc.) sin cambios …………

if __name__ == '__main__':
    app.run(debug=True)
