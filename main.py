# main.py  –– LISTO PARA COPIAR‑Y‑PEGAR
# ------------------------------------
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_file
)
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz          # PyMuPDF
import os
import qrcode        # (sigue instalado aunque no lo usemos aquí)

# ─────────────────────────  CONFIG  ──────────────────────────
app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0."
    "NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Carpeta donde guardamos los PDFs
os.makedirs("documentos", exist_ok=True)

# ─────────────────────  FUNCIÓN PDF NUEVA  ────────────────────
def generar_pdf(folio: str,
                numero_serie: str,
                fecha_expedicion: datetime) -> str:
    """
    Abre la plantilla 'oaxacaverga.pdf', escribe:
      • Fecha      en (136, 141)
      • Serie      en (136, 166)
      • Hora       en (146, 206)
    y guarda documentos/<folio>.pdf
    Devuelve la ruta completa.
    """
    plantilla = "oaxacaverga.pdf"          # asegúrate de tenerla en /src
    doc = fitz.open(plantilla)
    page = doc[0]

    # Coordenadas
    x_fecha,  y_fecha  = 136, 141
    x_serie,  y_serie  = 136, 166
    x_hora,   y_hora   = 146, 206

    # Inserciones
    page.insert_text((x_fecha, y_fecha),
                     fecha_expedicion.strftime("%d/%m/%Y"),
                     fontsize=10, fontname="helv")

    page.insert_text((x_serie, y_serie),
                     numero_serie,
                     fontsize=10, fontname="helv")

    page.insert_text((x_hora, y_hora),
                     fecha_expedicion.strftime("%H:%M:%S"),
                     fontsize=10, fontname="helv")

    salida = f"documentos/{folio}.pdf"
    doc.save(salida)
    doc.close()
    return salida

# ──────────────────────────  RUTAS  ───────────────────────────
@app.route('/')
def inicio():
    return redirect(url_for('login'))

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']

        # Admin fijo
        if u == 'Gsr89roja.' and p == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))

        # Usuario común
        r = supabase.table("verificaciondigitalcdmx")\
                    .select("*")\
                    .eq("username", u)\
                    .eq("password", p)\
                    .execute()
        if r.data:
            session['user_id']  = r.data[0]['id']
            session['username'] = u
            return redirect(url_for('registro_usuario'))

        flash("Credenciales incorrectas", "error")

    return render_template("login.html")

# ---------- PANEL ----------
@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template("panel.html")

# ---------- CREAR USUARIO ----------
@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user   = request.form['username']
        pwd    = request.form['password']
        folios = int(request.form['folios'])

        existe = supabase.table("verificaciondigitalcdmx")\
                         .select("id").eq("username", user).execute()

        if existe.data:
            flash("El usuario ya existe", "error")
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": user,
                "password": pwd,
                "folios_asignac": folios,
                "folios_usados": 0
            }).execute()
            flash("Usuario creado", "success")

    return render_template("crear_usuario.html")

# ---------- REGISTRO (USUARIO NORMAL) ----------
@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    uid = session['user_id']

    if request.method == 'POST':
        folio        = request.form['folio']
        numero_serie = request.form['serie']
        vig          = int(request.form['vigencia'])

        # Verificar duplicado
        if supabase.table("folios_registrados").select("folio")\
                  .eq("folio", folio).execute().data:
            flash("Ese folio ya existe", "error")
            return redirect(url_for('registro_usuario'))

        # Disponibilidad de folios
        info = supabase.table("verificaciondigitalcdmx")\
                       .select("folios_asignac, folios_usados")\
                       .eq("id", uid).execute().data[0]

        if info['folios_asignac'] - info['folios_usados'] < 1:
            flash("No tienes folios disponibles", "error")
            return redirect(url_for('registro_usuario'))

        # Guardar en BD
        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": numero_serie,
            "numero_motor": request.form['motor'],
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vig)).isoformat()
        }).execute()

        # Actualizar contador
        supabase.table("verificaciondigitalcdmx")\
                .update({"folios_usados": info['folios_usados'] + 1})\
                .eq("id", uid).execute()

        # Generar PDF
        pdf = generar_pdf(folio, numero_serie, hoy)

        flash("Folio registrado y PDF generado", "success")
        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=hoy.strftime("%d/%m/%Y"))

    # GET → mostrar formulario + info
    datos = supabase.table("verificaciondigitalcdmx")\
                   .select("folios_asignac, folios_usados")\
                   .eq("id", uid).execute().data[0]
    return render_template("registro_usuario.html", folios_info=datos)

# ---------- REGISTRO (ADMIN) ----------
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio        = request.form['folio']
        numero_serie = request.form['serie']
        vig          = int(request.form['vigencia'])

        if supabase.table("folios_registrados").select("folio")\
                  .eq("folio", folio).execute().data:
            flash("Ese folio ya existe", "error")
            return render_template("registro_admin.html")

        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": numero_serie,
            "numero_motor": request.form['motor'],
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vig)).isoformat()
        }).execute()

        generar_pdf(folio, numero_serie, hoy)

        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=hoy.strftime("%d/%m/%Y"))

    return render_template("registro_admin.html")

# ---------- CONSULTA ----------
@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    if request.method == 'POST':
        folio = request.form['folio']
        r = supabase.table("folios_registrados").select("*")\
                    .eq("folio", folio).execute().data
        if not r:
            resultado = {"estado": "No encontrado", "folio": folio}
        else:
            reg  = r[0]
            fe   = datetime.fromisoformat(reg['fecha_expedicion'])
            fv   = datetime.fromisoformat(reg['fecha_vencimiento'])
            est  = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
            resultado = {
                "estado": est,
                "folio": folio,
                "fecha_expedicion": fe.strftime("%d/%m/%Y"),
                "fecha_vencimiento": fv.strftime("%d/%m/%Y"),
                "marca": reg['marca'],
                "linea": reg['linea'],
                "año": reg['anio'],
                "numero_serie": reg['numero_serie'],
                "numero_motor": reg['numero_motor']
            }
        return render_template("resultado_consulta.html", resultado=resultado)

    return render_template("consulta_folio.html")

# ---------- DESCARGAR PDF ----------
@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    return send_file(f"documentos/{folio}.pdf",
                     as_attachment=True)

# ---------- (resto de rutas: admin_folios, editar, eliminar, logout) ----------
# *Estas rutas se mantienen idénticas; no se modificaron*

# ... (PEGA AQUÍ sin cambiar nada los bloques de admin_folios,
#     editar_folio, eliminar_folio y logout tal como los tienes
#     en tu versión funcional)

# ─────────────────────────  MAIN  ─────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
